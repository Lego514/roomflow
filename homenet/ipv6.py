"""Does this connection have working IPv6, and is it faster or slower than IPv4?

Many ISPs (Comcast among them) route IPv6 differently from IPv4, so the same
service can be a few milliseconds closer one way. Applications prefer IPv6
when it works ("Happy Eyeballs"), so a slow IPv6 path quietly makes calls slower.
Each target is reached over both protocols with TCP handshakes; the median of
each is compared.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from . import measure
from .stats import Series

# Fixed addresses where both families are known, plus names resolved at run time.
FIXED = [("Cloudflare", "1.1.1.1", "2606:4700:4700::1111"), ("Google DNS", "8.8.8.8", "2001:4860:4860::8888")]
NAMES = ["zoom.us", "teams.microsoft.com", "www.google.com"]
SAME_MS = 3.0  # differences smaller than this are noise


def resolve(name: str, family: int) -> str | None:
    try:
        return socket.getaddrinfo(name, 443, family, socket.SOCK_STREAM)[0][4][0]
    except OSError:
        return None


@dataclass
class Pair:
    label: str
    v4: Series | None
    v6: Series | None  # None when the target has no IPv6 address

    @property
    def verdict(self) -> str:
        if self.v6 is None:
            return "no IPv6 address"
        if self.v6.p50 is None:
            return "IPv6 fails"
        if self.v4 is None or self.v4.p50 is None:
            return "IPv4 fails"
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
    targets = list(FIXED) + [(n, resolve(n, socket.AF_INET), resolve(n, socket.AF_INET6)) for n in NAMES]
    return [Pair(label, _series(v4, count), _series(v6, count)) for label, v4, v6 in targets]


def summary(pairs: list[Pair]) -> str:
    tested = [p for p in pairs if p.v6 is not None]
    working = [p for p in tested if p.v6 and p.v6.p50 is not None]
    if not tested:
        return "None of the targets has an IPv6 address."
    if not working:
        return "IPv6 doesn't work from here: every IPv6 connection failed. Apps fall back to IPv4 after a delay."
    slower = [p for p in working if p.v4 and p.v4.p50 is not None and p.v6.p50 - p.v4.p50 >= SAME_MS]
    return (f"IPv6 works ({len(working)}/{len(tested)} targets). "
            + (f"It's slower for {', '.join(p.label for p in slower)}." if slower else "It isn't slower than IPv4 for any target."))
