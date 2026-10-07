"""Compare DNS resolvers by asking each one directly.

The operating system hides which resolver answered and caches answers, so
timing `getaddrinfo` says little. This module builds DNS queries by hand
(RFC 1035 wire format, standard library only) and sends each one to a chosen
resolver over UDP, timing the answer.

Two kinds of question, because they measure different things:
  - popular names (zoom.us, ...): almost always cached at the resolver, so this
    is mostly the round trip to the resolver itself
  - a random name under example.com: never cached, so the resolver has to walk
    the DNS tree; the answer is NXDOMAIN, which still proves it did the work
"""

from __future__ import annotations

import ipaddress
import os
import socket
import struct
import time
from dataclasses import dataclass

from . import measure
from .stats import Series

PUBLIC_RESOLVERS = {"Cloudflare": "1.1.1.1", "Google": "8.8.8.8", "Quad9": "9.9.9.9"}
POPULAR = ["zoom.us", "teams.microsoft.com", "www.udel.edu", "github.com"]
UNCACHED_PARENT = "example.com"

RCODE_OK, RCODE_NXDOMAIN = 0, 3


def build_query(name: str, qid: int, qtype: int = 1) -> bytes:
    """A standard recursive query for one name (qtype 1 = A record)."""
    header = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)  # flags: RD (recursion desired)
    labels = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.rstrip(".").split("."))
    return header + labels + b"\x00" + struct.pack("!HH", qtype, 1)  # class IN


def parse_reply(data: bytes, qid: int) -> tuple[int, int] | None:
    """(rcode, answer count) if `data` is a response to query `qid`, else None."""
    if len(data) < 12:
        return None
    rid, flags, _, ancount, _, _ = struct.unpack("!HHHHHH", data[:12])
    if rid != qid or not flags & 0x8000:  # wrong id, or not a response
        return None
    return flags & 0x000F, ancount


def query(server: str, name: str, timeout_s: float = 2.0, expect_nx: bool = False) -> float | None:
    """Milliseconds until `server` answers `name`, or None on timeout or a wrong answer."""
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    qid = int.from_bytes(os.urandom(2), "big")
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        start = time.perf_counter()
        try:
            sock.sendto(build_query(name, qid), (server, 53))
            while True:
                data, _ = sock.recvfrom(4096)
                reply = parse_reply(data, qid)
                if reply is not None:
                    break
        except OSError:
            return None
        elapsed = (time.perf_counter() - start) * 1000
    rcode, ancount = reply
    if expect_nx:
        return elapsed if rcode in (RCODE_OK, RCODE_NXDOMAIN) else None
    return elapsed if rcode == RCODE_OK and ancount > 0 else None


# --- Which resolvers is this machine using? ------------------------------------------


def _field_values(lines: list[str], name: str) -> list[str]:
    """Values of one `ipconfig /all` field, including its continuation lines.

    A field looks like "   DNS Servers . . . : first" followed by lines that
    hold only a value. The next field starts at the next line containing " : ".
    """
    for i, line in enumerate(lines):
        if line.strip().startswith(name):
            values = [line.split(" : ", 1)[1].strip()] if " : " in line else []
            for nxt in lines[i + 1:]:
                if " : " in nxt or not nxt.strip():
                    break
                values.append(nxt.strip())
            return values
    return []


def _ips(values: list[str]) -> list[str]:
    out = []
    for v in values:
        try:
            out.append(str(ipaddress.ip_address(v.split("%")[0])))
        except ValueError:
            pass
    return out


def parse_ipconfig_dns(output: str) -> list[str]:
    """DNS servers of the adapter that has an IPv4 default gateway, from `ipconfig /all`."""
    adapters: list[list[str]] = []
    for line in output.splitlines():
        if line and not line[0].isspace():
            adapters.append([])
        elif adapters:
            adapters[-1].append(line)
    for lines in adapters:
        gateways = _ips(_field_values(lines, "Default Gateway"))
        if any(ipaddress.ip_address(g).version == 4 for g in gateways):
            return _ips(_field_values(lines, "DNS Servers"))
    return []


def system_resolvers() -> list[str]:
    if measure.WINDOWS:
        return parse_ipconfig_dns(measure._run(["ipconfig", "/all"], timeout=10))
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            return [l.split()[1] for l in f if l.startswith("nameserver")]
    except OSError:
        return []


# --- Comparison ----------------------------------------------------------------------


@dataclass
class ResolverResult:
    label: str
    server: str
    cached: Series
    uncached: Series


def compare(resolvers: dict[str, str], rounds: int = 5) -> list[ResolverResult]:
    out = []
    for label, server in resolvers.items():
        cached, uncached = Series(server), Series(server)
        for _ in range(rounds):
            for name in POPULAR:
                cached.add(query(server, name))
            uncached.add(query(server, f"rf-{os.urandom(6).hex()}.{UNCACHED_PARENT}", timeout_s=3, expect_nx=True))
        out.append(ResolverResult(label, server, cached, uncached))
    return out


TIE_MS = 5.0  # cached medians closer than this are a tie at a few dozen queries


def tied_with_best(ranked: list[ResolverResult]) -> list[ResolverResult]:
    """Resolvers whose cached median is within TIE_MS of the fastest (input already ranked)."""
    if not ranked or ranked[0].cached.p50 is None:
        return []
    best = ranked[0].cached.p50
    return [r for r in ranked if r.cached.p50 is not None and r.cached.p50 - best < TIE_MS]


def rank(results: list[ResolverResult]) -> list[ResolverResult]:
    """Fastest first by cached median (what everyday lookups feel like); unanswered last."""
    return sorted(results, key=lambda r: (r.cached.p50 is None, r.cached.p50 or 0, r.uncached.p50 or 0))
