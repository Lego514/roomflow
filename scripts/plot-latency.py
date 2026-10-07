#!/usr/bin/env python3
"""Draw meeting latency over time per policy, as static light and dark SVGs.

Input: one CI batch directory (results/native-ci/batch). For each policy it
takes the "both" scenario run whose p95 is the median of the repeats, so the
chart shows a typical run rather than the best one, and plots every ping RTT
from the moment traffic starts. Standard library only.

    python3 scripts/plot-latency.py results/native-ci/batch docs/
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

POLICIES = [  # (mode, label) in fixed categorical order
    ("fifo", "FIFO"),
    ("sqm", "CAKE"),
    ("meeting", "CAKE + meeting priority"),
]
THEMES = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7",
        "series": ["#2a78d6", "#eb6834", "#1baf7a"],
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835",
        "series": ["#3987e5", "#d95926", "#199e70"],
    },
}
W, H = 760, 380
LEFT, RIGHT, TOP, BOTTOM = 56, 196, 78, 48
X_MAX, Y_MAX = 18.0, 320.0
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
LINE = re.compile(r"^\[(\d+\.\d+)\].*icmp_seq=(\d+).*time=([\d.]+) ms")


def representative_run(batch: Path, mode: str) -> Path:
    runs = sorted(batch.glob(f"r*-{mode}-both"))
    p95 = {r: json.loads((r / "summary.json").read_text())["rtt"]["p95_ms"] for r in runs}
    target = statistics.median_low(p95.values())
    return next(r for r in runs if p95[r] == target)


def samples(run: Path) -> tuple[list[list[tuple[float, float]]], float]:
    """Contiguous segments of (seconds since start, rtt ms); a lost ping breaks the line."""
    meta = json.loads((run / "metadata.json").read_text())
    start = meta["started_at_unix"]
    segments: list[list[tuple[float, float]]] = []
    last_seq = None
    for line in (run / "ping.txt").read_text().splitlines():
        m = LINE.match(line)
        if not m:
            continue
        t, seq, rtt = float(m[1]) - start, int(m[2]), float(m[3])
        if t > X_MAX:
            break
        if last_seq is None or seq != last_seq + 1:
            segments.append([])
        segments[-1].append((t, rtt))
        last_seq = seq
    p95 = json.loads((run / "summary.json").read_text())["rtt"]["p95_ms"]
    return segments, p95


def x(t: float) -> float:
    return LEFT + t / X_MAX * (W - LEFT - RIGHT)


def y(ms: float) -> float:
    return TOP + (1 - ms / Y_MAX) * (H - TOP - BOTTOM)


def svg(theme: dict, data: list[tuple[str, list, float]]) -> str:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family=\'{FONT}\' role="img" aria-labelledby="t d">',
        '<title id="t">Meeting latency over time, by queueing policy</title>',
        '<desc id="d">Ping round-trip time every 100 ms while a roommate saturates both directions. '
        + "; ".join(f"{label}: p95 {p95:.1f} ms" for label, _, p95 in data)
        + ". Base round trip is 40 ms.</desc>",
        f'<rect width="{W}" height="{H}" rx="8" fill="{theme["surface"]}"/>',
        f'<text x="{LEFT}" y="30" font-size="16" font-weight="600" fill="{theme["ink"]}">'
        "Meeting latency while the roommate saturates both directions</text>",
        f'<text x="{LEFT}" y="52" font-size="12.5" fill="{theme["ink2"]}">'
        "Ping RTT every 100 ms · gaps are lost pings · typical run per policy (median p95 of 5)</text>",
    ]
    # Grid and y axis.
    for ms in (0, 100, 200, 300):
        yy = y(ms)
        stroke = theme["axis"] if ms == 0 else theme["grid"]
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{stroke}" stroke-width="1"/>')
        out.append(
            f'<text x="{LEFT - 8}" y="{yy + 4:.1f}" font-size="11.5" text-anchor="end" fill="{theme["muted"]}" '
            f'font-variant-numeric="tabular-nums">{ms}</text>'
        )
    out.append(
        f'<text x="{LEFT - 8}" y="{TOP - 12}" font-size="11.5" text-anchor="end" fill="{theme["muted"]}">ms</text>'
    )
    for t in range(0, int(X_MAX) + 1, 3):
        out.append(
            f'<text x="{x(t):.1f}" y="{H - BOTTOM + 18}" font-size="11.5" text-anchor="middle" fill="{theme["muted"]}" '
            f'font-variant-numeric="tabular-nums">{t}s</text>'
        )
    # Base RTT reference.
    yb = y(40)
    out.append(
        f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{yb:.1f}" y2="{yb:.1f}" stroke="{theme["muted"]}" '
        'stroke-width="1" stroke-dasharray="3 4"/>'
    )
    out.append(
        f'<text x="{x(X_MAX) - 4:.1f}" y="{yb + 15:.1f}" font-size="11" text-anchor="end" fill="{theme["muted"]}">'
        "base RTT 40 ms</text>"
    )
    # Series: FIFO first, so the two CAKE lines draw on top of it.
    for i, (label, segments, _) in enumerate(data):
        color = theme["series"][i]
        for seg in segments:
            if len(seg) == 1:
                tx, ms = seg[0]
                out.append(f'<circle cx="{x(tx):.1f}" cy="{y(ms):.1f}" r="1.5" fill="{color}"/>')
                continue
            pts = " ".join(f"{x(t):.1f},{y(ms):.1f}" for t, ms in seg)
            out.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
                'stroke-linejoin="round" stroke-linecap="round"/>'
            )
    # Direct labels at the right edge, in the text ink, with a colored key mark.
    label_y = {"FIFO": y(data[0][2]), "CAKE": y(40) - 58, "CAKE + meeting priority": y(40) - 16}
    for i, (label, _, p95) in enumerate(data):
        ly = label_y[label]
        lx = W - RIGHT + 14
        out.append(f'<line x1="{lx}" x2="{lx + 14}" y1="{ly - 4:.1f}" y2="{ly - 4:.1f}" stroke="{theme["series"][i]}" '
                   'stroke-width="3" stroke-linecap="round"/>')
        out.append(f'<text x="{lx + 20}" y="{ly:.1f}" font-size="12.5" fill="{theme["ink"]}">{label}</text>')
        out.append(f'<text x="{lx + 20}" y="{ly + 15:.1f}" font-size="11.5" fill="{theme["ink2"]}" '
                   f'font-variant-numeric="tabular-nums">p95 {p95:.1f} ms</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> int:
    batch, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    data = []
    for mode, label in POLICIES:
        run = representative_run(batch, mode)
        segments, p95 = samples(run)
        data.append((label, segments, p95))
        print(f"{label}: {run.name}, p95 {p95} ms, {sum(len(s) for s in segments)} pings")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (out_dir / f"latency-{name}.svg").write_text(svg(theme, data), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
