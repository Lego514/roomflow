"""Probe summaries and observation flags; thresholds do not establish root causes."""

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
    "wifi": "The Wi-Fi link is disconnected or has a low reported signal; compare with a cable or a closer position.",
    "gateway": "Gateway echo probes are slow or unsuccessful; investigate the local link and gateway response behavior.",
    "internet": "Selected public-IP TCP probes are slow or unsuccessful; compare targets and wired/Wi-Fi paths before assigning a cause.",
    "dns": "Selected name lookups are slow or unsuccessful; compare resolver results and distinguish DNS from connectivity failures.",
    "service": "TCP connection probes to selected service addresses are slow or unsuccessful; this does not establish a service outage or call quality.",
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
    """(status, first flagged observation layer), not a root-cause diagnosis."""
    for layer in LAYERS:
        st = statuses.get(layer)
        if st and st != "ok":
            return st, layer
    return "ok", None


# --- Bufferbloat ----------------------------------------------------------------

# How much a link's latency grows under load, in ms of p95 over the idle p50.
# Project-specific latency bands, not standardized grades or call-quality scores.
BLOAT_BANDS = [(30, "A", "small added probe latency under load (<30 ms)"),
               (100, "B", "moderate added probe latency under load (30-100 ms)"),
               (300, "C", "high added probe latency under load (100-300 ms)"),
               (float("inf"), "D", "very high added probe latency under load (>=300 ms)")]


def bloat_grade(idle_p50: float | None, loaded_p95: float | None) -> tuple[str, float | None, str]:
    """(grade, added ms, meaning). Grade '?' when either side has no samples."""
    if idle_p50 is None or loaded_p95 is None:
        return "?", None, "not enough samples"
    added = max(0.0, loaded_p95 - idle_p50)
    for limit, grade, meaning in BLOAT_BANDS:
        if added < limit:
            return grade, added, meaning
    raise AssertionError("unreachable")
