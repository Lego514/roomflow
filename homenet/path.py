"""Hop-by-hop path analysis, MTR-style: where does latency start, and does it stay?

traceroute lists the routers between here and a destination. Pinging each of
them for a while shows latency and loss per hop. The trap is reading every
spike as a problem: routers answer pings addressed *to themselves* at low
priority, so a single middle hop can look slow or lossy while traffic passing
*through* it is fine. Only what persists to every later hop and to the
destination is real. This module applies exactly that rule, then says where
along the path the latency is added and whether any loss carries through.
"""

from __future__ import annotations

import ipaddress
import re
import threading
from dataclasses import dataclass

from . import measure
from .stats import Series

RISE_MS = 15.0  # a hop this much slower than what carries through is "slow only here"
LOSS_PCT = 5.0

_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}\b", re.IGNORECASE)
_HOP = re.compile(r"^\s*(\d+)\s+(.*)$")


@dataclass(frozen=True)
class Hop:
    index: int
    ip: str | None  # None when the hop never answered ("*")


def parse_traceroute(output: str) -> list[Hop]:
    """Hops from Windows `tracert -d` or Linux `traceroute -n` output."""
    hops = []
    for line in output.splitlines():
        m = _HOP.match(line)
        if not m:
            continue
        ip = _IP.search(m.group(2))
        hops.append(Hop(int(m.group(1)), ip.group(0) if ip else None))
    return hops


def traceroute(target: str, max_hops: int = 20) -> list[Hop]:
    if measure.WINDOWS:
        cmd = ["tracert", "-d", "-w", "1000", "-h", str(max_hops), target]
    else:
        cmd = ["traceroute", "-n", "-w", "1", "-m", str(max_hops), target]
    return parse_traceroute(measure._run(cmd, timeout=max_hops * 4 + 10))


def segment(hop: Hop) -> str:
    """Which part of the path a hop belongs to, from its position and address."""
    if hop.ip is None:
        return "unknown"
    addr = ipaddress.ip_address(hop.ip)
    if hop.index == 1 and addr.is_private:
        return "home router"
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return "ISP (carrier NAT)"
    if hop.index == 2 or (hop.index <= 3 and addr.is_private):
        return "ISP access line"
    return "ISP / internet"


def probe_hops(hops: list[Hop], count: int = 10) -> dict[int, Series]:
    """Ping every answering hop `count` times, all hops in parallel (about `count` seconds)."""
    results: dict[int, Series] = {}

    def run(hop: Hop) -> None:
        s = Series(hop.ip or "*")
        for _ in range(count):
            s.add(measure.ping_once(hop.ip))
        results[hop.index] = s

    threads = [threading.Thread(target=run, args=(h,), daemon=True) for h in hops if h.ip]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=count * 3 + 10)
    return results


@dataclass(frozen=True)
class HopReport:
    hop: Hop
    segment: str
    series: Series | None
    effective_ms: float | None  # latency that really carries through this hop
    added_ms: float | None  # how much of the path's latency is added between the previous hop and this one
    note: str


@dataclass(frozen=True)
class PathVerdict:
    rows: list[HopReport]
    biggest_step: HopReport | None  # where the largest share of latency is added
    loss_at: HopReport | None  # first hop where loss starts and carries through to the destination
    text: str


def _effective(values: list[float]) -> list[float]:
    """Running minimum from the destination backwards.

    A packet passing through hop i also passes through every later hop, so what
    traffic through hop i really experiences can't exceed what any later hop
    shows. The minimum over hop i and everything after it is the value that
    carries through; anything a hop shows above that is about pings to itself.
    """
    out, low = [], float("inf")
    for v in reversed(values):
        low = min(low, v)
        out.append(low)
    return out[::-1]


def analyze(hops: list[Hop], series: dict[int, Series]) -> PathVerdict:
    answered = [(h, series[h.index]) for h in hops if h.index in series and series[h.index].p50 is not None]
    if not answered:
        rows = [HopReport(h, segment(h), series.get(h.index), None, None, "no reply") for h in hops]
        return PathVerdict(rows, None, None, "No hop answered pings; can't analyze the path.")

    eff_lat = _effective([s.p50 for _, s in answered])
    eff_loss = _effective([s.loss_pct for _, s in answered])
    by_index: dict[int, HopReport] = {}
    biggest = loss_at = None
    prev_lat, prev_loss = 0.0, 0.0
    for (h, s), lat, loss in zip(answered, eff_lat, eff_loss):
        notes = []
        if s.p50 - lat >= RISE_MS:
            notes.append(f"slow only here (+{s.p50 - lat:.0f} ms): routers answer pings to themselves at low priority")
        starts_loss = loss > LOSS_PCT and prev_loss <= LOSS_PCT
        if starts_loss:
            notes.append("loss starts here and carries through to the destination")
        elif s.loss_pct > LOSS_PCT and loss <= LOSS_PCT:
            notes.append("loss only here: pings to the router itself are rate-limited")
        row = HopReport(h, segment(h), s, lat, lat - prev_lat, "; ".join(notes))
        by_index[h.index] = row
        if biggest is None or row.added_ms > biggest.added_ms:
            biggest = row
        if starts_loss and loss_at is None:
            loss_at = row
        prev_lat, prev_loss = lat, loss

    rows = []
    for h in hops:
        if h.index in by_index:
            rows.append(by_index[h.index])
        else:
            note = ("answers traceroute but not pings" if h.ip
                    else "silent: this router doesn't reply to probes (normal, traffic still passes)")
            rows.append(HopReport(h, segment(h), series.get(h.index), None, None, note))

    total = eff_lat[-1]
    text = (f"The destination answers in {total:.0f} ms (median). The largest share is added at hop "
            f"{biggest.hop.index} ({biggest.segment}): +{biggest.added_ms:.0f} ms.")
    if loss_at:
        text += (f" Loss starts at hop {loss_at.hop.index} ({loss_at.segment}) and reaches the destination: "
                 f"{eff_loss[-1]:.0f}% end to end.")
    else:
        text += " No loss carries through to the destination."
    return PathVerdict(rows, biggest, loss_at, text)
