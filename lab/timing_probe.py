#!/usr/bin/env python3
"""Read-only guest timing probe, run before/after traffic rather than alongside it."""
import json
from pathlib import Path
import statistics
import time

started = time.time()
samples = []
for _ in range(100):
    tick = time.monotonic()
    time.sleep(0.01)
    samples.append((time.monotonic() - tick) * 1000)
ordered = sorted(samples)
sources = {}
for name in ("current_clocksource", "available_clocksource"):
    source = Path("/sys/devices/system/clocksource/clocksource0") / name
    sources[name] = source.read_text().strip() if source.exists() else None
print(json.dumps({"started_at_unix": started, "ended_at_unix": time.time(),
    "requested_sleep_ms": 10, "count": len(samples), "elapsed_ms": samples,
    "p50_ms": statistics.median(samples), "p95_ms": ordered[94],
    "max_ms": max(samples), "clocksource": sources}, indent=2))
