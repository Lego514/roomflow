"""Portable regression tests for safety/measurement logic; no kernel claims."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import netlab
import session


class CommandPlanTests(unittest.TestCase):
    def test_prerequisite_probe_deletes_htb_before_cake(self):
        def fake_run(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout="iperf 3.22\n-D timestamp option", stderr="-D timestamp option")
        with patch.object(netlab, "guard_linux"), patch.object(netlab.shutil, "which", return_value="/usr/bin/tool"), patch.object(netlab.os, "uname", return_value=SimpleNamespace(release="test-kernel"), create=True), patch.object(netlab, "run", side_effect=fake_run) as command:
            netlab.prerequisite_check()
        args = [call.args for call in command.call_args_list]
        htb = next(i for i, value in enumerate(args) if "htb" in value and "qdisc" in value)
        cake = next(i for i, value in enumerate(args) if "cake" in value)
        deletes = [i for i, value in enumerate(args) if "qdisc" in value and "del" in value]
        self.assertTrue(any(htb < index < cake for index in deletes))

    def test_same_bandwidth_in_all_modes(self):
        for mbps in (5, 20, 7.5):
            for mode in netlab.MODES:
                commands = netlab.shaping_commands(mode, "wan", mbps, "src_ip", "mlan", 40)
                self.assertIn(f"{mbps:g}mbit", [arg for command in commands for arg in command])

    def test_fifo_is_one_htb_class_and_fifo_queue(self):
        commands = netlab.shaping_commands("fifo", "wan", 5, "src_ip", "mlan", 40)
        self.assertEqual(len(commands), 3)
        self.assertIn("htb", commands[0])
        self.assertIn("pfifo", commands[2])
        self.assertNotIn("netem", str(commands))

    def test_fifo_buffer_holds_the_configured_milliseconds(self):
        def limit(mbps, **kwargs):
            return int(netlab.shaping_commands("fifo", "wan", mbps, "src_ip", "mlan", 40, **kwargs)[2][-1])
        self.assertEqual(limit(20), 500)  # default 300 ms: 20 Mbit/s * 0.3 s / 1500 B
        self.assertEqual(limit(250, fifo_ms=180), 3750)  # the home line: 250 Mbit/s * 0.18 s / 1500 B
        self.assertEqual(limit(0.5, fifo_ms=20), 20)  # never below 20 packets
        with self.assertRaises(netlab.LabError):
            netlab.shaping_commands("fifo", "wan", 20, "src_ip", "mlan", 40, fifo_ms=5000)

    def test_selected_priority_requires_ingress_and_source(self):
        commands = netlab.shaping_commands("meeting", "wan", 5, "src_ip", "mlan", 40)
        self.assertIn("indev", commands[1])
        self.assertIn("mlan", commands[1])
        self.assertIn("10.77.1.2/32", commands[1])
        self.assertIn("1:4", commands[1])
        self.assertIn("1:2", commands[2])
        self.assertIn("wash", commands[0])

    def test_downstream_has_shared_destination_classification(self):
        commands = netlab.shaping_commands("meeting", "torouter", 20, "dst_ip", None, 40)
        self.assertIn("dual-dsthost", commands[0])
        self.assertIn("dst_ip", commands[1])
        self.assertNotIn("indev", commands[1])

    def test_invalid_configuration_rejected_before_commands(self):
        for mode, capacity, rtt in (("unknown", 5, 40), ("fifo", -5, 40), ("meeting", 5, 0)):
            with self.assertRaises(netlab.LabError):
                netlab.shaping_commands(mode, "wan", capacity, "src_ip", "mlan", rtt)

    def test_both_clients_have_one_shared_bottleneck_each_direction(self):
        self.assertEqual(len(netlab.SHAPERS), 2)
        self.assertEqual(netlab.SHAPERS[0][:2], ("router", "wan"))
        self.assertEqual(netlab.SHAPERS[1][:2], ("delay", "torouter"))
        self.assertTrue(all(name.startswith("nc-lab-") for name in netlab.NAMES.values()))


class MeasurementTests(unittest.TestCase):
    def test_warmup_excluded_and_p95_nearest_rank(self):
        raw = "\n".join(f"[{100 + i}.0] 64 bytes time={i + 1}.0 ms" for i in range(20))
        raw += "\n20 packets transmitted, 20 received, 0% packet loss"
        result = netlab.ping_summary(raw, 105)
        self.assertEqual(result["samples"], 15)
        self.assertEqual(result["p95_ms"], 20)
        self.assertEqual(result["mean_ms"], 13)
        self.assertEqual(result["ping_loss_including_warmup_pct"], 0)

    def test_zero_replies_not_reported_as_zero_latency(self):
        result = netlab.ping_summary("10 packets transmitted, 0 received, 100% packet loss", 0)
        self.assertIsNone(result["p95_ms"])
        self.assertEqual(result["samples"], 0)
        self.assertEqual(result["ping_loss_including_warmup_pct"], 100)

    def test_udp_receiver_metrics_kept(self):
        result = netlab.receive_summary({"end": {"sum": {"bits_per_second": 570000, "jitter_ms": 2.5,
                                                     "lost_packets": 4, "packets": 100, "lost_percent": 4}}}, True)
        self.assertEqual(result["lost_percent"], 4)
        self.assertEqual(result["jitter_ms"], 2.5)

    def test_cpu_percent(self):
        self.assertEqual(netlab.cpu_usage({"cpu0": (100, 30)}, {"cpu0": (200, 50)})["cpu0"], 80)

    def test_scenarios_share_two_meeting_flows(self):
        for scenario in netlab.SCENARIOS:
            specs = netlab.flow_specs(scenario)
            self.assertEqual(specs[0][0], "meeting-up")
            self.assertEqual(specs[1][0], "meeting-down")
        self.assertEqual(len(netlab.flow_specs("idle")), 2)
        self.assertEqual(len(netlab.flow_specs("both")), 4)


class SafetyTests(unittest.TestCase):
    def test_failed_readback_rolls_back_both_directions(self):
        state = {"mode": "sqm", "up_mbps": 5, "down_mbps": 20, "rtt_ms": 40}
        with patch.object(netlab, "assert_owned"), patch.object(netlab, "ns") as command, patch.object(netlab, "save_state"), patch.object(netlab, "verify_mode", side_effect=[netlab.LabError("bad classification"), None]) as verify:
            with self.assertRaises(netlab.LabError):
                netlab.set_mode(state, "meeting")
            cakes = [call.args for call in command.call_args_list if "cake" in call.args]
            self.assertEqual(len(cakes), 4)
            self.assertEqual(sum("besteffort" in args for args in cakes), 2)
            self.assertEqual(state["mode"], "sqm")
            self.assertEqual(verify.call_args.args[1], "sqm")

    def test_failed_rollback_records_unknown_mode(self):
        state = {"mode": "sqm", "up_mbps": 5, "down_mbps": 20, "rtt_ms": 40}
        with patch.object(netlab, "assert_owned"), patch.object(netlab, "ns"), patch.object(netlab, "save_state") as save, patch.object(netlab, "verify_mode", side_effect=netlab.LabError("readback unavailable")):
            with self.assertRaises(netlab.LabError):
                netlab.set_mode(state, "meeting")
            self.assertEqual(state["mode"], "unknown")
            save.assert_called_once_with(state)

    def test_foreign_marker_refuses_teardown_without_deleting(self):
        state = {"created": ["meeting"], "token": "a" * 32}
        fake = SimpleNamespace(stdout=json.dumps([{"ifname": "lo", "ifalias": "foreign"}]))
        with patch.object(netlab, "existing_names", return_value={netlab.NAMES["meeting"]}), patch.object(netlab, "run", return_value=fake) as command:
            with self.assertRaises(netlab.LabError):
                netlab.teardown(state)
            self.assertEqual(command.call_count, 1)
            self.assertNotIn("delete", command.call_args.args)

    def test_restore_failure_preserves_session_for_retry(self):
        value = {"baseline_mode": "sqm", "active": True}
        with patch.object(netlab, "set_mode", side_effect=netlab.LabError("readback failed")), patch.object(session, "write_session") as write, patch.object(session, "record_event") as event:
            with self.assertRaises(netlab.LabError):
                session.restore({}, value, "expired")
            self.assertTrue(value["active"])
            write.assert_not_called()
            self.assertEqual(event.call_args.args[0], "restore-failed")

    def test_expired_session_reconciles_to_baseline(self):
        value = {"baseline_mode": "fifo", "active": True, "expires_at": 10}
        with patch.object(session.time, "time", return_value=11), patch.object(session, "restore", return_value={"restored": True}) as restore:
            result = session.reconcile({}, value)
            restore.assert_called_once_with({}, value, "expired")
            self.assertTrue(result["restored"])

    def test_active_session_requires_actual_meeting_readback(self):
        value = {"active": True, "expires_at": 100}
        with patch.object(session.time, "time", return_value=10), patch.object(netlab, "verify_mode", side_effect=netlab.LabError("wrong qdisc")):
            with self.assertRaises(netlab.LabError):
                session.reconcile({}, value)


if __name__ == "__main__":
    unittest.main()
