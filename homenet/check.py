"""One quick health check of the home connection, bottom-up."""

from __future__ import annotations

from dataclasses import dataclass

from . import measure
from .stats import Series, diagnose, layer_status, wifi_status

INTERNET_IPS = ["1.1.1.1", "8.8.8.8"]
DNS_NAMES = ["www.udel.edu", "zoom.us"]
SERVICES = ["zoom.us", "teams.microsoft.com"]  # where calls actually go


@dataclass
class CheckResult:
    wifi: measure.WifiLink | None
    layers: dict[str, list[Series]]
    statuses: dict[str, str]
    verdict: tuple[str, str | None]


def _collect(target: str, fn, count: int) -> Series:
    s = Series(target)
    for _ in range(count):
        s.add(fn())
    return s


def run_check(count: int = 10) -> CheckResult:
    wifi = measure.wifi_link()
    gw = measure.default_gateway()
    layers = {
        "gateway": [_collect(gw, lambda: measure.ping_once(gw), count)] if gw else [],
        "internet": [_collect(ip, lambda ip=ip: measure.tcp_rtt(ip, 443), count) for ip in INTERNET_IPS],
        "dns": [_collect(n, lambda n=n: measure.dns_once(n), max(3, count // 3)) for n in DNS_NAMES],
        "service": [_collect(h, lambda h=h: measure.https_handshake(h), max(3, count // 3)) for h in SERVICES],
    }
    statuses = {name: layer_status(name, series) for name, series in layers.items()}
    if wifi is not None:
        statuses = {"wifi": wifi_status(wifi.signal_pct, wifi.state.lower() == "connected"), **statuses}
    return CheckResult(wifi, layers, statuses, diagnose(statuses))
