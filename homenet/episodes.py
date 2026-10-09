"""Slow periods: turn a timeline of checks into events with a start, an end and a size.

At home the internet latency doesn't drift; it sits near its normal value, jumps
to a flat plateau for hours, then drops back. A list of those plateaus ("Oct 8,
01:05 to 09:55, 8 h 50 min, 196 ms") is what you can take to a roommate or the
ISP, and what other measurements (capacity, IPv6) can be lined up against.

Rules, all on the per-check internet median:
  - normal is the line's usual latency: the 10th percentile of all checks
  - a check is slow when it is more than SLOW_ABOVE_MS above normal
  - a period starts at the first slow check and ends at the last slow check
    before RECOVER_CHECKS normal checks in a row (one good check inside a
    plateau doesn't end it)
  - a gap in the checks longer than GAP (the laptop asleep) ends a period too;
    it is marked open-ended, since nobody saw it end
  - a period needs MIN_CHECKS slow checks; a single slow check is a spike
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

SLOW_ABOVE_MS = 50.0
RECOVER_CHECKS = 2
MIN_CHECKS = 2
GAP = timedelta(minutes=15)


@dataclass(frozen=True)
class Episode:
    start: datetime  # first slow check
    end: datetime  # last slow check
    checks: int  # slow checks inside
    internet_p50: float  # median of the slow checks' internet latency
    router_p50: float | None  # median of the router latency over the same checks
    open_end: bool  # recording stopped (a gap or the end of the data) while still slow

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def contains(self, when: datetime) -> bool:
        return self.start <= when <= self.end


def median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def normal_latency(rows) -> float | None:
    """10th percentile of the internet latency: what the line does when nothing is wrong."""
    values = sorted(r[2] for r in rows if r[2] is not None)
    if not values:
        return None
    return values[int(len(values) * 0.1)]


def find(rows, normal: float | None = None) -> list[Episode]:
    """rows: (when, router p50, internet p50) per check, in time order."""
    rows = [r for r in rows if r[2] is not None]
    normal = normal_latency(rows) if normal is None else normal
    if normal is None:
        return []
    limit = normal + SLOW_ABOVE_MS
    episodes: list[Episode] = []
    slow: list[tuple] = []  # slow checks of the period in progress
    good_run = 0
    prev: datetime | None = None

    def close(open_end: bool) -> None:
        if len(slow) >= MIN_CHECKS:
            episodes.append(Episode(
                start=slow[0][0], end=slow[-1][0], checks=len(slow),
                internet_p50=median([r[2] for r in slow]),
                router_p50=median([r[1] for r in slow if r[1] is not None]),
                open_end=open_end,
            ))
        slow.clear()

    for row in rows:
        when, _, internet = row
        if slow and prev is not None and when - prev > GAP:
            close(open_end=True)
            good_run = 0
        if internet > limit:
            slow.append(row)
            good_run = 0
        elif slow:
            good_run += 1
            if good_run >= RECOVER_CHECKS:
                close(open_end=False)
        prev = when
    if slow:
        close(open_end=True)
    return episodes


def during(when: datetime, episodes: list[Episode]) -> bool:
    return any(e.contains(when) for e in episodes)


def fmt_duration(d: timedelta) -> str:
    minutes = round(d.total_seconds() / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"
