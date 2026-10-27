"""State-machine tests use synthetic observations and never contact a network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from homenet import dashboard, incidents, store
from homenet.check import CheckResult
from homenet.stats import Series

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def timestamp(index):
    return (BASE + timedelta(minutes=5 * index)).isoformat()


def result(degraded=False, *, missing=None, failed=False):
    layers = {name: [Series(f"private-target-{index}.example", 10, [2 if name == "gateway" else 20] * 10)
                     for index in range(incidents.EXPECTED_SERIES[name])] for name in incidents.LAYERS}
    if degraded:
        layers["internet"] = [Series(f"203.0.113.{45+index}", 10, [] if failed else [200] * 10) for index in range(2)]
    if missing:
        layers[missing] = []
    return CheckResult(None, layers, {}, ("degraded" if degraded else "ok", "internet" if degraded else None))


def sample(index, degraded=False, **kwargs):
    return incidents.sample_from_layers(timestamp(index), result(degraded, **kwargs).layers)


class IncidentStateMachine(unittest.TestCase):
    def test_spike_and_two_abnormal_checks_do_not_open(self):
        history = [sample(i, bad) for i, bad in enumerate((False, True, False, True, True, False))]
        self.assertEqual(incidents.replay(history)["incidents"], [])

    def test_open_once_then_resolve_once_after_two_complete_healthy_checks(self):
        history = [sample(i, bad) for i, bad in enumerate((True, True, True, True, False, True, False, False, False))]
        output = incidents.replay(history)
        incident, = output["incidents"]
        self.assertEqual(incident["status"], "resolved")
        self.assertEqual(incident["startedAt"], incidents.utc(timestamp(0)))
        self.assertEqual(incident["openedAt"], incidents.utc(timestamp(2)))
        self.assertEqual(incident["resolvedAt"], incidents.utc(timestamp(7)))
        self.assertEqual(incident["abnormalChecks"], 5)
        self.assertEqual([row["type"] for row in output["notifications"]], ["opened", "resolved"])
        self.assertEqual(incident["affectedLayers"], ["internet"])
        self.assertEqual(output, incidents.replay(history + [history[0], history[1]]))

    def test_unknown_and_collection_gap_reset_pending_abnormal_streak(self):
        unknown = sample(2, missing="dns")
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(incidents.replay([sample(0, True), sample(1, True), unknown, sample(3, True)])["incidents"], [])
        self.assertEqual(incidents.replay([sample(0, True), sample(1, True), sample(5, True)])["incidents"], [])

    def test_active_incident_survives_unknown_and_gap_with_bounded_duration(self):
        history = [sample(0, True), sample(1, True), sample(2, True), sample(3),
                   sample(4, missing="dns"), sample(5), sample(10)]
        output = incidents.replay(history)
        incident, = output["incidents"]
        self.assertEqual(incident["status"], "open")
        self.assertEqual(incident["durationSeconds"], 900)
        self.assertEqual(incident["spanSeconds"], 3000)
        self.assertEqual({gap["reason"] for gap in incident["evidenceGaps"]}, {"incomplete-check", "collection-gap"})
        self.assertEqual(len(output["notifications"]), 1)
        final = incidents.replay(history + [sample(11)])["incidents"][0]
        self.assertEqual(final["status"], "resolved")
        self.assertEqual(final["durationSeconds"], 1200)

    def test_replay_order_and_second_incident_have_stable_ids(self):
        history = [sample(i, i in (0, 1, 2, 5, 6, 7)) for i in range(10)]
        first = incidents.replay(history)
        self.assertEqual(first, incidents.replay(list(reversed(history))))
        self.assertEqual(len(first["incidents"]), 2)
        self.assertEqual(len({item["id"] for item in first["notifications"]}), 4)

    def test_no_attempts_unknown_differs_from_attempted_no_success(self):
        empty = incidents.sample_from_layers(timestamp(0), {name: [Series("private", 0, [])]
                                                             for name in incidents.LAYERS})
        self.assertEqual(empty["status"], "unknown")
        self.assertIsNone(empty["layers"]["internet"]["failurePct"])
        attempted = sample(1, True, failed=True)
        self.assertEqual(attempted["status"], "degraded")
        self.assertEqual(attempted["layers"]["internet"]["failed"], 20)
        self.assertEqual(attempted["layers"]["internet"]["failurePct"], 100)
        missing_counts = sample(2)
        for layer in missing_counts["layers"].values():
            layer["attempts"] = layer["failed"] = None
        self.assertEqual(incidents.replay([missing_counts])["timeline"][0]["status"], "unknown")

    def test_complete_recovery_cannot_hide_a_missing_target(self):
        incomplete = sample(3)
        incomplete["layers"]["internet"]["complete"] = False
        incomplete["layers"]["internet"]["status"] = "ok"
        history = [sample(0, True), sample(1, True), sample(2, True), incomplete, sample(4)]
        self.assertEqual(incidents.replay(history)["incidents"][0]["status"], "open")

    def test_malformed_normalized_healthy_status_cannot_hide_failed_or_absent_probes(self):
        absent = sample(3)
        for layer in absent["layers"].values():
            layer.update(attempts=0, failed=0, p50Ms=None, p95Ms=None, failurePct=0, status="ok", complete=True)
        history = [sample(0, True), sample(1, True), sample(2, True), absent, sample(4)]
        self.assertEqual(incidents.replay(history)["incidents"][0]["status"], "open")
        for layer in absent["layers"].values():
            layer.update(p50Ms=900, p95Ms=1000)
        self.assertEqual(incidents.replay([absent])["timeline"][0]["status"], "unknown")
        failed = sample(0)
        failed["layers"]["internet"].update(failed=20, failurePct=100, status="ok")
        normalized = incidents.replay([failed])["timeline"][0]
        self.assertEqual(normalized["status"], "degraded")
        invalid = sample(0)
        invalid["layers"]["internet"].update(failed=99, failurePct=495)
        normalized = incidents.replay([invalid])["timeline"][0]
        self.assertIsNone(normalized["layers"]["internet"]["failed"])
        self.assertIsNone(normalized["layers"]["internet"]["failurePct"])
        self.assertEqual(normalized["status"], "unknown")


class IncidentEvidence(unittest.TestCase):
    def test_per_target_failure_breach_survives_a_weighted_layer_ratio_at_threshold(self):
        history = []
        for index in range(3):
            layers = result().layers
            layers["internet"] = [Series("private-a", 10, [20] * 9), Series("private-b", 10, [20] * 10)]
            history.append(incidents.sample_from_layers(timestamp(index), layers))
        event, = incidents.replay(history)["incidents"]
        self.assertEqual(event["status"], "open")
        evidence = event["evidence"]["layers"]["internet"]
        self.assertEqual((evidence["attempts"], evidence["failed"], evidence["failurePct"]), (60, 3, 5))
        self.assertEqual((evidence["failureBreaches"], evidence["abnormalChecks"]), (3, 3))
        self.assertEqual(evidence["latencyBreaches"], 0)

    def test_known_target_failure_breach_survives_another_targets_missing_counts(self):
        history = []
        for index in range(3):
            row = sample(index)
            row["layers"]["internet"] = incidents.aggregate_layer("internet", [
                {"sent": 10, "loss_pct": 10, "p50_ms": 20, "p95_ms": 20},
                {"sent": None, "loss_pct": None, "p50_ms": None, "p95_ms": None},
            ], 2)
            history.append(row)
        evidence = incidents.replay(history)["incidents"][0]["evidence"]["layers"]["internet"]
        self.assertEqual((evidence["failureBreaches"], evidence["missingCountChecks"]), (3, 3))
        self.assertFalse(evidence["countsComplete"])
        self.assertIsNone(evidence["attempts"])
        self.assertIsNone(evidence["failurePct"])

    def test_weighted_failure_counts_peak_timestamp_and_healthy_gateway_exclude_recovery(self):
        history = [sample(i) for i in range(5)]
        for index, (attempts, failed, p95) in enumerate(((20, 2, 200), (10, 5, 350), (30, 3, 250))):
            history[index]["layers"]["internet"].update(attempts=attempts, failed=failed, p95Ms=p95)
        original = deepcopy(history)
        event, = incidents.replay(history)["incidents"]
        evidence = event["evidence"]
        self.assertEqual(history, original)  # replay never rewrites a saved observation
        self.assertEqual(event["status"], "resolved")
        self.assertEqual((evidence["startAt"], evidence["endAt"], evidence["checkCount"]),
                         (incidents.utc(timestamp(0)), incidents.utc(timestamp(2)), 3))
        internet = evidence["layers"]["internet"]
        self.assertEqual((internet["attempts"], internet["failed"], internet["failurePct"]), (60, 10, 16.666667))
        self.assertEqual((internet["peakP95Ms"], internet["peakP95At"]), (350, incidents.utc(timestamp(1))))
        self.assertEqual((internet["latencyThresholdMs"], internet["failureThresholdPct"]), (120, 5))
        self.assertEqual((internet["latencyBreaches"], internet["failureBreaches"]), (3, 3))
        self.assertTrue(internet["countsComplete"])
        gateway = evidence["layers"]["gateway"]
        self.assertEqual((gateway["attempts"], gateway["failed"], gateway["failurePct"]), (30, 0, 0))
        self.assertEqual((gateway["healthyChecks"], gateway["abnormalChecks"], gateway["unknownChecks"]), (3, 0, 0))
        self.assertEqual(gateway["peakP95Ms"], 2)
        self.assertEqual(set(evidence["layers"]), set(incidents.LAYERS))

    def test_unknown_within_abnormal_envelope_discloses_missing_counts_without_fabricating_failures(self):
        history = [sample(0, True), sample(1, True, missing="dns"), sample(2, True),
                   sample(3, missing="dns"), sample(4, True), sample(5), sample(6)]
        evidence = incidents.replay(history)["incidents"][0]["evidence"]
        self.assertEqual(evidence["checkCount"], 5)
        dns = evidence["layers"]["dns"]
        self.assertEqual((dns["countedChecks"], dns["missingCountChecks"], dns["countsComplete"]), (3, 2, False))
        self.assertEqual((dns["attempts"], dns["failed"], dns["failurePct"]), (60, 0, 0))
        self.assertEqual((dns["healthyChecks"], dns["unknownChecks"]), (3, 2))
        self.assertEqual(evidence["layers"]["gateway"]["healthyChecks"], 5)
        self.assertEqual(evidence["layers"]["internet"]["abnormalChecks"], 4)

    def test_p50_only_evidence_does_not_invent_p95_or_probe_counts(self):
        history = [sample(i) for i in range(3)]
        for row in history:
            row["layers"]["internet"].update(attempts=None, failed=None, p50Ms=200, p95Ms=None, complete=False)
        evidence = incidents.replay(history)["incidents"][0]["evidence"]["layers"]["internet"]
        self.assertEqual((evidence["countedChecks"], evidence["missingCountChecks"]), (0, 3))
        for key in ("attempts", "failed", "failurePct", "peakP95Ms", "peakP95At"):
            self.assertIsNone(evidence[key])
        self.assertEqual((evidence["latencyBreaches"], evidence["failureBreaches"]), (3, 0))

    def test_spikes_and_separate_events_cannot_contaminate_another_event(self):
        history = [sample(i, i in (0, 2, 3, 4, 7, 8, 9)) for i in range(12)]
        history[0]["layers"]["internet"]["p95Ms"] = 9999  # unconfirmed earlier spike
        history[8]["layers"]["internet"]["p95Ms"] = 400
        output = incidents.replay(history)
        first, second = output["incidents"]
        self.assertEqual((first["evidence"]["checkCount"], second["evidence"]["checkCount"]), (3, 3))
        self.assertEqual(first["evidence"]["layers"]["internet"]["peakP95Ms"], 200)
        self.assertEqual(second["evidence"]["layers"]["internet"]["peakP95Ms"], 400)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(output, incidents.replay(list(reversed(history)) + [history[2]]))

    def test_zero_attempts_do_not_supply_a_measured_latency_peak(self):
        history = [sample(i, True) for i in range(3)]
        for row in history:
            row["layers"]["dns"].update(attempts=0, failed=0, p50Ms=999, p95Ms=1000)
        dns = incidents.replay(history)["incidents"][0]["evidence"]["layers"]["dns"]
        self.assertEqual((dns["attempts"], dns["failed"], dns["countedChecks"]), (0, 0, 3))
        self.assertIsNone(dns["failurePct"])
        self.assertIsNone(dns["peakP95Ms"])
        self.assertEqual((dns["unknownChecks"], dns["latencyBreaches"]), (3, 0))


class IncidentPersistence(unittest.TestCase):
    def test_legacy_incident_is_enriched_without_changing_saved_samples_or_transitions(self):
        with tempfile.TemporaryDirectory() as temp:
            with closing(store.connect(Path(temp) / "home.sqlite")) as db, db:
                for index in range(5):
                    store.save_check(db, timestamp(index), result(index < 3))
                event_id, payload = db.execute("select id,payload from monitor_incidents").fetchone()
                legacy = json.loads(payload)
                del legacy["evidence"]
                db.execute("update monitor_incidents set payload=? where id=?", (json.dumps(legacy), event_id))
                db.commit()
                samples_before = db.execute("select * from monitor_samples order by at").fetchall()
                transitions_before = db.execute("select * from monitor_transitions order by id").fetchall()
                db.execute("begin immediate")
                enriched = incidents.persist(db, [])
                db.commit()
                self.assertEqual(db.execute("select * from monitor_samples order by at").fetchall(), samples_before)
                self.assertEqual(db.execute("select * from monitor_transitions order by id").fetchall(), transitions_before)
                stored = json.loads(db.execute("select payload from monitor_incidents where id=?", (event_id,)).fetchone()[0])
                self.assertEqual(stored["evidence"], enriched["incidents"][0]["evidence"])
                self.assertEqual(stored["id"], legacy["id"])
                self.assertEqual(stored["transitions"], legacy["transitions"])
                db.execute("begin immediate")
                repeated = incidents.persist(db, [sample(4)])
                db.commit()
                self.assertEqual(repeated, enriched)
                self.assertEqual(db.execute("select * from monitor_transitions order by id").fetchall(), transitions_before)

    def test_restart_replay_and_duplicate_saved_checks_do_not_duplicate_transitions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "home.sqlite"
            for index in range(6):
                with closing(store.connect(path)) as db, db:
                    store.save_check(db, timestamp(index), result(index < 3))
                    store.save_check(db, timestamp(index), result(index < 3))
            with closing(store.connect(path)) as db, db:
                self.assertEqual(db.execute("select count(*) from checks").fetchone()[0], 6)
                self.assertEqual(db.execute("select count(*) from monitor_samples").fetchone()[0], 6)
                self.assertEqual(db.execute("select count(*) from monitor_incidents").fetchone()[0], 1)
                self.assertEqual(db.execute("select count(*) from monitor_transitions").fetchone()[0], 2)
                before = db.execute("select * from monitor_transitions order by id").fetchall()
                db.execute("begin immediate")
                dashboard.from_connection(db, persist=True)
                db.commit()
                self.assertEqual(db.execute("select * from monitor_transitions order by id").fetchall(), before)

    def test_parallel_retry_writers_serialize_one_saved_check_and_one_alert(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "home.sqlite"
            with closing(store.connect(path)) as db, db:
                store.save_check(db, timestamp(0), result(True))
                store.save_check(db, timestamp(1), result(True))
            def save():
                with closing(store.connect(path)) as connection, connection:
                    store.save_check(connection, timestamp(2), result(True))
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: save(), range(4)))
            with closing(store.connect(path)) as db, db:
                self.assertEqual(db.execute("select count(*) from checks").fetchone()[0], 3)
                self.assertEqual(db.execute("select count(*) from monitor_transitions").fetchone()[0], 1)

    def test_persistence_failure_rolls_back_raw_check_and_transition(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            with closing(store.connect(Path(temp) / "home.sqlite")) as db, db:
                with patch("homenet.dashboard.from_connection", side_effect=RuntimeError("export normalization error")):
                    with self.assertRaises(RuntimeError):
                        try:
                            store.save_check(db, timestamp(0), result(True))
                        except Exception:
                            db.rollback()
                            raise
                self.assertEqual(db.execute("select count(*) from checks").fetchone()[0], 0)

    def test_persist_requires_transaction_and_rejects_mutable_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            with closing(store.connect(Path(temp) / "home.sqlite")) as db, db:
                with self.assertRaises(RuntimeError):
                    incidents.persist(db, [sample(0)])
                db.execute("begin immediate")
                incidents.persist(db, [sample(0)])
                db.commit()
                db.execute("begin immediate")
                with self.assertRaises(ValueError):
                    incidents.persist(db, [sample(0, True)])
                db.rollback()


if __name__ == "__main__":
    unittest.main()
