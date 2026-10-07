"""SQLite history, so an evening of interviews can be compared with a normal day.

Stored: radio facts (band, channel, signal, link rates) and latency summaries.
Never stored: network names (SSID), MAC addresses, the router's address, or
the addresses of routers along the path (a trace keeps hop numbers and segments).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .check import CheckResult
from .load import BloatResult

SCHEMA = """
create table if not exists checks (
  at text not null, band text, channel integer, signal_pct integer, rssi_dbm integer,
  rx_mbps real, tx_mbps real, status text not null, layer text
);
create table if not exists latency (
  at text not null, layer text not null, target text not null,
  sent integer, loss_pct real, p50_ms real, p95_ms real, jitter_ms real
);
create table if not exists trace (
  at text not null, target text not null, hop integer not null, segment text,
  loss_pct real, p50_ms real, effective_ms real, added_ms real, note text
);
create table if not exists ipv6 (
  at text not null, target text not null, v4_p50 real, v6_p50 real, verdict text
);
create table if not exists bloat (
  at text not null, phase text not null, mbps real,
  internet_p50 real, internet_p95 real, gateway_p50 real, gateway_p95 real,
  grade text, added_ms real
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def save_check(db: sqlite3.Connection, at: str, r: CheckResult) -> None:
    w = r.wifi
    db.execute(
        "insert into checks values (?,?,?,?,?,?,?,?,?)",
        (at, w and w.band, w and w.channel, w and w.signal_pct, w and w.rssi_dbm,
         w and w.rx_mbps, w and w.tx_mbps, r.verdict[0], r.verdict[1]),
    )
    for layer, series in r.layers.items():
        for s in series:
            target = "gateway" if layer == "gateway" else s.target  # don't store the router's IP
            db.execute("insert into latency values (?,?,?,?,?,?,?,?)",
                       (at, layer, target, s.sent, s.loss_pct, s.p50, s.p95, s.jitter))
    db.commit()


def save_bloat(db: sqlite3.Connection, at: str, r: BloatResult) -> None:
    for phase in (r.idle, r.download, r.upload):
        grade, added, _ = r.grade(phase) if phase is not r.idle else ("", None, "")
        db.execute("insert into bloat values (?,?,?,?,?,?,?,?,?)",
                   (at, phase.name, phase.mbps if phase is not r.idle else None,
                    phase.internet.p50, phase.internet.p95, phase.gateway.p50, phase.gateway.p95,
                    grade or None, added))
    db.commit()


def hourly(db: sqlite3.Connection) -> list[tuple]:
    """Median-ish view by local hour: mean of per-check internet p95 and worst status count."""
    return db.execute(
        """
        select strftime('%H', at, 'localtime') as hour,
               count(distinct l.at) as checks,
               round(avg(l.p95_ms), 1) as internet_p95,
               round(max(l.p95_ms), 1) as worst_p95,
               round(avg(l.loss_pct), 2) as loss_pct
        from latency l where l.layer = 'internet'
        group by hour order by hour
        """
    ).fetchall()


def save_trace(db: sqlite3.Connection, at: str, target: str, verdict) -> None:
    for r in verdict.rows:
        s = r.series
        db.execute("insert into trace values (?,?,?,?,?,?,?,?,?)",
                   (at, target, r.hop.index, r.segment, s.loss_pct if s else None, s.p50 if s else None,
                    r.effective_ms, r.added_ms, r.note))
    db.commit()


def save_ipv6(db: sqlite3.Connection, at: str, pairs) -> None:
    for pair in pairs:
        db.execute("insert into ipv6 values (?,?,?,?,?)",
                   (at, pair.label, pair.v4.p50 if pair.v4 else None, pair.v6.p50 if pair.v6 else None, pair.verdict))
    db.commit()


def _median(values: list[float]) -> float | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def bloat_runs(db: sqlite3.Connection) -> list[tuple]:
    """One row per bufferbloat run: local time, download and upload (Mbps, grade, added ms)."""
    rows = db.execute(
        """
        select datetime(d.at, 'localtime'), d.mbps, d.grade, d.added_ms, u.mbps, u.grade, u.added_ms
        from bloat d join bloat u on u.at = d.at and u.phase = 'upload'
        where d.phase = 'download' order by d.at
        """
    ).fetchall()
    return rows


def ipv6_summary(db: sqlite3.Connection) -> list[tuple]:
    """Per target: runs, median IPv4 and IPv6, and in how many runs IPv6 was at least 3 ms slower."""
    out = []
    targets = [r[0] for r in db.execute("select distinct target from ipv6 order by target")]
    for t in targets:
        rows = db.execute("select v4_p50, v6_p50 from ipv6 where target = ?", (t,)).fetchall()
        both = [(a, b) for a, b in rows if a is not None and b is not None]
        slower = sum(1 for a, b in both if b - a >= 3.0)
        out.append((t, len(rows), _median([a for a, _ in rows]), _median([b for _, b in rows]), slower, len(both)))
    return out


def trace_summary(db: sqlite3.Connection) -> tuple | None:
    """Across trace runs: count, median end-to-end latency, and which segment adds the most latency most often."""
    runs = db.execute("select distinct at from trace").fetchall()
    if not runs:
        return None
    totals, biggest_segments, biggest_added = [], {}, []
    for (at,) in runs:
        rows = db.execute(
            "select segment, effective_ms, added_ms from trace where at = ? and effective_ms is not null order by hop",
            (at,),
        ).fetchall()
        if not rows:
            continue
        totals.append(rows[-1][1])
        seg, _, added = max(rows, key=lambda r: r[2] or 0)
        biggest_segments[seg] = biggest_segments.get(seg, 0) + 1
        biggest_added.append(added)
    if not totals:
        return None
    top = max(biggest_segments.items(), key=lambda kv: kv[1])
    return len(totals), _median(totals), top[0], top[1], _median(biggest_added)
