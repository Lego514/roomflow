import sqlite3
import tempfile
import unittest
from pathlib import Path

from homenet import measure, stats, store
from homenet.check import CheckResult

NETSH = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 7 BE201 320MHz
    Physical address       : aa:bb:cc:dd:ee:ff
    State                  : connected
    SSID                   : MyHomeNetwork
    BSSID                  : 11:22:33:44:55:66
    Band                   : 5 GHz
    Channel                : 44
    Radio type             : 802.11ax
    Receive rate (Mbps)    : 649
    Transmit rate (Mbps)   : 865
    Signal                 : 86%
    Rssi                   : -54
"""


class WifiParsing(unittest.TestCase):
    def test_reads_radio_facts(self):
        w = measure.parse_wifi(NETSH)
        self.assertEqual(w.state, "connected")
        self.assertEqual((w.band, w.channel, w.radio), ("5 GHz", 44, "802.11ax"))
        self.assertEqual((w.signal_pct, w.rssi_dbm), (86, -54))
        self.assertEqual((w.rx_mbps, w.tx_mbps), (649.0, 865.0))

    def test_never_keeps_names_or_addresses(self):
        w = measure.parse_wifi(NETSH)
        text = repr(w)
        for secret in ("MyHomeNetwork", "aa:bb", "11:22"):
            self.assertNotIn(secret, text)

    def test_no_wifi_interface(self):
        self.assertIsNone(measure.parse_wifi("There is no wireless interface on the system."))

    def test_disconnected(self):
        w = measure.parse_wifi("    State                  : disconnected\n")
        self.assertEqual(w.state, "disconnected")
        self.assertIsNone(w.signal_pct)


class PingAndGateway(unittest.TestCase):
    def test_parse_ping(self):
        self.assertEqual(measure.parse_ping("Reply from 1.1.1.1: bytes=32 time=17ms TTL=57"), 17.0)
        self.assertEqual(measure.parse_ping("Reply from 10.0.0.1: bytes=32 time<1ms TTL=64"), 1.0)
        self.assertEqual(measure.parse_ping("64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=16.8 ms"), 16.8)
        self.assertIsNone(measure.parse_ping("Request timed out."))
        self.assertIsNone(measure.parse_ping("Reply from 10.0.0.1: Destination host unreachable."))

    def test_parse_gateway(self):
        self.assertEqual(measure.parse_gateway("          0.0.0.0          0.0.0.0         10.0.0.1      10.0.0.23     35"),
                         "10.0.0.1")
        self.assertEqual(measure.parse_gateway("default via 192.168.1.1 dev wlan0"), "192.168.1.1")


def series(rtts, sent=None):
    s = stats.Series("t")
    s.rtts = list(rtts)
    s.sent = len(rtts) if sent is None else sent
    return s


class Stats(unittest.TestCase):
    def test_percentiles_loss_jitter(self):
        s = series([10, 20, 10, 40], sent=5)
        self.assertEqual(s.loss_pct, 20.0)
        self.assertEqual((s.p50, s.p95), (10, 40))
        self.assertAlmostEqual(s.jitter, (10 + 10 + 30) / 3)

    def test_layer_status(self):
        good = series([10] * 10)
        self.assertEqual(stats.layer_status("internet", [good]), "ok")
        self.assertEqual(stats.layer_status("internet", [series([], sent=10)]), "down")
        self.assertEqual(stats.layer_status("internet", [series([10] * 8, sent=10)]), "degraded")
        self.assertEqual(stats.layer_status("gateway", [series([5] * 9 + [80])]), "degraded")
        self.assertEqual(stats.layer_status("internet", []), "down")

    def test_wifi_status(self):
        self.assertEqual(stats.wifi_status(86, True), "ok")
        self.assertEqual(stats.wifi_status(35, True), "degraded")
        self.assertEqual(stats.wifi_status(None, False), "down")

    def test_diagnose_blames_lowest_layer(self):
        self.assertEqual(stats.diagnose({"wifi": "ok", "gateway": "ok", "internet": "ok"}), ("ok", None))
        self.assertEqual(stats.diagnose({"wifi": "degraded", "gateway": "degraded", "internet": "down"}),
                         ("degraded", "wifi"))
        self.assertEqual(stats.diagnose({"gateway": "ok", "internet": "down", "dns": "down", "service": "down"}),
                         ("down", "internet"))

    def test_bloat_grades(self):
        self.assertEqual(stats.bloat_grade(25, 40)[:2], ("A", 15))
        self.assertEqual(stats.bloat_grade(25, 120)[0], "B")
        self.assertEqual(stats.bloat_grade(25, 125)[0], "C")  # +100 ms is the first C
        self.assertEqual(stats.bloat_grade(25, 300)[0], "C")
        self.assertEqual(stats.bloat_grade(25, 1000)[0], "D")
        self.assertEqual(stats.bloat_grade(40, 30)[:2], ("A", 0.0))  # never negative
        self.assertEqual(stats.bloat_grade(None, 30)[0], "?")


class Storage(unittest.TestCase):
    def test_check_never_stores_router_address(self):
        w = measure.parse_wifi(NETSH)
        gw = series([2, 3])
        gw.target = "10.0.0.1"
        r = CheckResult(w, {"gateway": [gw], "internet": [series([20, 25])]},
                        {"wifi": "ok", "gateway": "ok", "internet": "ok"}, ("ok", None))
        with tempfile.TemporaryDirectory() as d:
            db = store.connect(Path(d) / "h.sqlite")
            store.save_check(db, "2026-10-07T00:00:00+00:00", r)
            dump = "\n".join(db.iterdump())
            db.close()
        self.assertNotIn("10.0.0.1", dump)
        self.assertNotIn("MyHomeNetwork", dump)
        self.assertIn("5 GHz", dump)


class LoggedRuns(unittest.TestCase):
    def test_output_and_errors_go_to_the_log_in_one_block(self):
        import argparse
        from homenet.__main__ import run_logged

        def ok(_):
            print("measured")
            return 0

        def boom(_):
            print("half done")
            raise RuntimeError("probe failed")

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "sub" / "homenet.log"
            self.assertEqual(run_logged(argparse.Namespace(log=log, cmd="check", fn=ok)), 0)
            self.assertEqual(run_logged(argparse.Namespace(log=log, cmd="path", fn=boom)), 1)
            text = log.read_text(encoding="utf-8")
        self.assertIn("check\nmeasured", text)
        self.assertIn("path\nhalf done", text)
        self.assertIn("RuntimeError: probe failed", text)


class Ipv6History(unittest.TestCase):
    def test_compares_only_paired_runs_and_counts_failures(self):
        with tempfile.TemporaryDirectory() as d:
            db = store.connect(Path(d) / "h.sqlite")
            rows = [
                ("t1", "zoom.us", 22.0, 21.0, "about the same"),   # quiet hour: both answer
                ("t2", "zoom.us", 200.0, None, "no IPv6 address"),  # congested: AAAA lookup failed
                ("t3", "zoom.us", 190.0, None, "IPv6 fails"),       # congested: IPv6 connect failed
                ("t4", "zoom.us", 24.0, 30.0, "IPv6 6 ms slower"),
                ("t1", "v4only.example", 20.0, None, "no IPv6 address"),
            ]
            db.executemany("insert into ipv6 values (?,?,?,?,?)", rows)
            summary = {s.target: s for s in store.ipv6_summary(db)}
            db.close()
        zoom = summary["zoom.us"]
        self.assertEqual((zoom.runs, zoom.paired, zoom.v6_failed, zoom.v6_slower), (4, 2, 2, 1))
        # Medians over paired runs only: the congested 200/190 ms runs don't make IPv6 look faster.
        self.assertEqual((zoom.v4_p50, zoom.v6_p50), (23.0, 25.5))
        v4only = summary["v4only.example"]
        self.assertEqual((v4only.paired, v4only.v6_failed), (0, 0))  # never had IPv6: not a failure


if __name__ == "__main__":
    unittest.main()
