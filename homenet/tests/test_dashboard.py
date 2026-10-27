"""Snapshot/CLI integration, with mocked probes and temporary SQLite history."""
import argparse
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from homenet import dashboard, incidents, store
from homenet import __main__ as cli
from homenet.tests.test_incidents import result, sample, timestamp


class DashboardSnapshots(unittest.TestCase):
    def test_drill_frames_are_authoritative_prefixes_without_future_evidence(self):
        samples = [sample(i, i in (2, 3, 4)) for i in range(7)]
        samples[4]["layers"]["internet"]["p95Ms"] = 700
        payload = dashboard.build_dashboard(samples, source_kind="lab-drill", evaluated_at=timestamp(6))
        replay = payload["replay"]
        self.assertTrue(replay["available"])
        self.assertEqual(replay["totalSamples"], 7)
        self.assertEqual([frame["stage"] for frame in replay["frames"]],
                         ["normal", "normal", "pending", "pending", "open", "recovering", "resolved"])
        for count, frame in enumerate(replay["frames"], 1):
            expected = incidents.replay(samples[:count])
            self.assertEqual(frame["sampleCount"], count)
            self.assertEqual(frame["at"], incidents.utc(timestamp(count - 1)))
            for key in ("incidents", "notifications", "pendingAbnormalChecks", "pendingRecoveryChecks"):
                self.assertEqual(frame[key], expected[key])
            for event in frame["incidents"]:
                self.assertLessEqual(incidents.instant(event["evidence"]["endAt"]), incidents.instant(frame["at"]))
                for transition in event["transitions"]:
                    self.assertLessEqual(incidents.instant(transition["at"]), incidents.instant(frame["at"]))
        self.assertEqual(replay["frames"][3]["incidents"], [])
        opened = replay["frames"][4]["incidents"][0]
        self.assertIsNone(opened["resolvedAt"])
        self.assertEqual(len(opened["transitions"]), 1)
        self.assertEqual(replay["frames"][-1]["incidents"], payload["incidents"])
        self.assertEqual(replay["frames"][-1]["notifications"], payload["notifications"])

    def test_drill_prefix_peak_does_not_leak_a_later_open_event_spike(self):
        samples = [sample(i, i < 4) for i in range(6)]
        samples[3]["layers"]["internet"]["p95Ms"] = 900
        frames = dashboard.build_dashboard(samples, source_kind="lab-drill")["replay"]["frames"]
        self.assertEqual(frames[2]["incidents"][0]["evidence"]["layers"]["internet"]["peakP95Ms"], 200)
        self.assertEqual(frames[3]["incidents"][0]["evidence"]["layers"]["internet"]["peakP95Ms"], 900)
        self.assertEqual([frame["stage"] for frame in frames],
                         ["pending", "pending", "open", "open", "recovering", "resolved"])

    def test_drill_stages_keep_unknown_and_interrupted_recovery_distinct(self):
        samples = [sample(0, missing="dns"), sample(1, True), sample(2, True), sample(3, True),
                   sample(4), sample(5, missing="dns"), sample(6), sample(7)]
        frames = dashboard.build_dashboard(samples, source_kind="lab-drill")["replay"]["frames"]
        self.assertEqual([frame["stage"] for frame in frames],
                         ["unknown", "pending", "pending", "open", "recovering", "open", "recovering", "resolved"])
        self.assertEqual(frames[5]["pendingRecoveryChecks"], 0)
        self.assertEqual(frames[5]["incidents"][0]["status"], "open")
        self.assertEqual(len(frames[5]["notifications"]), 1)

    def test_drill_replay_deduplicates_samples_and_bounds_work_for_large_inputs(self):
        samples = [sample(1, True), sample(0), sample(1, True)]
        replay = dashboard.build_dashboard(samples, source_kind="lab-drill")["replay"]
        self.assertEqual(replay["totalSamples"], 2)
        self.assertEqual([frame["sampleCount"] for frame in replay["frames"]], [1, 2])
        with patch.object(dashboard, "MAX_REPLAY_SAMPLES", 2):
            limited = dashboard.build_dashboard([sample(i) for i in range(3)], source_kind="lab-drill")
        self.assertEqual(limited["replay"], {"frames": [], "totalSamples": 3, "available": False, "reason": "sample-limit"})
        self.assertEqual(limited["timelineTotal"], 3)
        empty = dashboard.build_dashboard([], source_kind="lab-drill")["replay"]
        self.assertEqual(empty, {"frames": [], "totalSamples": 0, "available": True})

    def test_replay_frames_are_only_exported_for_lab_drills(self):
        for source in ("local-history", "historical-demo"):
            self.assertNotIn("replay", dashboard.build_dashboard([sample(0)], source_kind=source))

    def test_empty_historical_current_and_stale_are_distinct(self):
        self.assertEqual(dashboard.build_dashboard([], evaluated_at=timestamp(0))["monitor"]["status"], "empty")
        samples = [sample(0), sample(1), sample(2)]
        fresh = dashboard.build_dashboard(samples, evaluated_at=timestamp(3))
        self.assertEqual(fresh["monitor"]["status"], "current")
        stale = dashboard.build_dashboard(samples, evaluated_at=timestamp(6))
        self.assertEqual(stale["monitor"]["status"], "stale")
        self.assertEqual(stale["latest"]["status"], "ok")  # last observation, not current health
        historical = dashboard.build_dashboard(samples, source_kind="historical-demo", evaluated_at=timestamp(2))
        self.assertEqual(historical["monitor"]["status"], "historical")
        future = dashboard.build_dashboard(samples, evaluated_at=timestamp(0))
        self.assertEqual(future["monitor"]["status"], "stale")
        self.assertTrue(future["monitor"]["clockSkew"])

    def test_stale_active_incident_does_not_accumulate_unobserved_now(self):
        samples = [sample(i, True) for i in range(3)]
        before = dashboard.build_dashboard(samples, evaluated_at=timestamp(2))
        later = dashboard.build_dashboard(samples, evaluated_at=timestamp(100))
        self.assertEqual(before["incidents"], later["incidents"])
        self.assertEqual(later["incidents"][0]["status"], "open")
        self.assertEqual(later["incidents"][0]["durationSeconds"], 600)

    def test_snapshot_whitelist_excludes_addresses_and_radio_identifiers(self):
        clean = sample(0)
        clean["target"] = "203.0.113.45"
        clean["ssid"] = "family-network"
        clean["mac"] = "11:22:33:44:55:66"
        clean["layers"]["internet"]["target"] = "private-target.example"
        clean["layers"]["dns"]["flags"].append("private-target.example timed out")
        payload = json.dumps(dashboard.build_dashboard([clean], evaluated_at=timestamp(0)))
        for private in ("203.0.113.45", "family-network", "11:22:33:44:55:66", "private-target.example"):
            self.assertNotIn(private, payload)

    def test_historical_partial_snapshot_does_not_manufacture_counts_or_recovery(self):
        raw = {"timeline": [{"at_utc": timestamp(i), "gateway_p50_ms": 2,
                             "internet_p50_ms": 200 if i < 3 else 20} for i in range(5)]}
        payload = dashboard.build_dashboard(dashboard.historical_samples(raw), source_kind="historical-demo")
        self.assertEqual(payload["incidents"][0]["status"], "open")
        self.assertEqual(payload["latest"]["status"], "unknown")
        self.assertIsNone(payload["latest"]["layers"]["internet"]["attempts"])
        self.assertIsNone(payload["latest"]["layers"]["internet"]["failurePct"])

    def test_full_history_is_classified_before_timeline_is_bounded(self):
        samples = [sample(i, True) for i in range(2002)]
        payload = dashboard.build_dashboard(samples, evaluated_at=timestamp(2002))
        self.assertEqual(len(payload["timeline"]), 2000)
        self.assertEqual(payload["timelineTotal"], 2002)
        self.assertTrue(payload["timelineTruncated"])
        self.assertEqual(payload["incidents"][0]["startedAt"], incidents.utc(timestamp(0)))

    def test_duplicate_legacy_rows_are_deduplicated_and_collisions_remain_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            with closing(store.connect(Path(temp) / "home.sqlite")) as db, db:
                store.save_check(db, timestamp(0), result())
                db.execute("insert into checks select * from checks")
                db.execute("insert into latency select * from latency")
                db.commit()
                duplicate, = dashboard.samples_from_connection(db)
                self.assertEqual(duplicate["status"], "ok")
                self.assertEqual(duplicate["layers"]["internet"]["attempts"], 20)
                db.execute("insert into latency select at,layer,target,sent,loss_pct,p50_ms,500,jitter_ms from latency where layer='internet' limit 1")
                db.commit()
                collision, = dashboard.samples_from_connection(db)
                layer = collision["layers"]["internet"]
                self.assertEqual(layer["status"], "degraded")
                self.assertFalse(layer["complete"])
                self.assertIsNone(layer["attempts"])
                self.assertIn("conflicting-target-records", layer["flags"])

    def test_atomic_export_leaves_complete_json_and_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "observations.json"
            data = dashboard.build_dashboard([sample(0)], evaluated_at=timestamp(0))
            dashboard.atomic_export(data, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), data)
            self.assertEqual([path.name for path in Path(temp).iterdir()], ["observations.json"])

    def test_read_only_source_export_never_migrates_or_changes_sqlite_history(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "home.sqlite"
            with closing(store.connect(path)) as db, db:
                store.save_check(db, timestamp(0), result(True))
            original = path.read_bytes()
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db, db:
                db.execute("pragma query_only=on")
                db.execute("begin")
                payload = dashboard.build_dashboard(dashboard.samples_from_connection(db, timestamp(0)),
                                                    source_kind="historical-demo", evaluated_at=timestamp(0))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(payload["timelineTotal"], 1)
            self.assertNotIn("203.0.113.45", json.dumps(payload))


class ScheduledExport(unittest.TestCase):
    def test_check_saves_and_exports_without_real_network_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "home.sqlite"
            with patch.object(cli, "DB", database), patch.object(cli, "run_check", return_value=result(True)), \
                    patch.object(cli, "now", return_value=timestamp(0)), redirect_stdout(io.StringIO()):
                with patch.object(cli, "print_check"):
                    cli.cmd_check(argparse.Namespace(count=10, skip_during_bloat=False))
            output = json.loads((Path(temp) / "observations.json").read_text(encoding="utf-8"))
            self.assertEqual(output["source"]["kind"], "local-history")
            self.assertEqual(output["timelineTotal"], 1)
            self.assertEqual(output["latest"]["status"], "degraded")

    def test_watch_exports_each_saved_check_without_real_network_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "home.sqlite"
            with patch.object(cli, "DB", database), patch.object(cli, "run_check", return_value=result()), \
                    patch.object(cli, "now", return_value=timestamp(0)), redirect_stdout(io.StringIO()), \
                    patch.object(cli.time, "sleep", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cli.cmd_watch(argparse.Namespace(count=10, every=300))
            output = json.loads((Path(temp) / "observations.json").read_text(encoding="utf-8"))
            self.assertEqual(output["timelineTotal"], 1)


if __name__ == "__main__":
    unittest.main()
