#!/usr/bin/env python3
"""Export a fixed, de-identified incident snapshot from existing SQLite records.

Read-only: no probes, network calls, schema migrations, or writes to the source DB.
This incident's local display is explicitly UTC-04:00 (America/New_York during
the selected October 2026 window), independent of the execution host timezone.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics

UTC = timezone.utc
LOCAL = timezone(timedelta(hours=-4), "EDT")
TABLES = ("checks", "latency", "trace", "ipv6", "capacity", "bloat")
SLOW_ABOVE_MS = 50.0
GAP_SECONDS = 15 * 60


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include an explicit UTC offset.")
    return result.astimezone(UTC)


def utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def local(value: datetime) -> str:
    return value.astimezone(LOCAL).isoformat(timespec="seconds")


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def median(values) -> float | None:
    present = [value for value in values if value is not None]
    return rounded(statistics.median(present)) if present else None


def mean(values) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None


def periods(timeline):
    """Freeze the project's current rule, independently of future collector edits."""
    values = sorted(row["internet_p50_ms"] for row in timeline if row["internet_p50_ms"] is not None)
    if not values:
        return None, []
    # Match homenet.episodes.normal_latency: floor(n*0.1), zero-based.
    baseline = values[int(len(values) * 0.1)]
    limit = baseline + SLOW_ABOVE_MS
    found, slow = [], []
    previous, good_run = None, 0

    def close(open_end):
        if len(slow) >= 2:
            found.append({
                "start_utc": slow[0]["at_utc"], "end_utc": slow[-1]["at_utc"],
                "start_local": slow[0]["at_local"], "end_local": slow[-1]["at_local"],
                "duration_seconds": (instant(slow[-1]["at_utc"]) - instant(slow[0]["at_utc"])).total_seconds(),
                "slow_checks": len(slow),
                "internet_p50_ms": median(row["internet_p50_ms"] for row in slow),
                "gateway_p50_ms": median(row["gateway_p50_ms"] for row in slow),
                "open_end": open_end,
            })
        slow.clear()

    for row in timeline:
        if row["internet_p50_ms"] is None:
            continue
        when = instant(row["at_utc"])
        if slow and previous is not None and (when - previous).total_seconds() > GAP_SECONDS:
            close(True)
            good_run = 0
        if row["internet_p50_ms"] > limit:
            slow.append(row)
            good_run = 0
        elif slow:
            good_run += 1
            if good_run >= 2:
                close(False)
        previous = when
    if slow:
        close(True)
    return baseline, found


def inside(value, found) -> bool:
    when = instant(value)
    return any(instant(period["start_utc"]) <= when <= instant(period["end_utc"]) for period in found)


def error_category(value: str | None) -> str | None:
    """Never publish raw exception text: it can contain paths, endpoints or tokens."""
    if value is None:
        return None
    codes = re.findall(r"HTTP (\d{3})", value)
    if codes:
        return "+".join(f"http_{code}" for code in sorted(set(codes)))
    lowered = value.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "reset" in lowered:
        return "connection_reset"
    return "other_measurement_error"


def missing_ipv6_kind(row, historically_probed: bool) -> str | None:
    """Retain legacy ambiguity and understand the newer collector's explicit labels."""
    if row["v4_p50"] is None or row["v6_p50"] is not None:
        return None
    verdict = row["verdict"] or ""
    if "no IPv6 TCP probes recorded" in verdict:
        return None
    if "IPv6 address lookup unavailable" in verdict:
        return "lookup"
    if verdict == "IPv6 fails" or "IPv6 TCP probes had no successful connections" in verdict:
        return "tcp"
    return "unclassified" if historically_probed else None


def no_address_result(row) -> bool:
    verdict = row["verdict"] or ""
    return verdict == "no IPv6 address" or "no IPv6 probe address" in verdict


