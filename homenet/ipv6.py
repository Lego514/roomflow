"""Compare selected targets' IPv4/IPv6 TCP probes, separately from name lookup.

These sequential probes do not measure application address racing/fallback,
call-media performance, or availability of every IPv6 destination.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from . import measure
from .stats import Series

# Fixed addresses where both families are known, plus names resolved at run time.
FIXED = [("Cloudflare", "1.1.1.1", "2606:4700:4700::1111"), ("Google DNS", "8.8.8.8", "2001:4860:4860::8888")]
NAMES = ["zoom.us", "teams.microsoft.com", "www.google.com"]
SAME_MS = 3.0  # project-specific reporting tolerance, not a significance test


def resolve(name: str, family: int) -> str | None:
    """Compatibility helper; compare() also retains why an address was unavailable."""
    return _resolve(name, family)[0]


def _resolve(name: str, family: int) -> tuple[str | None, str | None]:
    try:
        addresses = socket.getaddrinfo(name, 443, family, socket.SOCK_STREAM)
        if not addresses:
            return None, "resolver returned no addresses"
        return addresses[0][4][0], None
    except OSError as exc:
        # EAI_NONAME may mean no address, not necessarily a DNS transport fault.
        return None, f"{type(exc).__name__}: {exc}"


@dataclass
class Pair:
    label: str
    v4: Series | None
    v6: Series | None  # None when no probe address was available
    v4_resolution_error: str | None = None
    v6_resolution_error: str | None = None

    @staticmethod
    def _unavailable(family: str, samples: Series | None, error: str | None) -> str | None:
        if error:
            return f"{family} address lookup unavailable ({error})"
        if samples is None:
            return f"no {family} probe address"
        if not samples.sent:
            return f"no {family} TCP probes recorded"
        if samples.p50 is None:
            return f"{family} TCP probes had no successful connections"
        return None

    @property
    def verdict(self) -> str:
        missing = [reason for reason in (self._unavailable("IPv4", self.v4, self.v4_resolution_error),
                                        self._unavailable("IPv6", self.v6, self.v6_resolution_error)) if reason]
        if missing:
            return "; ".join(missing)
        diff = self.v6.p50 - self.v4.p50
        if abs(diff) < SAME_MS:
            return "about the same"
        return f"IPv6 {abs(diff):.0f} ms {'slower' if diff > 0 else 'faster'}"


def _series(addr: str | None, count: int) -> Series | None:
    if addr is None:
        return None
    s = Series(addr)
    for _ in range(count):
        s.add(measure.tcp_rtt(addr, 443))
    return s


def compare(count: int = 10) -> list[Pair]:
    pairs = [Pair(label, _series(v4, count), _series(v6, count)) for label, v4, v6 in FIXED]
    for name in NAMES:
        v4, err4 = _resolve(name, socket.AF_INET)
        v6, err6 = _resolve(name, socket.AF_INET6)
        pairs.append(Pair(name, _series(v4, count), _series(v6, count), err4, err6))
    return pairs


def summary(pairs: list[Pair]) -> str:
    tested = [p for p in pairs if p.v6 is not None and p.v6.sent]
    working = [p for p in tested if p.v6 and p.v6.p50 is not None]
    unavailable = [p.label for p in pairs if p.v6 is None]
    if not tested:
        text = "No IPv6 TCP probe results were recorded for these targets."
    else:
        text = f"IPv6 TCP probes succeeded for {len(working)}/{len(tested)} tested targets."
    if unavailable:
        text += f" IPv6 probe addresses were unavailable for {', '.join(unavailable)}; see the per-target lookup outcomes."
    paired = [p for p in working if p.v4 and p.v4.p50 is not None]
    slower = [p.label for p in paired if p.v6.p50 - p.v4.p50 >= SAME_MS]
    if paired:
        text += (f" Among {len(paired)} paired targets, IPv6 median TCP connect time was at least {SAME_MS:.0f} ms higher for "
                 + (", ".join(slower) if slower else "none") + ".")
    text += " These sequential probes do not establish network-wide IPv6 availability or application fallback behavior."
    return text
