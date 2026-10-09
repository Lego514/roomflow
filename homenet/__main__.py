"""Command line.

    python -m homenet check            Wi-Fi + latency layer by layer, with a verdict
    python -m homenet wifi             how crowded your Wi-Fi channel is, and a quieter one
    python -m homenet trace            hop by hop: where latency is added, whether loss carries through
    python -m homenet dns              your resolvers vs 1.1.1.1 / 8.8.8.8 / 9.9.9.9, cached and uncached
    python -m homenet ipv6             the same services over IPv4 and IPv6
    python -m homenet path             trace, then ipv6 (what the schedule runs every 2 hours)
    python -m homenet bloat            bufferbloat test (uses data: ~10 s each way at full speed)
    python -m homenet capacity         available download/upload right now (~5 s each way at full speed)
    python -m homenet watch --every 300   run `check` every 5 minutes
    python -m homenet report           what the scheduled runs found: by hour, bufferbloat, path, IPv6

Scheduled runs (scripts/schedule-homenet.ps1) add --log data/homenet.log, which
appends output and errors to that file instead of a console.
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


BLOAT_LOCK = DB.parent / ".bloat-running"  # held by bloat and capacity, which both saturate the link


def bloat_running() -> bool:
    """A load test saturates the link; a check during it would record the load, not the network."""
    try:
        return time.time() - BLOAT_LOCK.stat().st_mtime < 180
    except OSError:
        return False


def cmd_check(args) -> int:
    if getattr(args, "skip_during_bloat", False) and bloat_running():
        print("skipped: a bufferbloat test is running")
        return 0
    r = run_check(args.count)
    print_check(r)
    with store.connect(DB) as db:
        store.save_check(db, now(), r)
    return 0 if r.verdict[0] == "ok" else 1


def cmd_wifi(args) -> int:
    from . import channels, measure

    link = measure.wifi_link()
    aps = measure.scan()
    if not aps:
        print("no scan results (is Wi-Fi on? Windows may need location access for scans)")
        return 1
    try:
        advice = channels.advise(aps, link and link.band, link and link.channel)
        stats = channels.count_by_channel(channels.neighbors(aps))
    except NotImplementedError as e:
        print(f"{e}\nOnce it's written, this command shows the channel table.")
        return 2
    own = len(aps) - len(channels.neighbors(aps))
    print(f"heard {len(aps)} access points ({own} from your own router, left out below); "
          f"you are on {link.band} channel {link.channel}"
          + (f", which a neighbor reports as {advice.my_utilization}% busy" if advice.my_utilization is not None else ""))
    print(f"\n{'5 GHz block':<12} {'neighbors':>9} {'strongest':>10}  note")
    for b in channels.block_loads(stats):
        mine = advice.my_block is not None and b.block == advice.my_block.block
        note = ("<- you" if mine else "") + ("  DFS" if b.dfs else "")
        print(f"{b.block[0]:>3}-{b.block[-1]:<8} {b.count:>9} {b.strongest:>9}%  {note.strip()}")
    print(f"\n{advice.text}")
    return 0


def cmd_trace(args) -> int:
    from . import path

    print(f"tracing the route to {args.target}...")
    hops = path.traceroute(args.target)
    if not hops:
        print("traceroute returned nothing")
        return 1
    print(f"pinging {sum(1 for h in hops if h.ip)} hops {args.count} times each, in parallel...")
    verdict = path.analyze(hops, path.probe_hops(hops, args.count))
    print(f"\n{'hop':>3}  {'segment':<18} {'address':<16} {'loss%':>6} {'p50':>6} {'carries':>8} {'added':>6}  note")
    for r in verdict.rows:
        s = r.series
        addr = r.hop.ip or "*"
        loss = fmt(s.loss_pct) if s else "-"
        p50 = fmt(s.p50) if s else "-"
        added = "" if r.added_ms is None else f"+{r.added_ms:.0f}"
        print(f"{r.hop.index:>3}  {r.segment:<18} {addr:<16} {loss:>6} {p50:>6} {fmt(r.effective_ms):>8} {added:>6}  {r.note}")
    print(f"\n{verdict.text}")
    print("'carries' is the latency that really passes through each hop (lowest of it and every later hop).")
    with store.connect(DB) as db:
        store.save_trace(db, now(), args.target, verdict)
    return 0


def cmd_dns(args) -> int:
    from . import dns

    resolvers = {}
    for i, server in enumerate(dns.system_resolvers()[: args.system], 1):
        resolvers[f"system {i} (IPv{6 if ':' in server else 4})"] = server
    resolvers.update(dns.PUBLIC_RESOLVERS)
    print(f"asking {len(resolvers)} resolvers, {args.rounds} rounds of {len(dns.POPULAR)} popular names + 1 uncached name...")
    results = dns.rank(dns.compare(resolvers, args.rounds))
    print(f"\n{'resolver':<18} {'cached p50':>11} {'cached p95':>11} {'uncached p50':>13} {'failed':>7}")
    for r in results:
        failed = (r.cached.sent - len(r.cached.rtts)) + (r.uncached.sent - len(r.uncached.rtts))
        print(f"{r.label:<18} {fmt(r.cached.p50):>11} {fmt(r.cached.p95):>11} {fmt(r.uncached.p50):>13} {failed:>7}")
    best = results[0]
    tied = dns.tied_with_best(results)
    if len(tied) > 1:
        print(f"\n{len(tied)} resolvers are within {dns.TIE_MS:.0f} ms of the fastest ({', '.join(r.label for r in tied)}): "
              "at this sample size that's a tie, so switching wouldn't change much.")
    else:
        print(f"\nfastest for everyday lookups: {best.label}, by more than {dns.TIE_MS:.0f} ms.")
    print("'uncached' forces a full lookup through the DNS tree: the worst case for a name you haven't visited.")
    return 0


def cmd_ipv6(args) -> int:
    from . import ipv6

    pairs = ipv6.compare(args.count)
    print(f"{'target':<20} {'IPv4 p50':>9} {'IPv6 p50':>9}  verdict")
    for p in pairs:
        v4 = fmt(p.v4.p50) if p.v4 else "-"
        v6 = fmt(p.v6.p50) if p.v6 else "-"
        print(f"{p.label:<20} {v4:>9} {v6:>9}  {p.verdict}")
    print(f"\n{ipv6.summary(pairs)}")
    with store.connect(DB) as db:
        store.save_ipv6(db, now(), pairs)
    return 0


def cmd_path(args) -> int:
    """trace, then ipv6, in one process (one scheduled action, measured one after the other)."""
    args.target = "1.1.1.1"
    code = cmd_trace(args)
    print()
    return cmd_ipv6(args) or code


def cmd_capacity(args) -> int:
    from .load import capacity

    BLOAT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    BLOAT_LOCK.touch()
    try:
        r = capacity(args.seconds)
    finally:
        BLOAT_LOCK.unlink(missing_ok=True)
    print(f"available now: download {fmt(r.download.mbps)} Mbps, upload {fmt(r.upload.mbps)} Mbps")
    print(f"latency while loaded (p50): download {fmt(r.download.internet.p50)} ms, upload {fmt(r.upload.internet.p50)} ms")
    with store.connect(DB) as db:
        store.save_capacity(db, now(), r)
    return 0


def cmd_bloat(args) -> int:
    print(f"measuring idle, then download, then upload, {args.seconds:.0f} s each...")
    BLOAT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    BLOAT_LOCK.touch()
    try:
        r = bufferbloat(args.seconds)
    finally:
        BLOAT_LOCK.unlink(missing_ok=True)
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
        hours = store.hourly(db)
        cap = store.capacity_by_hour(db)
        blo = store.bloat_runs(db)
        v6 = store.ipv6_summary(db)
        tr = store.trace_summary(db)
    if not (hours or blo or v6 or tr or cap):
        print("nothing recorded yet: run a command, or install the schedule (scripts/schedule-homenet.ps1)")
        return 0

    if hours:
        print("Latency to the internet by hour of day (from scheduled checks)")
        print(f"{'hour':>4} {'checks':>6} {'avg p95':>8} {'worst p95':>10} {'loss%':>6}")
        for hour, checks, p95, worst, loss in hours:
            print(f"{hour:>4} {checks:>6} {fmt(p95):>8} {fmt(worst):>10} {fmt(loss, 2):>6}")
    if cap:
        print("\nAvailable throughput by hour of day (what's left for this machine)")
        print(f"{'hour':>4} {'runs':>4} {'down Mbps':>10} {'up Mbps':>8}")
        for hour, runs, down, up in cap:
            print(f"{hour:>4} {runs:>4} {fmt(down):>10} {fmt(up):>8}")
    if blo:
        print("\nBufferbloat runs")
        print(f"{'when':<20} {'down Mbps':>9} {'grade':>5} {'added':>7}   {'up Mbps':>7} {'grade':>5} {'added':>7}")
        for when, dm, dg, da, um, ug, ua in blo:
            print(f"{when:<20} {fmt(dm):>9} {dg or '?':>5} {fmt(da, 0):>7}   {fmt(um):>7} {ug or '?':>5} {fmt(ua, 0):>7}")
    if tr:
        runs, total, seg, times, added = tr
        print(f"\nPath ({runs} traces): median {fmt(total)} ms end to end; the most latency is added at the "
              f"{seg} in {times} of {runs} runs (median +{fmt(added, 0)} ms).")
    if v6:
        print("\nIPv4 vs IPv6 (latency compared only on runs where both answered)")
        print(f"{'target':<20} {'runs':>4} {'both ok':>7} {'IPv4 p50':>9} {'IPv6 p50':>9} {'v6 slower':>9} {'v6 failed':>9}")
        for s in v6:
            print(f"{s.target:<20} {s.runs:>4} {s.paired:>7} {fmt(s.v4_p50):>9} {fmt(s.v6_p50):>9} "
                  f"{s.v6_slower:>9} {s.v6_failed:>9}")
        failing = [s for s in v6 if s.v6_failed]
        if failing:
            print("'v6 failed' counts runs where IPv4 answered and IPv6 didn't; check whether they line up "
                  "with the slow hours above.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homenet")
    parser.add_argument("--log", type=Path, help="append output and errors to this file (for scheduled runs)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--count", type=int, default=10)
    c.add_argument("--skip-during-bloat", action="store_true", help="do nothing while a bloat test runs")
    c.set_defaults(fn=cmd_check)
    sub.add_parser("wifi").set_defaults(fn=cmd_wifi)
    t = sub.add_parser("trace")
    t.add_argument("--target", default="1.1.1.1")
    t.add_argument("--count", type=int, default=10)
    t.set_defaults(fn=cmd_trace)
    d = sub.add_parser("dns")
    d.add_argument("--rounds", type=int, default=5)
    d.add_argument("--system", type=int, default=4, help="how many of the system's resolvers to include")
    d.set_defaults(fn=cmd_dns)
    pa = sub.add_parser("path")
    pa.add_argument("--count", type=int, default=10)
    pa.set_defaults(fn=cmd_path)
    v = sub.add_parser("ipv6")
    v.add_argument("--count", type=int, default=10)
    v.set_defaults(fn=cmd_ipv6)
    cp = sub.add_parser("capacity")
    cp.add_argument("--seconds", type=float, default=3)
    cp.set_defaults(fn=cmd_capacity)
    b = sub.add_parser("bloat")
    b.add_argument("--seconds", type=float, default=10)
    b.set_defaults(fn=cmd_bloat)
    w = sub.add_parser("watch")
    w.add_argument("--every", type=int, default=300)
    w.add_argument("--count", type=int, default=5)
    w.set_defaults(fn=cmd_watch)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = parser.parse_args(argv)
    if args.log is None:
        return args.fn(args)
    return run_logged(args)


def run_logged(args) -> int:
    """Scheduled runs have no console: send output and any traceback to the log file.

    Output is collected in memory and appended in one write at the end. Scheduled
    tasks can overlap (a check every 5 minutes, a path run every 2 hours), and two
    processes appending line by line to one file interleave or overwrite each
    other's lines; a single append per run keeps every run's block intact.
    """
    import io
    import traceback

    buf = io.StringIO()
    sys.stdout = sys.stderr = buf
    print(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {args.cmd}")
    try:
        code = args.fn(args)
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with open(args.log, "a", encoding="utf-8") as log:
        log.write(buf.getvalue())
    return code


if __name__ == "__main__":
    sys.exit(main())
