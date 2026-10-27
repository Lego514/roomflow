"""Privacy-filtered monitoring snapshots, with honest historical/stale labels."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from . import incidents

MAX_TIMELINE = 2000
# Prefix replay deliberately uses the same state machine as persisted events.
# Small isolated drills are replayable; ordinary multi-day history is not
# expanded into a quadratic-size collection of prefix snapshots.
MAX_REPLAY_SAMPLES = 200


def samples_from_connection(db: sqlite3.Connection, through: str | None = None) -> list[dict]:
    """Read one existing check at a time, without publishing raw target names.

    The caller owns the read transaction. Duplicate legacy check rows at the
    same timestamp represent one monitoring check, not a confirmation streak.
    """
    cutoff = incidents.instant(through) if through else None
    times = {at for (at,) in db.execute("select distinct at from checks")
             if cutoff is None or incidents.instant(at) <= cutoff}
    target_rows = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    # Only measurements tied to actual completed checks participate.
    for at, layer, target, sent, loss, p50, p95 in db.execute(
            "select at, layer, target, sent, loss_pct, p50_ms, p95_ms from latency order by rowid"):
        if at in times and layer in incidents.LAYERS:
            target_rows[at][layer][target].add((sent, loss, p50, p95))
    grouped = defaultdict(lambda: defaultdict(list))
    for at, layers in target_rows.items():
        for layer, targets in layers.items():
            for rows in targets.values():
                for sent, loss, p50, p95 in sorted(rows, key=repr):
                    grouped[at][layer].append({"sent": sent, "loss_pct": loss, "p50_ms": p50,
                                               "p95_ms": p95, "_collision": len(rows) > 1})
    return [incidents.sample_from_records(at, grouped[at]) for at in sorted(times, key=incidents.instant)]


def historical_samples(snapshot: dict) -> list[dict]:
    """Fallback for the earlier two-layer de-identified evidence file.

    Only p50 values were retained; attempts, failure ratios and DNS/service
    outcomes cannot be reconstructed and are never manufactured.
    """
    result = []
    for row in snapshot.get("timeline", []):
        layers = {}
        for name in incidents.LAYERS:
            p50 = row.get(name + "_p50_ms")
            abnormal = isinstance(p50, (int, float)) and p50 > incidents.MAX_P95_MS[name]
            layers[name] = {"p50Ms": p50, "p95Ms": None, "attempts": None, "failed": None,
                            "failurePct": None, "status": "degraded" if abnormal else "unknown",
                            "complete": False, "flags": ["missing-metrics"] + (["high-p50-without-p95"] if abnormal else [])}
        result.append({"at": row["at_utc"], "layers": layers})
    return result


def _drill_replay(timeline: list[dict], policy: incidents.Policy) -> dict:
    if len(timeline) > MAX_REPLAY_SAMPLES:
        return {"frames": [], "totalSamples": len(timeline), "available": False, "reason": "sample-limit"}
    frames = []
    for count in range(1, len(timeline) + 1):
        prefix = incidents.replay(timeline[:count], policy)
        active = any(incident["status"] == "open" for incident in prefix["incidents"])
        if active:
            stage = "recovering" if prefix["pendingRecoveryChecks"] else "open"
        elif prefix["timeline"][-1]["status"] == "unknown":
            stage = "unknown"
        elif prefix["pendingAbnormalChecks"]:
            stage = "pending"
        else:
            stage = "resolved" if prefix["incidents"] else "normal"
        frames.append({"sampleCount": count, "at": prefix["timeline"][-1]["at"], "stage": stage,
                       "incidents": prefix["incidents"], "notifications": prefix["notifications"],
                       "pendingAbnormalChecks": prefix["pendingAbnormalChecks"],
                       "pendingRecoveryChecks": prefix["pendingRecoveryChecks"]})
    return {"frames": frames, "totalSamples": len(timeline), "available": True}


def build_dashboard(samples: list[dict], *, source_kind: str = "local-history",
                    label: str = "Local saved observations", evaluated_at: str | None = None,
                    generated_at: str | None = None, notes: list[str] | None = None,
                    policy: incidents.Policy | None = None, replay_result: dict | None = None) -> dict:
    if source_kind not in ("local-history", "historical-demo", "lab-drill"):
        raise ValueError("Unknown monitoring source kind.")
    policy = policy or incidents.Policy()
    generated = incidents.utc(generated_at or datetime.now(timezone.utc).isoformat())
    evaluated = incidents.utc(evaluated_at or generated)
    result = replay_result if replay_result is not None else incidents.replay(samples, policy)
    timeline = result["timeline"]
    latest = timeline[-1] if timeline else None
    elapsed = (incidents.instant(evaluated) - incidents.instant(latest["at"])).total_seconds() if latest else None
    age = max(0, elapsed) if elapsed is not None else None
    clock_skew = elapsed is not None and elapsed < -60
    monitor_status = ("empty" if not latest else "historical" if source_kind != "local-history"
                      else "stale" if age > policy.stale_after_seconds or clock_skew else "current")
    snapshot = {"schemaVersion": 1,
            "source": {"kind": source_kind, "label": label, "windowStart": timeline[0]["at"] if timeline else None,
                       "windowEnd": latest["at"] if latest else None, "generatedAt": generated,
                       "notes": list(notes or [])},
            "policy": policy.as_dict(), "latest": latest,
            "timeline": timeline[-MAX_TIMELINE:], "timelineTotal": len(timeline),
            "timelineTruncated": len(timeline) > MAX_TIMELINE,
            "incidents": result["incidents"], "notifications": result["notifications"],
            "monitor": {"status": monitor_status, "evaluatedAt": evaluated,
                        "lastObservedAt": latest["at"] if latest else None, "ageSeconds": age,
                        "clockSkew": clock_skew,
                        "pendingAbnormalChecks": result["pendingAbnormalChecks"],
                        "pendingRecoveryChecks": result["pendingRecoveryChecks"]}}
    if source_kind == "lab-drill":
        snapshot["replay"] = _drill_replay(timeline, policy)
    return snapshot


def from_connection(db: sqlite3.Connection, *, persist: bool = False, **kwargs) -> dict:
    """Create a snapshot inside one transaction; optionally persist local events.

    Read-only historical exports never create incident tables or migrate source
    data. A persisting caller must acquire BEGIN IMMEDIATE before reading.
    """
    samples = samples_from_connection(db)
    if persist:
        result = incidents.persist(db, samples)
        return build_dashboard(samples, replay_result=result, **kwargs)
    return build_dashboard(samples, **kwargs)


def atomic_export(snapshot: dict, output: Path) -> None:
    """Readers see a complete old/new JSON document; temporary files are local."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    handle, name = tempfile.mkstemp(prefix=".observations-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
