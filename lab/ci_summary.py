#!/usr/bin/env python3
"""Summarize a batch's measurements.csv as a Markdown table (used by CI).

Each cell is the mean over repeats, with the range of single runs for p95 RTT.
Reads only the CSV the batch wrote; never imports netlab logic.
"""
import argparse
import csv
import platform
import statistics
from collections import defaultdict
from pathlib import Path

SCENARIOS = ["idle", "upload", "download", "both"]
POLICIES = ["fifo", "sqm", "meeting"]


def num(row, key):
    value = row.get(key, "")
    return float(value) if value not in ("", None) else None


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def fmt(value, digits=1):
    return "—" if value is None else f"{value:.{digits}f}"


def summarize(csv_path: Path, environment: str) -> str:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    cells = defaultdict(list)
    for row in rows:
        cells[(row["scenario"], row["mode"])].append(row)
    repeats = max(len(v) for v in cells.values()) if cells else 0
    lines = [
        "## Kernel lab results",
        "",
        f"{environment}. {len(rows)} runs, {repeats} per cell. "
        "p95 RTT is the mean of per-run p95 values (range of single runs in brackets).",
        "",
        "| Scenario | Policy | Meeting p95 RTT ms | Meeting loss % up / down | Meeting jitter ms up / down | Roommate Mbps up / down |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for scenario in SCENARIOS:
        for policy in POLICIES:
            runs = cells.get((scenario, policy), [])
            if not runs:
                continue
            p95 = [num(r, "rtt_p95_ms") for r in runs]
            p95_known = [v for v in p95 if v is not None]
            span = f" ({min(p95_known):.1f}–{max(p95_known):.1f})" if p95_known else ""
            mbps = lambda key: mean([(num(r, key) or 0) / 1e6 if num(r, key) is not None else None for r in runs])  # noqa: E731
            lines.append(
                f"| {scenario} | {policy} | {fmt(mean(p95))}{span} | "
                f"{fmt(mean([num(r, 'meeting-up_lost_percent') for r in runs]), 2)} / "
                f"{fmt(mean([num(r, 'meeting-down_lost_percent') for r in runs]), 2)} | "
                f"{fmt(mean([num(r, 'meeting-up_jitter_ms') for r in runs]), 2)} / "
                f"{fmt(mean([num(r, 'meeting-down_jitter_ms') for r in runs]), 2)} | "
                f"{fmt(mbps('roommate-up_bits_per_second'), 2)} / {fmt(mbps('roommate-down_bits_per_second'), 2)} |"
            )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="batch measurements.csv")
    parser.add_argument("--environment", default=f"Linux {platform.release()}")
    args = parser.parse_args()
    print(summarize(args.input, args.environment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
