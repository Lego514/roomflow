"""Conservative, deterministic incidents from selected probe observations.

An incident is a local monitoring record, never a diagnosis or an external
notification. Missing probes and collection gaps cannot establish recovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
import statistics

from .stats import MAX_LOSS_PCT, MAX_P95_MS

LAYERS = ("gateway", "internet", "dns", "service")
EXPECTED_SERIES = {"gateway": 1, "internet": 2, "dns": 2, "service": 2}
SCHEMA = """
create table if not exists monitor_samples (at text primary key, payload text not null);
create table if not exists monitor_incidents (id text primary key, payload text not null);
create table if not exists monitor_transitions (
  id text primary key, incident_id text not null, type text not null, at text not null,
  unique(incident_id, type)
);
"""


@dataclass(frozen=True)
class Policy:
    open_after: int = 3
    recover_after: int = 2
    max_gap_seconds: int = 900
    stale_after_seconds: int = 900
    expected_series: dict[str, int] = field(default_factory=lambda: dict(EXPECTED_SERIES))

    def __post_init__(self):
        if min(self.open_after, self.recover_after, self.max_gap_seconds, self.stale_after_seconds) < 1:
            raise ValueError("Incident policy values must be positive.")

    def as_dict(self):
        return {"openAfter": self.open_after, "recoverAfter": self.recover_after,
                "maxGapSeconds": self.max_gap_seconds, "staleAfterSeconds": self.stale_after_seconds,
                "requiredLayers": list(LAYERS), "failureThresholdPct": MAX_LOSS_PCT,
                "p95ThresholdMs": dict(MAX_P95_MS), "expectedSeries": dict(self.expected_series),
                "durationSemantics": "Span from first abnormal check through last observed check or confirmed recovery; excludes collection gaps and unknown intervals. This is observed monitoring span, not proven continuous outage time.",
                "latencyAggregation": "p50Ms is the mean of available per-target p50 values; p95Ms is the maximum per-target p95, not a pooled percentile.",
                "notificationSemantics": "Durable local transition records only; no external messages are sent."}


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Monitoring timestamps require an explicit UTC offset.")
    return result.astimezone(timezone.utc)


def utc(value: str | datetime) -> str:
    dt = instant(value) if isinstance(value, str) else value.astimezone(timezone.utc)
    return dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds").replace("+00:00", "Z")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _rounded(value):
    return round(value, 6) if value is not None else None


def aggregate_layer(layer: str, records: list[dict], expected_series: int) -> dict:
    """Aggregate stored summaries; endpoint identifiers never enter the result.

    Failed counts are recovered only when the stored percent is consistent with
    an integer number of attempts. A missing count/percent remains unknown.
    """
    flags = []
    attempts, failed = 0, 0
    counts_known = True
    complete = len(records) == expected_series
    p50s, p95s = [], []
    abnormal = False
    for row in records:
        sent, loss = row.get("sent"), row.get("loss_pct")
        p50, p95 = row.get("p50_ms"), row.get("p95_ms")
        valid_attempts = _number(sent) and sent >= 0 and int(sent) == sent
        if not valid_attempts or sent == 0:
            complete = False
        valid_count = valid_attempts and _number(loss) and 0 <= loss <= 100
        count = round(sent * loss / 100) if valid_count else None
        if valid_count and sent and abs(count * 100 / sent - loss) > 0.0001:
            valid_count = False
        if not valid_count:
            counts_known = False
            complete = False
        else:
            attempts += int(sent)
            failed += count
        if _number(p50) and p50 >= 0:
            p50s.append(p50)
        if _number(p95) and p95 >= 0:
            p95s.append(p95)
        if valid_attempts and sent > 0:
            if valid_count and loss > MAX_LOSS_PCT:
                abnormal = True
                flags.append("unsuccessful-probes")
            if _number(p95) and p95 > MAX_P95_MS[layer]:
                abnormal = True
                flags.append("high-p95")
            # A recorded p50 above the p95 threshold is sufficient evidence of
            # slow observations, but never sufficient evidence of healthy tails.
            elif not _number(p95) and _number(p50) and p50 > MAX_P95_MS[layer]:
                abnormal = True
                flags.append("high-p50-without-p95")
            if valid_count and count < sent and (not _number(p50) or not _number(p95)):
                complete = False
    if any(row.get("_collision") for row in records):
        flags.append("conflicting-target-records")
        complete = counts_known = False
    if not records or not any(_number(row.get("sent")) and row["sent"] > 0 for row in records):
        flags.append("no-probes")
    if len(records) != expected_series:
        flags.append("incomplete-targets")
    if not complete:
        flags.append("incomplete-observation")
    status = "degraded" if abnormal else "ok" if complete else "unknown"
    return {"p50Ms": _rounded(statistics.fmean(p50s)) if p50s else None,
            "p95Ms": _rounded(max(p95s)) if p95s else None,
            "attempts": attempts if counts_known and records else None,
            "failed": failed if counts_known and records else None,
            "failurePct": _rounded(100 * failed / attempts) if counts_known and attempts else None,
            "status": status, "flags": sorted(set(flags)), "complete": complete,
            "observedSeries": len(records), "expectedSeries": expected_series}


def sample_from_records(at: str, layers: dict[str, list[dict]], expected_series=None) -> dict:
    expected = expected_series or EXPECTED_SERIES
    summary = {name: aggregate_layer(name, layers.get(name, []), expected.get(name, 1)) for name in LAYERS}
    status = ("degraded" if any(layer["status"] == "degraded" for layer in summary.values())
              else "ok" if all(layer["status"] == "ok" for layer in summary.values()) else "unknown")
    return {"at": utc(at), "status": status, "layers": summary}


def sample_from_layers(at: str, layers: dict, expected_series=None) -> dict:
    return sample_from_records(at, {name: [{"sent": series.sent, "loss_pct": series.loss_pct,
                                "p50_ms": series.p50, "p95_ms": series.p95} for series in items]
                                          for name, items in layers.items()}, expected_series)


def _identifier(prefix: str, at: str) -> str:
    return prefix + "-" + hashlib.sha256(at.encode("utf-8")).hexdigest()[:16]


def _safe_sample(sample: dict) -> dict:
    """Whitelist the public contract, even when a caller supplied private fields."""
    layers = {}
    for name in LAYERS:
        original = sample.get("layers", {}).get(name, {})
        layer = {key: original.get(key) if _number(original.get(key)) and original[key] >= 0 else None
                 for key in ("p50Ms", "p95Ms", "attempts", "failed", "failurePct")}
        if layer["failurePct"] is not None and layer["failurePct"] > 100:
            layer["failurePct"] = None
        for key in ("attempts", "failed"):
            if layer[key] is not None and int(layer[key]) != layer[key]:
                layer[key] = None
        if layer["failed"] is not None and layer["attempts"] is not None and layer["failed"] > layer["attempts"]:
            layer["failed"] = layer["failurePct"] = None
        # Free-form collector strings may include addresses or errors. Publish
        # only known machine flags; lab-specific detail belongs in source notes.
        allowed_flags = {"unsuccessful-probes", "high-p95", "high-p50-without-p95", "no-probes",
                         "incomplete-targets", "incomplete-observation", "missing-metrics", "conflicting-target-records"}
        layer["flags"] = sorted(set(original.get("flags", [])) & allowed_flags)
        status = original.get("status", "unknown")
        layer["status"] = status if status in ("ok", "degraded", "unknown") else "unknown"
        attempts, failed = layer["attempts"], layer["failed"]
        valid_counts = (_number(attempts) and attempts > 0 and int(attempts) == attempts
                        and _number(failed) and int(failed) == failed and 0 <= failed <= attempts)
        metrics_complete = valid_counts and (failed == attempts or
                                             (layer["p50Ms"] is not None and layer["p95Ms"] is not None))
        layer["complete"] = original.get("complete", layer["status"] == "ok") is True and metrics_complete
        if valid_counts:
            layer["failurePct"] = _rounded(100 * failed / attempts)
        observed = ((_number(attempts) and attempts > 0) or
                    (attempts is None and (layer["p50Ms"] is not None or layer["p95Ms"] is not None)))
        if valid_counts and layer["failurePct"] > MAX_LOSS_PCT:
            layer["status"] = "degraded"
            layer["flags"] = sorted(set(layer["flags"]) | {"unsuccessful-probes"})
        if observed and layer["p95Ms"] is not None and layer["p95Ms"] > MAX_P95_MS[name]:
            layer["status"] = "degraded"
            layer["flags"] = sorted(set(layer["flags"]) | {"high-p95"})
        elif observed and layer["p95Ms"] is None and layer["p50Ms"] is not None and layer["p50Ms"] > MAX_P95_MS[name]:
            layer["status"] = "degraded"
            layer["flags"] = sorted(set(layer["flags"]) | {"high-p50-without-p95"})
        if not observed:
            layer["status"] = "unknown"
            layer["complete"] = False
        if not layer["complete"] and layer["status"] == "ok":
            layer["status"] = "unknown"
        for key in ("observedSeries", "expectedSeries"):
            if _number(original.get(key)) and original[key] >= 0:
                layer[key] = original[key]
        layers[name] = layer
    status = ("degraded" if any(layer["status"] == "degraded" for layer in layers.values())
              else "ok" if all(layer["status"] == "ok" and layer["complete"] for layer in layers.values()) else "unknown")
    return {"at": utc(sample["at"]), "status": status, "layers": layers}


def _explain(incident):
    affected = incident["affectedLayers"]
    incident["observations"] = [f"{name}: selected probes exceeded the configured latency or unsuccessful-probe threshold." for name in affected]
    incident["unknowns"] = ["Selected probes do not establish a root cause, an ISP fault, a service-wide outage, or real call quality.",
                            "Checks are sequential samples; conditions between checks were not continuously observed."]
    if incident["evidenceGaps"]:
        incident["unknowns"].append("Collection gaps or incomplete checks interrupt evidence; missing time is excluded from observed duration and does not prove recovery.")
    advice = {"gateway": "Compare gateway echo responses over wired and Wi-Fi paths; check host and gateway behavior.",
              "internet": "Compare multiple public TCP targets and a wired path before assigning an upstream cause.",
              "dns": "Compare resolver responses and distinguish name lookup failure from IP connectivity.",
              "service": "Compare service TCP connection results with DNS and public-IP probes; verify the application separately."}
    incident["nextChecks"] = [advice[name] for name in affected]


def _evidence(incident: dict, timeline: list[dict]) -> dict:
    """Summarize only the incident's observed abnormal envelope.

    Recovery confirmation checks do not dilute the failure ratio. Healthy and
    unknown observations *between* abnormal checks remain in the envelope, so
    every layer can provide an honest simultaneous comparison. Per-check p95
    maxima are summaries, never a pooled event percentile.
    """
    start = instant(incident["startedAt"])
    end = instant(incident["lastAbnormalAt"])
    checks = [sample for sample in timeline if start <= instant(sample["at"]) <= end]
    layers = {}
    for name in LAYERS:
        summary = {"peakP95Ms": None, "peakP95At": None,
                   "latencyThresholdMs": MAX_P95_MS[name], "failureThresholdPct": MAX_LOSS_PCT,
                   "attempts": None, "failed": None, "failurePct": None,
                   "countsComplete": True, "countedChecks": 0, "missingCountChecks": 0,
                   "abnormalChecks": 0, "healthyChecks": 0, "unknownChecks": 0,
                   "latencyBreaches": 0, "failureBreaches": 0}
        attempts_total, failed_total = 0, 0
        for sample in checks:
            layer = sample["layers"][name]
            status_key = {"degraded": "abnormalChecks", "ok": "healthyChecks", "unknown": "unknownChecks"}[layer["status"]]
            summary[status_key] += 1
            # The collector flags a breach when any individual target exceeds
            # the failure threshold. Layer totals are weighted across targets
            # and may mask that breach (one 10%-failed target + one healthy
            # target can total 5%). Preserve the canonical observation even
            # when another target's missing counts prevent a complete total.
            if "unsuccessful-probes" in layer["flags"]:
                summary["failureBreaches"] += 1
            attempts, failed = layer["attempts"], layer["failed"]
            counts_known = (_number(attempts) and int(attempts) == attempts and attempts >= 0
                            and _number(failed) and int(failed) == failed and 0 <= failed <= attempts)
            if counts_known:
                summary["countedChecks"] += 1
                attempts_total += int(attempts)
                failed_total += int(failed)
            else:
                summary["missingCountChecks"] += 1
            observed = ((_number(attempts) and attempts > 0) or
                        (attempts is None and (layer["p50Ms"] is not None or layer["p95Ms"] is not None)))
            p95 = layer["p95Ms"] if observed else None
            if p95 is not None and (summary["peakP95Ms"] is None or p95 > summary["peakP95Ms"]):
                summary["peakP95Ms"], summary["peakP95At"] = p95, sample["at"]
            latency = p95 if p95 is not None else layer["p50Ms"] if observed else None
            if latency is not None and latency > MAX_P95_MS[name]:
                summary["latencyBreaches"] += 1
        summary["countsComplete"] = summary["missingCountChecks"] == 0
        if summary["countedChecks"]:
            summary["attempts"], summary["failed"] = attempts_total, failed_total
            summary["failurePct"] = _rounded(100 * failed_total / attempts_total) if attempts_total else None
        layers[name] = summary
    return {"startAt": incident["startedAt"], "endAt": incident["lastAbnormalAt"],
            "checkCount": len(checks), "layers": layers}


def replay(samples: list[dict], policy: Policy | None = None) -> dict:
    """Replay one check per timestamp; stable IDs make restart/export idempotent.

    A positive observation in an incomplete check can open/extend an incident,
    but recovery requires every required layer to have a complete healthy check.
    """
    policy = policy or Policy()
    unique = {}
    for sample in samples:
        clean = _safe_sample(sample)
        old = unique.get(clean["at"])
        if old is not None and old != clean:
            raise ValueError("Conflicting observations at the same timestamp.")
        unique[clean["at"]] = clean
    timeline = sorted(unique.values(), key=lambda sample: instant(sample["at"]))
    incidents, notifications, pending = [], [], []
    active = None
    healthy = 0
    previous = None
    for sample in timeline:
        at, status = sample["at"], sample["status"]
        gap = previous is not None and (instant(at) - instant(previous["at"])).total_seconds() > policy.max_gap_seconds
        if gap:
            pending = []
            healthy = 0
            if active:
                active["evidenceGaps"].append({"from": previous["at"], "to": at, "reason": "collection-gap"})
        if status == "unknown":
            pending = []
            healthy = 0
            if active:
                active["evidenceGaps"].append({"from": at, "to": at, "reason": "incomplete-check"})
        if active:
            # Only adjacent fully classified observations contribute bounded
            # observed span. Never extend an incident into an unobserved now().
            if previous and not gap and previous["status"] != "unknown" and status != "unknown":
                active["durationSeconds"] += (instant(at) - instant(previous["at"])).total_seconds()
            active["lastObservedAt"] = at
        if status == "degraded":
            healthy = 0
            affected = [name for name in LAYERS if sample["layers"][name]["status"] == "degraded"]
            if active is None:
                pending.append(sample)
                if len(pending) >= policy.open_after:
                    first = pending[0]["at"]
                    incident_id = _identifier("incident", first)
                    transition = {"id": incident_id + ":opened", "type": "opened", "at": at}
                    active = {"id": incident_id, "status": "open", "startedAt": first, "openedAt": at,
                              "lastObservedAt": at, "lastAbnormalAt": at, "resolvedAt": None,
                              "durationSeconds": (instant(at) - instant(first)).total_seconds(),
                              "affectedLayers": sorted({name for row in pending for name in LAYERS
                                                        if row["layers"][name]["status"] == "degraded"}),
                              "abnormalChecks": len(pending), "evidenceGaps": [], "transitions": [transition]}
                    incidents.append(active)
                    notifications.append({**transition, "incidentId": incident_id})
                    pending = []
            else:
                active["lastAbnormalAt"] = at
                active["abnormalChecks"] += 1
                active["affectedLayers"] = sorted(set(active["affectedLayers"]) | set(affected))
        elif status == "ok":
            pending = []
            if active:
                healthy += 1
                if healthy >= policy.recover_after:
                    transition = {"id": active["id"] + ":resolved", "type": "resolved", "at": at}
                    active["status"] = "resolved"
                    active["resolvedAt"] = at
                    active["transitions"].append(transition)
                    notifications.append({**transition, "incidentId": active["id"]})
                    active = None
                    healthy = 0
        previous = sample
    for incident in incidents:
        incident["durationSeconds"] = round(incident["durationSeconds"], 6)
        incident["spanSeconds"] = (instant(incident["lastObservedAt"]) - instant(incident["startedAt"])).total_seconds()
        incident["evidence"] = _evidence(incident, timeline)
        _explain(incident)
    return {"timeline": timeline, "incidents": incidents, "notifications": notifications,
            "pendingAbnormalChecks": len(pending), "pendingRecoveryChecks": healthy}


def initialize(db: sqlite3.Connection) -> None:
    # execute (not executescript): never implicitly commit a caller's transaction.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)


def persist(db: sqlite3.Connection, samples: list[dict], policy: Policy | None = None) -> dict:
    """Write aggregate samples and replay under the caller's write transaction.

    BEGIN IMMEDIATE at the boundary serializes scheduled writers. The append-only
    transition primary/unique keys protect against duplicate local alerts.
    """
    if not db.in_transaction:
        raise RuntimeError("Incident persistence requires an explicit write transaction.")
    initialize(db)
    latest = db.execute("select max(at) from monitor_samples").fetchone()[0]
    for sample in samples:
        clean = _safe_sample(sample)
        prior = db.execute("select payload from monitor_samples where at=?", (clean["at"],)).fetchone()
        if prior:
            if json.loads(prior[0]) != clean:
                raise ValueError("A persisted observation timestamp is immutable.")
            continue
        if latest and instant(clean["at"]) < instant(latest):
            raise ValueError("Cannot append older observations after persisted monitoring history; replay them in a separate database.")
        db.execute("insert or ignore into monitor_samples values (?,?)", (clean["at"], json.dumps(clean, allow_nan=False)))
    all_samples = [json.loads(row[0]) for row in db.execute("select payload from monitor_samples order by at")]
    result = replay(all_samples, policy)
    for incident in result["incidents"]:
        db.execute("insert into monitor_incidents values (?,?) on conflict(id) do update set payload=excluded.payload",
                   (incident["id"], json.dumps(incident, allow_nan=False)))
    for transition in result["notifications"]:
        db.execute("insert or ignore into monitor_transitions values (?,?,?,?)",
                   (transition["id"], transition["incidentId"], transition["type"], transition["at"]))
    return result
