"""Raw measurements on Windows or Linux, standard library only.

Every function returns milliseconds or a parsed record, or None on failure;
nothing here decides what is "good". Wi-Fi parsing keeps radio facts only:
never the network name (SSID) or any MAC address.
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import time
from dataclasses import dataclass

WINDOWS = platform.system() == "Windows"


def _run(cmd: list[str], timeout: float) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace").stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


# --- Wi-Fi --------------------------------------------------------------------


@dataclass(frozen=True)
class WifiLink:
    state: str
    band: str | None  # "2.4 GHz", "5 GHz", "6 GHz"
    channel: int | None
    radio: str | None  # e.g. "802.11ax"
    signal_pct: int | None
    rssi_dbm: int | None
    rx_mbps: float | None  # negotiated link rate, not throughput
    tx_mbps: float | None


_FIELDS = {
    "state": "State",
    "band": "Band",
    "channel": "Channel",
    "radio": "Radio type",
    "signal": "Signal",
    "rssi": "Rssi",
    "rx": "Receive rate (Mbps)",
    "tx": "Transmit rate (Mbps)",
}


def parse_wifi(output: str) -> WifiLink | None:
    """Parse `netsh wlan show interfaces` (English Windows). None if no Wi-Fi interface."""
    raw: dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        for name, label in _FIELDS.items():
            if key == label and name not in raw:  # first interface only
                raw[name] = value
    if "state" not in raw:
        return None

    def num(name: str, cast=float):
        m = re.search(r"-?\d+(?:\.\d+)?", raw.get(name, ""))
        return cast(float(m.group())) if m else None

    return WifiLink(
        state=raw["state"],
        band=raw.get("band"),
        channel=num("channel", int),
        radio=raw.get("radio"),
        signal_pct=num("signal", int),
        rssi_dbm=num("rssi", int),
        rx_mbps=num("rx"),
        tx_mbps=num("tx"),
    )


def wifi_link() -> WifiLink | None:
    if not WINDOWS:
        return None  # Linux would read `iw dev <if> link`; not needed on this machine yet
    return parse_wifi(_run(["netsh", "wlan", "show", "interfaces"], timeout=10))


# --- Latency ------------------------------------------------------------------

_RTT = re.compile(r"[=<]\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)


def parse_ping(output: str) -> float | None:
    """RTT from one ping's output, None if no reply. Reply lines always carry a TTL."""
    for line in output.splitlines():
        if "ttl" in line.lower():
            m = _RTT.search(line)
            if m:
                return float(m.group(1))
    return None


def ping_once(host: str, timeout_s: float = 1.0) -> float | None:
    if WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), host]
    return parse_ping(_run(cmd, timeout=timeout_s + 2))


def tcp_rtt(host: str, port: int = 443, timeout_s: float = 2.0) -> float | None:
    """Time for a TCP handshake to an already-resolved address: one network round trip.

    Used instead of ping under load because Windows ping can only send once a
    second without admin rights; handshakes can be timed five times a second.
    """
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return (time.perf_counter() - start) * 1000
    except OSError:
        return None


def dns_once(name: str) -> float | None:
    start = time.perf_counter()
    try:
        socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    return (time.perf_counter() - start) * 1000


def https_handshake(host: str, port: int = 443, timeout_s: float = 3.0) -> float | None:
    """Resolve and complete a TCP handshake to a named service."""
    try:
        addr = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)[0][4]
    except OSError:
        return None
    return tcp_rtt(addr[0], port, timeout_s)


_ROUTE_PRINT = re.compile(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
_IP_ROUTE = re.compile(r"default via (\d+\.\d+\.\d+\.\d+)")


def parse_gateway(output: str) -> str | None:
    m = _ROUTE_PRINT.search(output) or _IP_ROUTE.search(output)
    return m.group(1) if m else None


def default_gateway() -> str | None:
    cmd = ["route", "print", "-4", "0.0.0.0"] if WINDOWS else ["ip", "route", "show", "default"]
    return parse_gateway(_run(cmd, timeout=5))