def export_snapshot(database: Path, through: datetime) -> dict:
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")  # All tables come from one consistent read snapshot.
        bound = through.isoformat(timespec="seconds")
        records = {
            table: [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE julianday(at) <= julianday(?) ORDER BY julianday(at)", (bound,))]
            for table in TABLES
        }
    finally:
        connection.close()
    if not records["checks"]:
        raise ValueError("No checks exist through the requested cutoff.")
    first, last = instant(records["checks"][0]["at"]), instant(records["checks"][-1]["at"])
    # UTC-04:00 is deliberately explicit, rather than relying on host localtime.
    if not (instant("2026-10-01T00:00:00Z") <= first <= through < instant("2026-11-01T06:00:00Z")):
        raise ValueError("This incident exporter is scoped to the October 2026 EDT window; review timezone rules for a different window.")

    per_check = defaultdict(lambda: defaultdict(list))
    for row in records["latency"]:
        if row["layer"] in ("gateway", "internet"):
            per_check[row["at"]][row["layer"]].append(row["p50_ms"])
    timeline = []
    for at in sorted({row["at"] for row in records["checks"]}):
        layers = per_check[at]
        when = instant(at)
        timeline.append({
            "at_utc": utc(when), "at_local": local(when),
            "gateway_p50_ms": mean(layers["gateway"]),
            "internet_p50_ms": mean(layers["internet"]),
            "available_internet_targets": sum(value is not None for value in layers["internet"]),
            "expected_internet_targets": 2,
        })
    normal, found = periods(timeline)
    if normal is None:
        raise ValueError("No internet p50 observations exist through this cutoff.")

    gateway = [row for row in records["latency"] if row["layer"] == "gateway"]
    intervals = [(instant(b["at_utc"]) - instant(a["at_utc"])).total_seconds() for a, b in zip(timeline, timeline[1:])]
    sampled_slow = sum(row["internet_p50_ms"] is not None and row["internet_p50_ms"] > normal + SLOW_ABOVE_MS for row in timeline)

    by_v6_run = defaultdict(list)
    eligible = {row["target"] for row in records["ipv6"] if row["v6_p50"] is not None
                or row["verdict"] == "IPv6 fails"
                or "IPv6 TCP probes had no successful connections" in (row["verdict"] or "")}
    aliases = {target: f"public-target-{index + 1}" for index, target in enumerate(sorted({row["target"] for row in records["ipv6"]}))}
    for row in records["ipv6"]:
        by_v6_run[row["at"]].append(row)

    def v6_outcome(row):
        return missing_ipv6_kind(row, row["target"] in eligible) is not None

    ipv6 = {}
    for label, is_inside in (("inside", True), ("outside", False)):
        runs = [(at, rows) for at, rows in by_v6_run.items() if inside(at, found) == is_inside]
        rows = [row for _, group in runs for row in group]
        ipv6[label] = {
            "runs": len(runs), "target_rows": len(rows),
            "runs_with_any_missing_ipv6_outcome_while_ipv4_answered": sum(any(v6_outcome(row) for row in group) for _, group in runs),
            "runs_with_explicit_connection_failure": sum(any(missing_ipv6_kind(row, row["target"] in eligible) == "tcp" for row in group) for _, group in runs),
            "runs_with_no_address_result": sum(any(v6_outcome(row) and no_address_result(row) for row in group) for _, group in runs),
            "explicit_connection_failure_rows": sum(missing_ipv6_kind(row, row["target"] in eligible) == "tcp" for row in rows),
            "no_address_result_rows_for_ever_testable_targets": sum(v6_outcome(row) and no_address_result(row) for row in rows),
            "explicit_lookup_unavailable_rows": sum(missing_ipv6_kind(row, row["target"] in eligible) == "lookup" for row in rows),
            "unclassified_missing_rows": sum(missing_ipv6_kind(row, row["target"] in eligible) == "unclassified" for row in rows),
            "no_ipv6_tcp_probes_recorded_rows": sum("no IPv6 TCP probes recorded" in (row["verdict"] or "") for row in rows),
            "paired_response_rows": sum(row["v4_p50"] is not None and row["v6_p50"] is not None for row in rows),
        }
    ipv6["per_target"] = []
    for target, alias in aliases.items():
        rows = [row for row in records["ipv6"] if row["target"] == target]
        paired = [row for row in rows if row["v4_p50"] is not None and row["v6_p50"] is not None]
        ipv6["per_target"].append({
            "target_alias": alias, "runs": len(rows), "paired_response_runs": len(paired),
            "paired_ipv4_p50_median_ms": median(row["v4_p50"] for row in paired),
            "paired_ipv6_p50_median_ms": median(row["v6_p50"] for row in paired),
            "explicit_connection_failure_rows": sum(missing_ipv6_kind(row, row["target"] in eligible) == "tcp" for row in rows),
            "no_address_result_rows": sum(v6_outcome(row) and no_address_result(row) for row in rows),
        })

    capacity = {}
    for label, is_inside in (("inside", True), ("outside", False)):
        rows = [row for row in records["capacity"] if inside(row["at"], found) == is_inside]
        capacity[label] = {
            "runs": len(rows),
            "download_successes": sum(row["down_mbps"] is not None for row in rows),
            "upload_successes": sum(row["up_mbps"] is not None for row in rows),
            "download_median_mbps": median(row["down_mbps"] for row in rows),
            "upload_median_mbps": median(row["up_mbps"] for row in rows),
            "download_failed_measurements": sum(row["down_error"] is not None for row in rows),
            "upload_failed_measurements": sum(row["up_error"] is not None for row in rows),
            "download_failure_categories": dict(sorted(Counter(error_category(row["down_error"]) for row in rows if row["down_error"] is not None).items())),
        }
    capacity["measurement_semantics"] = {
        "download": "Application payload bytes read by this client divided by phase duration",
        "upload": "Client-side payload generation/send estimate divided by phase duration; remote receiver goodput is not measured",
        "missing": "Failed/unavailable measurement remains null, never zero Mbps",
    }

    traces_by_run = defaultdict(list)
    allowed_segments = {"home router", "ISP access line", "ISP / internet", "unknown"}
    for row in records["trace"]:
        traces_by_run[row["at"]].append(row)
    traces = {}
    for label, wanted in (("all", None), ("inside", True), ("outside", False)):
        runs = [rows for at, rows in traces_by_run.items() if wanted is None or inside(at, found) == wanted]
        segments, terminal, added = [], [], []
        usable = 0
        for rows in runs:
            responding = sorted((row for row in rows if row["effective_ms"] is not None), key=lambda row: row["hop"])
            if not responding:
                continue
            usable += 1
            biggest = max(responding, key=lambda row: row["added_ms"] or 0)
            segments.append(biggest["segment"] if biggest["segment"] in allowed_segments else "unclassified")
            terminal.append(responding[-1]["effective_ms"])
            added.append(biggest["added_ms"])
        traces[label] = {
            "runs": len(runs), "usable_runs": usable,
            "largest_added_segment_heuristic_counts": dict(sorted(Counter(segments).items())),
            "terminal_effective_latency_median_ms": median(terminal),
            "largest_added_latency_median_ms": median(added),
        }

    bloat = {"runs": len({row["at"] for row in records["bloat"]}), "phase_rows": len(records["bloat"])}
    for phase in ("download", "upload"):
        rows = [row for row in records["bloat"] if row["phase"] == phase]
        bloat[phase] = {
            "phase_rows": len(rows), "successful_transfer_phases": sum(row["mbps"] is not None and row.get("error") is None for row in rows),
            "throughput_median_mbps": median(row["mbps"] for row in rows),
            "stored_added_latency_median_ms": median(row["added_ms"] for row in rows),
            "gateway_loaded_p50_median_ms": median(row["gateway_p50"] for row in rows),
            "gateway_loaded_p95_median_ms": median(row["gateway_p95"] for row in rows),
        }

    snapshot = {
        "schema_version": 1, "analysis_type": "existing-home-records-read-only",
        "source": {
            "database": "data/home.sqlite", "sqlite_access": "URI mode=ro; query_only; one read transaction",
            "generator": "scripts/export-home-incident.py",
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "collection": "Previously saved homenet check/path/ipv6/capacity/bloat results; no new measurement during export",
            "record_kind": "Per-run summary statistics, not original packet timing samples",
            "ipv6_record_semantics": "Legacy IPv6 fails/no IPv6 address labels are preserved as TCP failure/unclassified no-address outcomes respectively. Newer explicit lookup/TCP/no-probes labels are also recognized without publishing exception text.",
            "raw_history_published": False,
        },
        "window": {
            "start_utc": utc(first), "end_utc": utc(last), "cutoff_utc": utc(through),
            "start_local": local(first), "end_local": local(last),
            "timezone": "America/New_York", "utc_offset": "-04:00",
            "timezone_conversion": "Explicit EDT offset for this October 2026 window; independent of host timezone",
            "elapsed_hours": rounded((last - first).total_seconds() / 3600),
        },
        "counts": {**{f"{table}_rows": len(records[table]) for table in TABLES},
            "distinct_check_runs": len(timeline), "ipv6_runs": len(by_v6_run), "trace_runs": len(traces_by_run),
            "latency_attempts_by_layer": dict(sorted({layer: sum(row["sent"] or 0 for row in records["latency"] if row["layer"] == layer) for layer in {row["layer"] for row in records["latency"]}}.items())),
        },
        "rules": {
            "baseline": "Sorted mean-of-available-target p50 values at zero-based floor(n*0.1), matching current episode rule",
            "slow_above_baseline_ms": SLOW_ABOVE_MS, "minimum_slow_checks": 2,
            "recovery_checks": 2, "gap_closes_open_episode_seconds": GAP_SECONDS,
            "episode_end": "Last slow sample; confirmation occurs after two subsequent non-slow samples",
            "protocols": "Gateway uses ICMP echo; internet uses TCP connects; probes are neither simultaneous nor interchangeable",
            "ipv6_missing_outcome": "Any target has IPv4 p50 but no usable IPv6 result: explicit TCP/lookup outcome, or legacy/unclassified result for a historically probed target. No-probes records are excluded.",
        },
        "summary": {
            "normal_internet_p50_ms": rounded(normal), "episode_count": len(found),
            "episode_span_hours": rounded(sum(period["duration_seconds"] for period in found) / 3600),
            "slow_checks": sum(period["slow_checks"] for period in found),
            "all_above_threshold_checks_including_isolated_spikes": sampled_slow,
            "gateway_p50_median_ms": median(row["p50_ms"] for row in gateway),
            "gateway_p50_max_ms": max((row["p50_ms"] for row in gateway if row["p50_ms"] is not None), default=None),
            "gateway_p95_over_30ms_rows": sum(row["p95_ms"] is not None and row["p95_ms"] > 30 for row in gateway),
            "gateway_nonzero_loss_rows": sum(row["loss_pct"] > 0 for row in gateway),
            "median_check_spacing_seconds": median(intervals),
            "gaps_over_15_minutes": sum(interval > GAP_SECONDS for interval in intervals),
            "largest_check_gap_seconds": max(intervals, default=None),
        },
        "episodes": found,
        "comparisons": {"ipv6": ipv6, "capacity": capacity, "traces": traces, "bloat": bloat},
        "limitations": [
            "Observed plateau and IPv6 outcomes are correlated; no cause or home repair is confirmed.",
            "Legacy no IPv6 address conflates no usable AAAA resolution with other resolver outcomes; it does not establish DNS failure.",
            ("No capacity runs fall within the detected episodes; outside medians cannot identify saturated direction or device."
             if capacity["inside"]["runs"] == 0 else "Inside/outside capacity samples are active transfer estimates, not passive utilization or proof of a saturating device."),
            "Home upload estimates are client-side payload counts, not receiver-confirmed goodput or provisioned line capacity.",
            "Gateway tails and loss mean low medians do not rule out local wireless/router/host effects.",
            "Trace segment attribution is a probe heuristic, not proof of a physical queue location or ISP fault.",
            "A single host/connection, sequential protocols and small per-check samples do not measure real call quality.",
        ],
        "privacy": {
            "excluded": ["SSID", "MAC/BSSID", "user/roommate identifiers", "private addresses", "endpoint names/addresses", "raw exception text", "secrets"],
            "target_identifiers": "Opaque aliases only; alias mapping is not exported",
        },
        "timeline": timeline,
    }
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/home.sqlite"))
    parser.add_argument("--through", required=True, help="Fixed inclusive UTC cutoff, e.g. 2026-10-12T06:05:02Z")
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/home-incident.json"))
    args = parser.parse_args()
    if args.database.resolve() == args.output.resolve():
        parser.error("Output must not overwrite the source database.")
    snapshot = export_snapshot(args.database, instant(args.through))
    encoded = json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    # Only de-identified high-level counts are printed, never raw rows/addresses.
    print(json.dumps({"schema_version": snapshot["schema_version"], "cutoff_utc": snapshot["window"]["cutoff_utc"],
                      "checks": snapshot["counts"]["distinct_check_runs"], "episodes": snapshot["summary"]["episode_count"],
                      "output_file": args.output.name}, ensure_ascii=False))


if __name__ == "__main__":
    main()
