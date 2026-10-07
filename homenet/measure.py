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


@dataclass(frozen=True)
class Bss:
    """One access point heard in a scan: radio facts only, no name or address."""

    band: str | None
    channel: int | None
    signal_pct: int | None
    radio: str | None
    utilization_pct: int | None  # from Bss Load, when the AP advertises it
    stations: int | None
    own: bool = False  # broadcast by the router this machine is connected to


_BSSID_LINE = re.compile(r"^\s*BSSID \d+\s*:\s*(\S+)")  # "BSSID 3 : ..." starts a record
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def same_radio(a: str | None, b: str | None) -> bool:
    """Do two BSSIDs belong to the same router? Compared in memory, never stored.

    A router that broadcasts several networks (main, guest, another band) derives
    their BSSIDs from one base address: it changes the last byte and often sets
    the "locally administered" bit in the first byte. So the middle four bytes
    identify the hardware. A heuristic, not a guarantee.
    """
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    if not (_MAC.match(a) and _MAC.match(b)):
        return False
    return a.split(":")[1:5] == b.split(":")[1:5]
_UTIL = re.compile(r"\((\d+)\s*%\)")


def parse_bss(output: str, own_bssid: str | None = None) -> list[Bss]:
    """Parse `netsh wlan show networks mode=bssid` into access points.

    SSIDs are never read. Each BSSID is looked at once, to mark access points
    that belong to the router this machine is connected to (`own_bssid`), and
    then dropped; the returned records hold no address. "Colocated APs" lines
    (which also carry addresses) match no field below and are ignored.
    """
    records: list[dict[str, str]] = []
    for line in output.splitlines():
        m = _BSSID_LINE.match(line)
        if m:
            records.append({"own": "1" if same_radio(m.group(1), own_bssid) else ""})
            continue
        if not records:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key in ("Signal", "Radio type", "Band", "Channel", "Channel Utilization", "Connected Stations"):
            records[-1].setdefault(key, value)

    def num(rec: dict[str, str], key: str) -> int | None:
        m = re.search(r"\d+", rec.get(key, ""))
        return int(m.group()) if m else None

    out = []
    for rec in records:
        util = _UTIL.search(rec.get("Channel Utilization", ""))
        out.append(
            Bss(
                band=rec.get("Band"),
                channel=num(rec, "Channel"),
                signal_pct=num(rec, "Signal"),
                radio=rec.get("Radio type"),
                utilization_pct=int(util.group(1)) if util else None,
                stations=num(rec, "Connected Stations"),
                own=bool(rec.get("own")),
            )
        )
    return out


def connected_bssid(output: str) -> str | None:
    """The connected access point's BSSID from `netsh wlan show interfaces`. Kept in memory only."""
    for line in output.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("AP BSSID", "BSSID"):  # Windows 11 says "AP BSSID"
            return value.strip()
    return None


def scan() -> list[Bss]:
    """Access points currently heard, with this machine's own router marked.

    Windows may return the last cached scan rather than a fresh one.
    """
    if not WINDOWS:
        return []
    own = connected_bssid(_run(["netsh", "wlan", "show", "interfaces"], timeout=10))
    return parse_bss(_run(["netsh", "wlan", "show", "networks", "mode=bssid"], timeout=20), own)


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
