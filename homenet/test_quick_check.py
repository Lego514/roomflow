"""Quick-check translation tests: synthetic samples, never network probes."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import json

from homenet.check import CheckResult
from homenet.stats import Series

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("quick_check_bridge", ROOT / "scripts" / "quick-check.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def series(values):
    result = Series("192.0.2.99")
    for value in values:
        result.add(value)
    return result


def healthy():
    names = ("gateway", "internet", "dns", "service")
    return CheckResult(None, {name: [series([10, 11, 12])] for name in names},
                       {name: "ok" for name in names}, ("ok", None))


class QuickCheckBridgeTests(unittest.TestCase):
    def summarize(self, result):
        return bridge.summarize(result, "2026-10-27T05:00:00.000Z")

    def test_no_attempts_are_unknown_rather_than_an_outage_or_success(self):
        result = healthy()
        result.layers = {name: [] for name in result.layers}
        result.statuses = {name: "down" for name in result.statuses}
        summary = self.summarize(result)
        self.assertEqual(summary["overall"], "unknown")
        self.assertTrue(all(row["status"] == "unknown" for row in summary["layers"]))
        self.assertTrue(all(row["p95Ms"] is None for row in summary["layers"]))

    def test_actual_unsuccessful_attempts_are_attention(self):
        result = healthy()
        result.layers["internet"] = [series([None, None, None])]
        result.statuses["internet"] = "down"
        summary = self.summarize(result)
        self.assertEqual(summary["overall"], "attention")
        self.assertEqual(summary["layers"][1], {"id": "internet", "status": "attention",
                         "p95Ms": None, "attempts": 3, "failed": 3})

    def test_wifi_without_a_signal_is_unknown_but_disconnected_is_attention(self):
        result = healthy()
        result.wifi = SimpleNamespace(signal_pct=None, ssid="private-ssid", state="connected")
        result.statuses["wifi"] = "ok"
        self.assertEqual(self.summarize(result)["wifi"]["status"], "unknown")
        self.assertEqual(self.summarize(result)["overall"], "unknown")
        result.statuses["wifi"] = "down"
        self.assertEqual(self.summarize(result)["wifi"]["status"], "attention")

    def test_export_has_no_target_ip_ssid_or_private_properties(self):
        result = healthy()
        result.wifi = SimpleNamespace(signal_pct=90, ssid="private-ssid", state="connected")
        result.statuses["wifi"] = "ok"
        payload = json.dumps(self.summarize(result))
        self.assertNotIn("192.0.2.99", payload)
        self.assertNotIn("private-ssid", payload)
        self.assertNotIn('"target"', payload)
        self.assertNotIn('"ssid"', payload)

    def test_peak_is_maximum_of_target_p95_not_a_pooled_percentile(self):
        result = healthy()
        result.layers["internet"] = [series([1, 2, 3]), series([20, 30, 40])]
        summary = self.summarize(result)
        self.assertEqual(summary["layers"][1]["p95Ms"], 40)
        self.assertEqual(summary["layers"][1]["attempts"], 6)
        self.assertEqual(summary["p95Basis"], "maximum-target-p95")

    def test_history_error_keeps_useful_result_and_hides_exception(self):
        with patch.object(bridge, "run_check", return_value=healthy()) as collect, \
             patch.object(bridge.store, "connect", side_effect=OSError("C:/private/secret")):
            summary = bridge.collect(ROOT / "data")
        collect.assert_called_once_with(count=3)
        self.assertEqual(summary["overall"], "ok")
        self.assertFalse(summary["historySaved"])
        self.assertNotIn("private", json.dumps(summary))

    def test_save_and_export_use_existing_history_and_transaction_methods(self):
        db = Mock()
        with patch.object(bridge, "run_check", return_value=healthy()), \
             patch.object(bridge.store, "connect", return_value=db), \
             patch.object(bridge.store, "save_check") as save, \
             patch.object(bridge.dashboard, "from_connection", return_value={"sample": "saved"}), \
             patch.object(bridge.dashboard, "atomic_export") as export:
            summary = bridge.collect(ROOT / "data")
        self.assertTrue(summary["historySaved"])
        save.assert_called_once()
        db.execute.assert_called_once_with("begin immediate")
        export.assert_called_once_with({"sample": "saved"}, ROOT / "data" / "observations.json")
        db.commit.assert_called_once()
        db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
