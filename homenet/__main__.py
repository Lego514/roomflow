"""Command line.

    python -m homenet check            Wi-Fi + latency layer by layer, with a verdict
    python -m homenet wifi             how crowded your Wi-Fi channel is, and a quieter one
    python -m homenet trace            hop by hop: where latency is added, whether loss carries through
    python -m homenet dns              your resolvers vs 1.1.1.1 / 8.8.8.8 / 9.9.9.9, cached and uncached
    python -m homenet ipv6             the same services over IPv4 and IPv6
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
    return 0


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
    sub.add_parser("wifi").set_defaults(fn=cmd_wifi)
    t = sub.add_parser("trace")
    t.add_argument("--target", default="1.1.1.1")
    t.add_argument("--count", type=int, default=10)
    t.set_defaults(fn=cmd_trace)
    d = sub.add_parser("dns")
    d.add_argument("--rounds", type=int, default=5)
    d.add_argument("--system", type=int, default=4, help="how many of the system's resolvers to include")
    d.set_defaults(fn=cmd_dns)
    v = sub.add_parser("ipv6")
    v.add_argument("--count", type=int, default=10)
    v.set_defaults(fn=cmd_ipv6)
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
