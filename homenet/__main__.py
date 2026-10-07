"""Command line.

    python -m homenet check            Wi-Fi + latency layer by layer, with a verdict
    python -m homenet bloat            bufferbloat test (uses data: ~10 s each way at full speed)
    python -m homenet watch --every 300   run `check` every 5 minutes
    python -m homenet report           history by hour of day
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .check import run_check
from .load import bufferbloat
from .stats import FIXES

DB = Path(__file__).resolve().parent.parent / "data" / "home.sqlite"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fmt(v: float | None, digits: int = 1) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def print_check(r) -> None:
    w = r.wifi
    if w:
        print(f"wifi      {w.state}, {w.band}, channel {w.channel}, {w.radio}, signal {w.signal_pct}% "
              f"({w.rssi_dbm} dBm), link {fmt(w.rx_mbps, 0)}/{fmt(w.tx_mbps, 0)} Mbps  [{r.statuses.get('wifi')}]")
    print(f"{'layer':<9} {'target':<22} {'loss%':>6} {'p50':>7} {'p95':>7} {'jitter':>7}  status")
    for layer, series in r.layers.items():
        for s in series:
            target = "(router)" if layer == "gateway" else s.target
            print(f"{layer:<9} {target:<22} {s.loss_pct:>6.1f} {fmt(s.p50):>7} {fmt(s.p95):>7} {fmt(s.jitter):>7}  "
                  f"{r.statuses[layer]}")
    status, layer = r.verdict
    print("\nverdict: all layers ok" if status == "ok" else f"\nverdict: {layer} {status}. {FIXES[layer]}")


def cmd_check(args) -> int:
    r = run_check(args.count)
    print_check(r)
    with store.connect(DB) as db:
        store.save_check(db, now(), r)
    return 0 if r.verdict[0] == "ok" else 1


def cmd_bloat(args) -> int:
    print(f"measuring idle, then download, then upload, {args.seconds:.0f} s each...")
    r = bufferbloat(args.seconds)
    print(f"\n{'phase':<9} {'Mbps':>7} {'internet p50':>13} {'internet p95':>13} {'router p95':>11}  grade")
    for phase in (r.idle, r.download, r.upload):
        grade = ""
        if phase is not r.idle:
            g, added, meaning = r.grade(phase)
            grade = f"{g}  +{fmt(added, 0)} ms ({meaning})"
        mbps = "" if phase is r.idle else fmt(phase.mbps)
        print(f"{phase.name:<9} {mbps:>7} {fmt(phase.internet.p50):>13} {fmt(phase.internet.p95):>13} "
              f"{fmt(phase.gateway.p95):>11}  {grade}")
    with store.connect(DB) as db:
        store.save_bloat(db, now(), r)
    return 0


def cmd_watch(args) -> int:
    while True:
        try:
            r = run_check(args.count)
            with store.connect(DB) as db:
                store.save_check(db, now(), r)
            status, layer = r.verdict
            print(f"[{datetime.now():%H:%M}] {status}{'' if layer is None else ' at ' + layer}", flush=True)
        except Exception as e:  # keep watching through a transient failure
            print(f"[{datetime.now():%H:%M}] check failed: {e}", file=sys.stderr, flush=True)
        time.sleep(args.every)


def cmd_report(args) -> int:
    with store.connect(DB) as db:
        rows = store.hourly(db)
    if not rows:
        print("no checks yet: run `python -m homenet check` or `watch` first")
        return 0
    print(f"{'hour':>4} {'checks':>6} {'internet p95':>13} {'worst p95':>10} {'loss%':>6}")
    for hour, checks, p95, worst, loss in rows:
        print(f"{hour:>4} {checks:>6} {fmt(p95):>13} {fmt(worst):>10} {fmt(loss, 2):>6}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homenet")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--count", type=int, default=10)
    c.set_defaults(fn=cmd_check)
    b = sub.add_parser("bloat")
    b.add_argument("--seconds", type=float, default=10)
    b.set_defaults(fn=cmd_bloat)
    w = sub.add_parser("watch")
    w.add_argument("--every", type=int, default=300)
    w.add_argument("--count", type=int, default=5)
    w.set_defaults(fn=cmd_watch)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
