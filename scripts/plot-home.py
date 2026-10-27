#!/usr/bin/env python3
"""Draw home latency over time, router vs internet, as light and dark SVGs.

Input: a frozen incident JSON snapshot, or read-only local history from homenet.
For every scheduled
check it takes the router's median ping and the internet's median (mean of the
1.1.1.1 and 8.8.8.8 medians) and plots both along real time. A timeline rather
than an average by hour of day, because the slow periods start and stop at
different hours on different days; averaging by hour would blur that on/off
shape. The two series use different protocols and sequential measurements;
they show observations rather than locating a queue or ruling out Wi-Fi.
Gaps longer than 15 minutes break the lines; their cause is not inferred.
Shaded bands are the slow periods homenet's report detects (homenet/episodes.py).

    python scripts/plot-home.py docs/evidence/home-incident.json docs/
    python scripts/plot-home.py data/home.sqlite docs/
"""
from __future__ import annotations

import sys
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from homenet import episodes, store  # noqa: E402

THEMES = {
    "light": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
              "grid": "#e1e0d9", "axis": "#c3c2b7", "band": "#efede6", "series": ["#2a78d6", "#eb6834"]},
    "dark": {"surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
             "grid": "#2c2c2a", "axis": "#383835", "band": "#262624", "series": ["#3987e5", "#d95926"]},
}
W, H = 760, 380
LEFT, RIGHT, TOP, BOTTOM = 56, 150, 78, 48
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


GAP = timedelta(minutes=15)


def segments(rows, index: int, t0: datetime, t1: datetime, top: float) -> list[list[str]]:
    """Point lists for one series; a gap in time or a missing value starts a new segment."""
    out, seg, prev = [], [], None
    for row in rows:
        t, value = row[0], row[index]
        if value is None or (prev is not None and t - prev > GAP):
            if seg:
                out.append(seg)
            seg = []
        if value is not None:
            seg.append(f"{xt(t, t0, t1):.1f},{y(min(value, top), top):.1f}")
        prev = t
    if seg:
        out.append(seg)
    return out


def xt(t: datetime, t0: datetime, t1: datetime) -> float:
    return LEFT + (t - t0) / (t1 - t0) * (W - LEFT - RIGHT)


def y(ms: float, top: float) -> float:
    return TOP + (1 - ms / top) * (H - TOP - BOTTOM)


def draw(segs: list[list[str]], color: str) -> list[str]:
    svg = []
    for s in segs:
        if len(s) == 1:
            cx, cy = s[0].split(",")
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="{color}"/>')
        else:
            svg.append(f'<polyline points="{" ".join(s)}" fill="none" stroke="{color}" stroke-width="1.5" '
                       'stroke-linejoin="round" stroke-linecap="round"/>')
    return svg


