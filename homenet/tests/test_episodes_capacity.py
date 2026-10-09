import sqlite3
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from homenet import episodes, store
from homenet.load import BloatResult, CapacityResult, Phase, describe

T0 = datetime(2026, 10, 7, 12, 0)


def timeline(*internet, every=5, router=3.0):
    """Checks every `every` minutes; None in `internet` leaves a gap of one check."""
    rows = []
    for i, value in enumerate(internet):
        if value is not None:
            rows.append((T0 + timedelta(minutes=every * i), router, value))
    return rows


class SlowPeriods(unittest.TestCase):
    def test_a_plateau_is_one_period_with_start_end_and_size(self):
        rows = timeline(25, 24, 26, 200, 210, 205, 198, 25, 24, 26, 25, 23)
        [e] = episodes.find(rows)
        self.assertEqual((e.start, e.end, e.checks), (T0 + timedelta(minutes=15), T0 + timedelta(minutes=30), 4))
        self.assertEqual(e.internet_p50, 202.5)
        self.assertEqual(e.router_p50, 3.0)
        self.assertFalse(e.open_end)
        self.assertEqual(episodes.fmt_duration(e.duration), "15 min")

    def test_one_good_check_inside_a_plateau_does_not_split_it(self):
        rows = timeline(25, 24, 26, 25, 200, 210, 30, 205, 198, 25, 24, 25, 23)
        [e] = episodes.find(rows)
        self.assertEqual(e.checks, 4)
        self.assertEqual(e.end, T0 + timedelta(minutes=40))

    def test_two_good_checks_end_it(self):
        rows = timeline(25, 24, 26, 25, 200, 210, 30, 28, 205, 198, 25, 24, 23)
        self.assertEqual([e.checks for e in episodes.find(rows)], [2, 2])

    def test_a_single_slow_check_is_a_spike_not_a_period(self):
        rows = timeline(25, 24, 26, 300, 25, 24, 26, 25, 23, 24)
        self.assertEqual(episodes.find(rows), [])

    def test_a_gap_ends_a_period_as_open_ended(self):
        # Slow, then the laptop sleeps for an hour, then normal again.
        rows = timeline(25, 24, 26, 25, 200, 210, *[None] * 12, 25, 24, 26)
        [e] = episodes.find(rows)
        self.assertTrue(e.open_end)
        self.assertEqual(e.checks, 2)

    def test_still_slow_at_the_end_of_the_data_is_open_ended(self):
        rows = timeline(25, 24, 26, 25, 23, 24, 200, 210, 205)
        [e] = episodes.find(rows)
        self.assertTrue(e.open_end)

    def test_threshold_is_relative_to_the_lines_normal_latency(self):
        # A line that normally sits at 100 ms: 140 is not slow, 160 is.
        rows = timeline(100, 101, 99, 100, 140, 140, 100, 160, 160, 100, 100)
        self.assertEqual(episodes.normal_latency(rows), 100)
        [e] = episodes.find(rows)
        self.assertEqual(e.internet_p50, 160)

    def test_during(self):
        [e] = episodes.find(timeline(25, 24, 26, 200, 210, 205, 25, 24, 23, 25))
        self.assertTrue(episodes.during(T0 + timedelta(minutes=20), [e]))
        self.assertFalse(episodes.during(T0 + timedelta(minutes=5), [e]))


class FailedTransfers(unittest.TestCase):
    def test_no_data_is_a_failure_with_the_reason_not_zero_mbps(self):
        p = Phase("download", seconds=3.0, errors=Counter({"HTTP 403": 6, "TimeoutError": 1}))
        self.assertIsNone(p.mbps)
        self.assertEqual(p.failure, "HTTP 403 x6, TimeoutError x1")
        self.assertEqual(Phase("upload", seconds=3.0).failure, "no data received")

    def test_data_moved_is_a_measurement_even_with_some_errors(self):
        p = Phase("download", bytes_moved=37_500_000, seconds=3.0, errors=Counter({"HTTP 429": 1}))
        self.assertIsNone(p.failure)
        self.assertEqual(p.mbps, 100.0)

    def test_idle_never_fails(self):
        self.assertIsNone(Phase("idle", seconds=10).failure)

    def test_describe_orders_by_count(self):
        self.assertEqual(describe(Counter({"a": 1, "b": 3})), "b x3, a x1")

    def test_a_failed_load_phase_gets_no_grade(self):
        idle = Phase("idle", seconds=10)
        idle.internet.rtts = [25.0] * 10
        down = Phase("download", seconds=10, errors=Counter({"HTTP 403": 4}))
        down.internet.rtts = [25.0] * 10  # the line was idle, so this would grade "A"
        grade, added, meaning = BloatResult(idle, down, down).grade(down)
        self.assertEqual((grade, added), ("?", None))
        self.assertIn("HTTP 403", meaning)

    def test_capacity_stores_null_and_the_reason(self):
        ok = Phase("upload", bytes_moved=15_000_000, seconds=3.0)
        bad = Phase("download", seconds=3.0, errors=Counter({"HTTP 403": 4}))
        with tempfile.TemporaryDirectory() as d:
            db = store.connect(Path(d) / "h.sqlite")
            store.save_capacity(db, "2026-10-09T02:20:00+00:00", CapacityResult(bad, ok))
            row = db.execute("select down_mbps, up_mbps, down_error, up_error from capacity").fetchone()
            by_hour = store.capacity_by_hour(db)
            db.close()
        self.assertEqual(row, (None, 40.0, "HTTP 403 x4", None))
        self.assertEqual(by_hour[0][2:], (None, 40.0, 1))  # no fake 0 in the median; one failure counted


class OldDatabases(unittest.TestCase):
    def test_connect_adds_new_columns_to_an_existing_database(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "h.sqlite"
            old = sqlite3.connect(path)
            old.execute("create table capacity (at text not null, down_mbps real, up_mbps real, "
                        "down_loaded_p50 real, up_loaded_p50 real)")
            old.execute("insert into capacity values ('t', 250, 35, 40, 60)")
            old.commit()
            old.close()
            db = store.connect(path)
            row = db.execute("select down_mbps, down_error, up_error from capacity").fetchone()
            store.connect(path).close()  # connecting twice must not fail
            db.close()
        self.assertEqual(row, (250, None, None))


if __name__ == "__main__":
    unittest.main()
