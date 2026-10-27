"""Compare ICMP observations along a traced route, without claiming an exact fault.

Hop replies measure control-plane response and a return path, not just packet
forwarding. Persistent increases can suggest a region to investigate, but do
not prove ownership, a particular link's delay, or forwarding packet loss.
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
    """A position/address hint, not a verified owner or physical link."""
    if hop.ip is None:
        return "unknown"
    addr = ipaddress.ip_address(hop.ip)
    if hop.index == 1 and addr.is_private:
        return "first private hop"
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return "shared-address hop"
    if hop.index <= 3:
        return "early upstream hop"
    return "upstream hop"


def probe_hops(hops: list[Hop], count: int = 10) -> dict[int, Series]:
    """Ping each traced address `count` times in parallel; duration depends on replies."""
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
    effective_ms: float | None  # suffix-minimum ICMP RTT comparison, not forwarding latency
    added_ms: float | None  # difference from the previous answering hop's suffix minimum
    note: str


@dataclass(frozen=True)
class PathVerdict:
    rows: list[HopReport]
    biggest_step: HopReport | None  # largest observed suffix-minimum step
    loss_at: HopReport | None  # first sustained >5% probe-failure observation
    text: str
    destination_status: str = "unconfirmed"  # replied, no_ping_reply, not_traced, unconfirmed


def _effective(values: list[float]) -> list[float]:
    """Suffix minimum of replying hops, an ICMP comparison heuristic.

    This suppresses isolated high replies. Different return paths and control-plane
    response behavior mean the result is not a physical link-delay decomposition.
    """
    out, low = [], float("inf")
    for v in reversed(values):
        low = min(low, v)
        out.append(low)
    return out[::-1]


LIMITATIONS = ("These are ICMP observations; control-plane response, asymmetric return paths, "
               "silent hops and route changes limit link/owner and forwarding-loss inference.")


def analyze(hops: list[Hop], series: dict[int, Series], target: str | None = None) -> PathVerdict:
    """Confirm a destination only by a supplied literal IP and successful echo replies.

    Hostnames are deliberately not resolved here: another DNS lookup could select a
    different endpoint from the trace. Existing callers may omit target, in which
    case the last replying hop is never presented as a confirmed destination.
    """
    try:
        destination = ipaddress.ip_address(target) if target else None
    except ValueError:
        destination = None
    dest_hop = next((h for h in hops if h.ip and destination is not None
                     and ipaddress.ip_address(h.ip) == destination), None)
    dest_series = series.get(dest_hop.index) if dest_hop else None
    dest_status = ("unconfirmed" if destination is None else "not_traced" if dest_hop is None
                   else "replied" if dest_series and dest_series.p50 is not None else "no_ping_reply")
    if dest_hop:
        hops = [h for h in hops if h.index <= dest_hop.index]
    answered = [(h, series[h.index]) for h in hops if h.index in series and series[h.index].p50 is not None]
    if not answered:
        rows = [HopReport(h, segment(h), series.get(h.index), None, None, "no reply") for h in hops]
        return PathVerdict(rows, None, None, "No hop answered pings; can't analyze the path. " + LIMITATIONS,
                           dest_status)

    eff_lat = _effective([s.p50 for _, s in answered])
    eff_loss = _effective([s.loss_pct for _, s in answered])
    by_index: dict[int, HopReport] = {}
    biggest = loss_at = None
    prev_lat, prev_loss = 0.0, 0.0
    for (h, s), lat, loss in zip(answered, eff_lat, eff_loss):
        notes = []
        if s.p50 - lat >= RISE_MS:
            notes.append(f"higher ICMP RTT only here (+{s.p50 - lat:.0f} ms); control-plane response is one possible reason")
        starts_loss = loss > LOSS_PCT and prev_loss <= LOSS_PCT
        if starts_loss:
            notes.append("probe failures exceed 5% here and at later replying hops; forwarding loss is unconfirmed")
        elif s.loss_pct > LOSS_PCT and loss <= LOSS_PCT:
            notes.append("probe failures only here; ICMP rate limiting is one possible reason")
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
                    else "no traceroute reply; this hop's forwarding behavior is unknown")
            rows.append(HopReport(h, segment(h), series.get(h.index), None, None, note))

    last_hop, last_series = answered[-1]
    if dest_status == "replied":
        text = (f"The confirmed destination replied to ICMP probes with median {dest_series.p50:.0f} ms "
                f"and {dest_series.loss_pct:.0f}% probe failures.")
    else:
        reason = {"unconfirmed": "Destination identity was not confirmed",
                  "not_traced": "The requested destination was not observed in the trace",
                  "no_ping_reply": "The destination appeared in the trace but did not answer echo probes"}[dest_status]
        text = f"{reason}; last replying hop {last_hop.index} has median ICMP RTT {last_series.p50:.0f} ms."
    text += (f" The largest observed comparison step is at hop {biggest.hop.index} "
             f"({biggest.segment}): +{biggest.added_ms:.0f} ms; this does not identify an exact link or owner.")
    if loss_at:
        text += f" Probe failures above 5% persist across replying hops from hop {loss_at.hop.index}."
    else:
        text += " No sustained >5% probe-failure pattern was observed across replying hops."
    return PathVerdict(rows, biggest, loss_at, text + " " + LIMITATIONS, dest_status)
