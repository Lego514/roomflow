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
