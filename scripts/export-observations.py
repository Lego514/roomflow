#!/usr/bin/env python3
"""Export sanitized aggregate monitoring history without modifying its database.

Examples:
  python scripts/export-observations.py --through 2026-10-12T06:05:02Z --output docs/evidence/observations-demo.json
  python scripts/export-observations.py --database data/home.sqlite --output data/observations.json

--through produces a fixed historical demonstration. Omitting it exports local
history, whose stale/current state is evaluated at generation time. No probes or
external notifications are performed. Only completed check summaries participate.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homenet import dashboard, incidents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/home.sqlite"))
    parser.add_argument("--through", help="Inclusive timestamp with offset, e.g. 2026-10-12T06:05:02Z")
    parser.add_argument("--output", type=Path, default=Path("data/observations.json"))
    parser.add_argument("--sanitized-history", type=Path, help="Fallback two-layer evidence JSON; missing metrics remain unknown")
    args = parser.parse_args(argv)
    source = args.sanitized_history or args.database
    if source.resolve() == args.output.resolve():
        parser.error("Output must not overwrite its source.")
    if args.through:
        incidents.instant(args.through)
    if args.sanitized_history:
        samples = dashboard.historical_samples(json.loads(source.read_text(encoding="utf-8")))
        if args.through:
            samples = [sample for sample in samples if incidents.instant(sample["at"]) <= incidents.instant(args.through)]
        notes = ["Previously de-identified two-layer history; attempts, failure ratios, p95, DNS and service observations were not retained.",
                 "Incomplete checks cannot establish recovery; no new probes were run."]
    else:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db, db:
            db.execute("pragma query_only=on")
            db.execute("begin")
            samples = dashboard.samples_from_connection(db, args.through)
        notes = ["Read-only SQLite snapshot of previously saved completed checks; no new probes were run.",
                 "Only per-layer aggregates are published; endpoint addresses, SSID, MAC and raw errors are excluded.",
                 "Incident policy replays historical observations; local transition records are not historical messages that were actually sent."]
    historical = bool(args.through or args.sanitized_history)
    frozen = incidents.utc(args.through) if args.through else samples[-1]["at"] if historical and samples else None
    if historical:
        notes.append("Historical replay is evaluated at the fixed cutoff/last observation; generatedAt is the actual export time.")
    payload = dashboard.build_dashboard(samples, source_kind="historical-demo" if historical else "local-history",
                                        label="De-identified saved home observations" if historical else "Local saved observations",
                                        evaluated_at=frozen, notes=notes)
    dashboard.atomic_export(payload, args.output)
    print(json.dumps({"schemaVersion": 1, "checks": payload["timelineTotal"], "incidents": len(payload["incidents"]),
                      "transitions": len(payload["notifications"]), "monitor": payload["monitor"]["status"],
                      "output": args.output.name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