def svg(theme: dict, rows, checks: int, slow: list) -> str:
    t0, t1 = rows[0][0], rows[-1][0]
    top = 300.0  # clip the rare spike so the plateaus stay readable
    span = f"{t0:%b %d %H:%M} to {t1:%b %d %H:%M}"
    offset = t0.strftime("%z")
    zone = f"UTC{offset[:3]}:{offset[3:]}" if offset else "host local time"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family=\'{FONT}\' role="img" aria-labelledby="t d">',
        '<title id="t">Home latency over time: router vs internet</title>',
        f'<desc id="d">Recorded checks from {span}, {zone}. Gateway ICMP and external TCP handshake '
        'medians are different probes. Shaded bands mark sustained external latency increases; '
        'these observations do not confirm the cause or rule out Wi-Fi.</desc>',
        f'<rect width="{W}" height="{H}" rx="8" fill="{theme["surface"]}"/>',
        f'<text x="{LEFT}" y="30" font-size="16" font-weight="600" fill="{theme["ink"]}">'
        "Home latency observations; the cause remains unconfirmed</text>",
        f'<text x="{LEFT}" y="52" font-size="12.5" fill="{theme["ink2"]}">'
        f"{checks} checks · {span} {zone} · medians capped at {top:.0f} ms</text>",
    ]
    for e in slow:  # behind the grid and the lines
        x0, x1 = xt(e.start, t0, t1), xt(e.end, t0, t1)
        out.append(f'<rect x="{x0:.1f}" y="{TOP}" width="{max(x1 - x0, 1):.1f}" height="{H - TOP - BOTTOM}" '
                   f'fill="{theme["band"]}"/>')
    for ms in range(0, int(top) + 1, 100):
        yy = y(ms, top)
        stroke = theme["axis"] if ms == 0 else theme["grid"]
        out.append(f'<line x1="{LEFT}" x2="{W - RIGHT}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{stroke}" stroke-width="1"/>')
        out.append(f'<text x="{LEFT - 8}" y="{yy + 4:.1f}" font-size="11.5" text-anchor="end" fill="{theme["muted"]}" '
                   f'font-variant-numeric="tabular-nums">{ms}</text>')
    out.append(f'<text x="{LEFT - 8}" y="{TOP - 12}" font-size="11.5" text-anchor="end" fill="{theme["muted"]}">ms</text>')
    # Keep labels readable as the observation window grows.
    hours = (t1 - t0).total_seconds() / 3600
    tick_hours = next((step for step in (6, 12, 24, 48, 96, 168) if hours / step <= 7), 336)
    tick = t0.replace(minute=0, second=0, microsecond=0)
    if tick_hours < 24:
        while tick.hour % tick_hours:
            tick += timedelta(hours=1)
    else:
        tick = tick.replace(hour=0)
    while tick < t0:
        tick += timedelta(hours=tick_hours)
    while tick <= t1:
        if tick >= t0:
            label = (f"{tick:%a %d}" if tick_hours >= 24 else
                     f"{tick:%a} {tick.hour % 12 or 12}{'am' if tick.hour < 12 else 'pm'}")
            out.append(f'<text x="{xt(tick, t0, t1):.1f}" y="{H - BOTTOM + 18}" font-size="11.5" text-anchor="middle" '
                       f'fill="{theme["muted"]}">{label}</text>')
        tick += timedelta(hours=tick_hours)
    out += draw(segments(rows, 2, t0, t1, top), theme["series"][0])
    out += draw(segments(rows, 1, t0, t1, top), theme["series"][1])
    lx = W - RIGHT + 14
    for name, ly, i in (("External TCP", y(200, top) + 4, 0), ("Gateway ping", y(0, top) - 4, 1)):
        out.append(f'<line x1="{lx}" x2="{lx + 14}" y1="{ly - 4:.1f}" y2="{ly - 4:.1f}" stroke="{theme["series"][i]}" '
                   'stroke-width="3" stroke-linecap="round"/>')
        out.append(f'<text x="{lx + 20}" y="{ly:.1f}" font-size="12.5" fill="{theme["ink"]}">{name}</text>')
    if slow:
        ly = y(100, top) + 4
        out.append(f'<rect x="{lx}" y="{ly - 10:.1f}" width="14" height="12" fill="{theme["band"]}" '
                   f'stroke="{theme["axis"]}" stroke-width="0.5"/>')
        out.append(f'<text x="{lx + 20}" y="{ly:.1f}" font-size="12.5" fill="{theme["ink"]}">Slow period</text>')
    out.append(f'<text x="{LEFT}" y="{H - 8}" font-size="10.5" fill="{theme["ink2"]}">'
               'ICMP/TCP probes differ; shading marks observations, not a confirmed cause.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def load_rows(source: Path):
    if source.suffix.lower() == ".json":
        snapshot = json.loads(source.read_text(encoding="utf-8"))
        return [(datetime.fromisoformat(row["at_local"]), row["gateway_p50_ms"], row["internet_p50_ms"])
                for row in snapshot["timeline"]]
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return store.check_timeline(db)


def main() -> int:
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    rows = load_rows(source)
    checks = len(rows)
    slow = episodes.find(rows)
    if len(rows) < 2:
        print("not enough checks recorded yet")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        (out_dir / f"home-latency-{name}.svg").write_text(svg(theme, rows, checks, slow), encoding="utf-8", newline="\n")
    print(f"{checks} checks, {rows[0][0]} to {rows[-1][0]}; {len(slow)} slow periods shaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
