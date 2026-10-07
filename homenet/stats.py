"""Summaries and verdicts. Pure functions, so every threshold is tested."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class Series:
    target: str
    sent: int = 0
    rtts: list[float] = field(default_factory=list)  # successful samples, in send order

    def add(self, ms: float | None) -> None:
        self.sent += 1
        if ms is not None:
            self.rtts.append(ms)

    @property
    def loss_pct(self) -> float:
        return 100.0 * (self.sent - len(self.rtts)) / self.sent if self.sent else 100.0

    def pct(self, p: float) -> float | None:
        """Nearest-rank percentile."""
        if not self.rtts:
            return None
        s = sorted(self.rtts)
        return s[max(0, -(-int(p) * len(s) // 100) - 1)]

    @property
    def p50(self) -> float | None:
        return self.pct(50)

    @property
    def p95(self) -> float | None:
        return self.pct(95)

    @property
    def jitter(self) -> float | None:
        """Mean absolute difference between consecutive samples."""
        if len(self.rtts) < 2:
            return None
        return statistics.fmean(abs(b - a) for a, b in zip(self.rtts, self.rtts[1:]))


# --- Layered diagnosis ----------------------------------------------------------

LAYERS = ("wifi", "gateway", "internet", "dns", "service")
FIXES = {
    "wifi": "Weak Wi-Fi: move closer to the router, or switch to 5 GHz / a cable.",
    "gateway": "The local network is slow or dropping packets: Wi-Fi interference or the router.",
    "internet": "The router is fine but public IPs are slow or unreachable: likely the ISP.",
    "dns": "IPs work but names resolve slowly or not at all: try another DNS server.",
    "service": "The network is fine; that service itself is slow or down.",
}
MAX_LOSS_PCT = 5.0
MAX_P95_MS = {"gateway": 30.0, "internet": 120.0, "dns": 200.0, "service": 250.0}
MIN_SIGNAL_PCT = 50  # Windows' signal quality; about -75 dBm


def layer_status(layer: str, series: list[Series]) -> str:
    if not series or all(not s.rtts for s in series):
        return "down"
    for s in series:
        if s.loss_pct > MAX_LOSS_PCT or (s.p95 or 0) > MAX_P95_MS[layer]:
            return "degraded"
    return "ok"


def wifi_status(signal_pct: int | None, connected: bool) -> str:
    if not connected:
        return "down"
    if signal_pct is not None and signal_pct < MIN_SIGNAL_PCT:
        return "degraded"
    return "ok"


def diagnose(statuses: dict[str, str]) -> tuple[str, str | None]:
    """(overall, layer at fault): the lowest layer that isn't ok."""
    for layer in LAYERS:
        st = statuses.get(layer)
        if st and st != "ok":
            return st, layer
    return "ok", None


# --- Bufferbloat ----------------------------------------------------------------

# How much a link's latency grows under load, in ms of p95 over the idle p50.
# These bands are this project's own, tied to calls: tens of ms go unnoticed,
# around 100 ms of extra delay is where conversation starts to feel laggy.
BLOAT_BANDS = [(30, "A", "no noticeable bufferbloat"),
               (100, "B", "mild: calls may feel slightly delayed"),
               (300, "C", "significant: calls will stutter under load"),
               (float("inf"), "D", "severe: the queue dominates latency under load")]


def bloat_grade(idle_p50: float | None, loaded_p95: float | None) -> tuple[str, float | None, str]:
    """(grade, added ms, meaning). Grade '?' when either side has no samples."""
    if idle_p50 is None or loaded_p95 is None:
        return "?", None, "not enough samples"
    added = max(0.0, loaded_p95 - idle_p50)
    for limit, grade, meaning in BLOAT_BANDS:
        if added < limit:
            return grade, added, meaning
    raise AssertionError("unreachable")
