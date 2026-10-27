"""Bounded-by-parent, privacy-filtered bridge for the local quick-check UI.

The parent runs this in its own process and enforces a wall-clock deadline,
including platform name resolution. No browser-supplied targets or commands.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homenet import dashboard, store
from homenet.check import run_check


def summarize(result, observed_at: str) -> dict:
    layers = []
    for name in ("gateway", "internet", "dns", "service"):
        series = result.layers.get(name, [])
        attempts = sum(s.sent for s in series)
        failed = sum(s.sent - len(s.rtts) for s in series)
        known = [s.p95 for s in series if s.p95 is not None and math.isfinite(s.p95)]
        if not attempts:
            status = "unknown"
        elif result.statuses.get(name) in ("down", "degraded"):
            status = "attention"
        elif not series or any(not s.sent for s in series) or result.statuses.get(name) != "ok":
            status = "unknown"
        else:
            status = "ok"
        layers.append({"id": name, "status": status, "p95Ms": max(known) if known else None,
                       "attempts": attempts, "failed": failed})
    wifi = {"available": False, "status": "unknown", "signalPct": None}
    if result.wifi is not None:
        signal = result.wifi.signal_pct
        signal = signal if isinstance(signal, (int, float)) and 0 <= signal <= 100 else None
        status = result.statuses.get("wifi")
        wifi = {"available": True,
                "status": "attention" if status in ("down", "degraded") else
                          "ok" if status == "ok" and signal is not None else "unknown",
                "signalPct": signal}
    statuses = [layer["status"] for layer in layers]
    if wifi["available"]:
        statuses.append(wifi["status"])
    overall = "attention" if "attention" in statuses else "unknown" if "unknown" in statuses else "ok"
    return {"scope": "server-host", "observedAt": observed_at, "overall": overall,
            "layers": layers, "wifi": wifi, "historySaved": False,
            "p95Basis": "maximum-target-p95", "probeCount": 3}


def collect(data_dir: Path) -> dict:
    result = run_check(count=3)
    observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    summary = summarize(result, observed_at)
    try:
        with closing(store.connect(data_dir / "home.sqlite")) as db:
            store.save_check(db, observed_at, result)
            # Serialize snapshot publication with scheduled writers, matching CLI.
            db.execute("begin immediate")
            try:
                snapshot = dashboard.from_connection(db)
                dashboard.atomic_export(snapshot, data_dir / "observations.json")
                db.commit()
            except Exception:
                db.rollback()
                raise
        summary["historySaved"] = True
    except Exception:
        # Real probe results are still useful if history storage is unavailable.
        # Do not expose raw exception text, local paths, addresses or identifiers.
        pass
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = collect(args.data_dir)
    except Exception:
        print(json.dumps({"errorCode": "probe-failed"}))
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
