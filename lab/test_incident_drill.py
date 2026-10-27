"""Portable checks for drill evidence interpretation; these do not run a packet lab.

The separate incident-drills CI job actually injects Linux faults and asserts
their measurements, incident transitions and cleanup. No mocked subprocess is
used as evidence that packets traversed a network.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import incident_drill as drill
from homenet.dashboard import build_dashboard


def observations(scenario):
    records = []
    for index in range(7):
        phase = "baseline" if index < 2 else "fault" if index < 5 else "recovery"
        affected = ("dns",) if scenario == "dns" else ("internet", "dns", "service")
        layers = {}
        for name in drill.LAYERS:
            abnormal = phase == "fault" and name in affected
            failed = abnormal and scenario != "delay"
            ms = 700 if abnormal else 0.5
            attempts = [{"ok": not failed, "elapsedMs": 1200 if failed else ms} for _ in range(2)]
            layers[name] = drill.layer_from_attempts(attempts, name)
        at = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index * 10)).isoformat()
        records.append({"phase": phase, "sample": {"at": at, "status": "degraded" if phase == "fault" else "ok", "layers": layers}})
    return {"measurements": records, "cleanup": {"namespacesAbsent": True, "errors": []}}


class EvidenceInterpretationTests(unittest.TestCase):
    def test_all_failed_probes_have_no_success_latency(self):
        layer = drill.layer_from_attempts([{"ok": False, "elapsedMs": 1200}] * 2, "dns")
        self.assertEqual((layer["attempts"], layer["failed"], layer["failurePct"]), (2, 2, 100))
        self.assertIsNone(layer["p50Ms"])
        self.assertIsNone(layer["p95Ms"])
        self.assertEqual(layer["flags"], ["unsuccessful-probes"])

    def test_timeout_elapsed_does_not_pollute_success_percentiles(self):
        layer = drill.layer_from_attempts([{"ok": True, "elapsedMs": 10}, {"ok": False, "elapsedMs": 1200}], "internet")
        self.assertEqual((layer["p50Ms"], layer["p95Ms"]), (10, 10))
        self.assertEqual(layer["failurePct"], 50)

    def test_thresholds_match_monitor_policy_by_layer(self):
        attempt = [{"ok": True, "elapsedMs": 150}]
        self.assertEqual(drill.layer_from_attempts(attempt, "internet")["status"], "degraded")
        self.assertEqual(drill.layer_from_attempts(attempt, "dns")["status"], "ok")
        empty = drill.layer_from_attempts([], "dns")
        self.assertEqual(empty["status"], "unknown")
        self.assertIsNone(empty["failurePct"])

    def test_dns_requires_matching_transaction_and_complete_expected_answer(self):
        answer = drill.dns_answer(drill.dns_query(1234))
        self.assertTrue(drill.valid_dns_answer(answer, 1234))
        self.assertFalse(drill.valid_dns_answer(answer, 1235))
        self.assertFalse(drill.valid_dns_answer(answer[:12], 1234))
        self.assertFalse(drill.valid_dns_answer(answer[:-1] + b"\xff", 1234))

    def test_truth_labels_cannot_replace_observed_faults(self):
        evidence = observations("dns")
        evidence["measurements"][2]["sample"]["layers"]["dns"] = drill.layer_from_attempts([{"ok": True, "elapsedMs": 1}], "dns")
        with self.assertRaisesRegex(drill.DrillError, "not observed"):
            drill.audit_measurements("dns", evidence)

    def test_cleanup_failure_invalidates_otherwise_good_evidence(self):
        evidence = observations("loss")
        evidence["cleanup"]["namespacesAbsent"] = False
        with self.assertRaisesRegex(drill.DrillError, "cleanup"):
            drill.audit_measurements("loss", evidence)

    def test_drill_contract_replays_all_scenarios_into_one_resolved_incident(self):
        for scenario in drill.SCENARIOS:
            with self.subTest(scenario=scenario):
                evidence = observations(scenario)
                drill.audit_measurements(scenario, evidence)
                samples = [record["sample"] for record in evidence["measurements"]]
                payload = build_dashboard(samples, source_kind="lab-drill")
                drill.audit_incidents(scenario, samples, payload)
                duplicated = deepcopy(payload)
                duplicated["notifications"].insert(1, duplicated["notifications"][0])
                with self.assertRaisesRegex(drill.DrillError, "exactly one"):
                    drill.audit_incidents(scenario, samples, duplicated)


if __name__ == "__main__":
    unittest.main()
