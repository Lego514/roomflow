"""SQLite history, so an evening of interviews can be compared with a normal day.

Stored: radio facts (band, channel, signal, link rates) and latency summaries.
Never stored: network names (SSID), MAC addresses, the router's address, or
the addresses of routers along the path (a trace keeps hop numbers and segments).
"""

from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
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
create table if not exists capacity (
  at text not null, down_mbps real, up_mbps real, down_loaded_p50 real, up_loaded_p50 real,
  down_error text, up_error text
);
create table if not exists bloat (
  at text not null, phase text not null, mbps real,
  internet_p50 real, internet_p95 real, gateway_p50 real, gateway_p95 real,
  grade text, added_ms real, error text
);
"""

# Columns added after the first release; older databases get them on connect.
ADDED_COLUMNS = {"capacity": ("down_error text", "up_error text"), "bloat": ("error text",)}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for table, columns in ADDED_COLUMNS.items():
        have = {row[1] for row in db.execute(f"pragma table_info({table})")}
        for column in columns:
            if column.split()[0] not in have:
                db.execute(f"alter table {table} add column {column}")
    db.commit()
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
        db.execute("insert into bloat values (?,?,?,?,?,?,?,?,?,?)",
                   (at, phase.name, phase.mbps if phase is not r.idle else None,
                    phase.internet.p50, phase.internet.p95, phase.gateway.p50, phase.gateway.p95,
                    None if grade in ("", "?") else grade, added, phase.failure))
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


@dataclass(frozen=True)
class Ipv6Summary:
    target: str
    runs: int
    paired: int  # runs where both IPv4 and IPv6 answered
    v4_p50: float | None  # median over paired runs only
    v6_p50: float | None
    v6_slower: int  # paired runs where IPv6 was at least 3 ms slower
    v6_failed: int  # runs where IPv4 answered but IPv6 didn't (target has an IPv6 address)


def ipv6_summary(db: sqlite3.Connection) -> list[Ipv6Summary]:
    """Per target, comparing IPv4 and IPv6 only on runs where both answered.

    Medians over all runs would compare different moments: if IPv6 fails exactly
    when the line is congested, its surviving samples all come from quiet hours
    and IPv6 looks far faster than it is. Failures are counted separately.
    """
    out = []
    targets = [r[0] for r in db.execute("select distinct target from ipv6 order by target")]
    for t in targets:
        rows = db.execute("select v4_p50, v6_p50, verdict from ipv6 where target = ?", (t,)).fetchall()
        both = [(a, b) for a, b, _ in rows if a is not None and b is not None]
        # A name that resolved to an IPv6 address in other runs but not in this one
        # failed too (the AAAA lookup itself failed), it isn't IPv4-only.
        has_v6 = any(verdict != "no IPv6 address" for _, _, verdict in rows)
        failed = sum(1 for a, b, _ in rows if a is not None and b is None and has_v6)
        out.append(Ipv6Summary(
            target=t,
            runs=len(rows),
            paired=len(both),
            v4_p50=_median([a for a, _ in both]),
            v6_p50=_median([b for _, b in both]),
            v6_slower=sum(1 for a, b in both if b - a >= 3.0),
            v6_failed=failed,
        ))
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


def save_capacity(db: sqlite3.Connection, at: str, r) -> None:
    """A direction whose transfers all failed is stored as NULL Mbps plus the reason, never as 0."""
    db.execute("insert into capacity values (?,?,?,?,?,?,?)",
               (at, r.download.mbps, r.upload.mbps, r.download.internet.p50, r.upload.internet.p50,
                r.download.failure, r.upload.failure))
    db.commit()


def capacity_by_hour(db: sqlite3.Connection) -> list[tuple]:
    """Per local hour: runs, median download and upload Mbps available, failed measurements."""
    by_hour: dict[str, tuple[list[float], list[float], list[int]]] = {}
    for hour, down, up, failed in db.execute(
        "select strftime('%H', at, 'localtime'), down_mbps, up_mbps, "
        "(down_error is not null) + (up_error is not null) from capacity order by at"
    ):
        downs, ups, fails = by_hour.setdefault(hour, ([], [], []))
        downs.append(down)
        ups.append(up)
        fails.append(failed)
    return [(h, len(d), _median(d), _median(u), sum(f)) for h, (d, u, f) in sorted(by_hour.items())]


def capacity_runs(db: sqlite3.Connection) -> list[tuple[datetime, float | None, float | None]]:
    """Every capacity run in local time: (when, down Mbps, up Mbps); None where that direction failed."""
    return [(datetime.fromisoformat(at), down, up) for at, down, up in db.execute(
        "select datetime(at, 'localtime'), down_mbps, up_mbps from capacity order by at")]


def ipv6_runs(db: sqlite3.Connection) -> list[tuple[datetime, bool]]:
    """Every IPv6 run in local time: (when, whether any target with IPv6 failed over IPv6 while IPv4 worked)."""
    v6_targets = {t for (t,) in db.execute("select distinct target from ipv6 where verdict != 'no IPv6 address'")}
    runs: dict[str, bool] = {}
    for at, target, v4, v6 in db.execute(
        "select datetime(at, 'localtime'), target, v4_p50, v6_p50 from ipv6 order by at"
    ):
        failed = target in v6_targets and v4 is not None and v6 is None
        runs[at] = runs.get(at, False) or failed
    return [(datetime.fromisoformat(at), failed) for at, failed in runs.items()]


def check_timeline(db: sqlite3.Connection) -> list[tuple[datetime, float | None, float | None]]:
    """One row per scheduled check in local time: (when, router p50, internet p50).

    The internet value is the mean of the per-target medians (1.1.1.1 and 8.8.8.8).
    """
    per_check: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for at, layer, p50 in db.execute(
        "select datetime(at, 'localtime'), layer, p50_ms from latency "
        "where layer in ('gateway', 'internet') and p50_ms is not null"
    ):
        per_check[at][layer].append(p50)
    rows = []
    for at in sorted(per_check):
        layers = per_check[at]
        rows.append((
            datetime.fromisoformat(at),
            statistics.fmean(layers["gateway"]) if layers.get("gateway") else None,
            statistics.fmean(layers["internet"]) if layers.get("internet") else None,
        ))
    return rows
