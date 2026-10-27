"""Regression cases that previously turned incomplete probes into causal claims.

All probes are synthetic or mocked. These tests never contact a network.
"""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta
import io
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from homenet import ipv6, path, stats, store
from homenet import __main__ as cli
from homenet.check import CheckResult
from homenet.path import Hop
from homenet.stats import Series


def samples(ms, failures=0, sent=10):
    return Series("synthetic", sent, [ms] * (sent - failures))


class IncompleteRoutes(unittest.TestCase):
    def test_last_reply_is_not_a_destination_when_trace_did_not_reach_it(self):
        verdict = path.analyze([Hop(1, "10.0.0.1"), Hop(2, "203.0.113.2")],
                               {1: samples(2), 2: samples(200, failures=2)}, target="1.1.1.1")
        self.assertEqual(verdict.destination_status, "not_traced")
        self.assertIn("requested destination was not observed", verdict.text)
        self.assertIn("last replying hop 2", verdict.text)
        self.assertNotIn("end to end", verdict.text)
        self.assertNotIn("confirmed destination replied", verdict.text)

    def test_destination_seen_in_trace_but_not_echo_probes_stays_unconfirmed(self):
        hops = [Hop(1, "10.0.0.1"), Hop(2, "1.1.1.1")]
        verdict = path.analyze(hops, {1: samples(2), 2: samples(0, failures=10)}, target="1.1.1.1")
        self.assertEqual(verdict.destination_status, "no_ping_reply")
        self.assertIn("did not answer echo probes", verdict.text)
        self.assertIn("last replying hop 1", verdict.text)
        self.assertNotIn("destination replied", verdict.text)

    def test_successful_literal_destination_is_confirmed_but_link_cause_is_not(self):
        verdict = path.analyze([Hop(1, "10.0.0.1"), Hop(2, "1.1.1.1")],
                               {1: samples(2), 2: samples(200)}, target="1.1.1.1")
        self.assertEqual(verdict.destination_status, "replied")
        self.assertIn("confirmed destination replied", verdict.text)
        self.assertIn("does not identify an exact link or owner", verdict.text)
        self.assertIn("asymmetric return paths", verdict.text)
        self.assertNotIn("ISP access line", verdict.text)

    def test_omitted_target_or_hostname_never_infers_destination_or_resolves_it(self):
        hops = [Hop(1, "10.0.0.1"), Hop(2, "1.1.1.1")]
        with patch("socket.getaddrinfo", side_effect=AssertionError("unexpected DNS lookup")) as lookup:
            for target in (None, "example.com"):
                verdict = path.analyze(hops, {1: samples(2), 2: samples(20)}, target=target)
                self.assertEqual(verdict.destination_status, "unconfirmed")
                self.assertIn("Destination identity was not confirmed", verdict.text)
            lookup.assert_not_called()

    def test_isolated_probe_failures_do_not_prove_router_rate_limiting(self):
        verdict = path.analyze([Hop(1, "10.0.0.1"), Hop(2, "203.0.113.2"), Hop(3, "1.1.1.1")],
                               {1: samples(2), 2: samples(20, failures=5), 3: samples(21)}, target="1.1.1.1")
        self.assertIsNone(verdict.loss_at)
        self.assertIn("rate limiting is one possible reason", verdict.rows[1].note)
        self.assertNotIn("are rate-limited", verdict.rows[1].note)

    def test_literal_ipv6_destination_matches_canonical_address(self):
        verdict = path.analyze([Hop(1, "2001:db8::1"), Hop(2, "2606:4700:4700::1111")],
                               {1: samples(2), 2: samples(20)}, target="2606:4700:4700:0:0:0:0:1111")
        self.assertEqual(verdict.destination_status, "replied")


class Ipv6ProbeStages(unittest.TestCase):
    def test_lookup_error_is_retained_and_no_connection_is_attempted_without_address(self):
        def lookup(name, port, family, kind):
            if family == socket.AF_INET6:
                raise socket.gaierror(socket.EAI_AGAIN, "temporary resolver error")
            return [(family, kind, 6, "", ("203.0.113.2", port))]

        with patch.object(ipv6, "FIXED", []), patch.object(ipv6, "NAMES", ["example.com"]), \
                patch.object(ipv6.socket, "getaddrinfo", side_effect=lookup), \
                patch.object(ipv6.measure, "tcp_rtt", return_value=20) as connect:
            pair, = ipv6.compare(count=2)
        self.assertEqual(connect.call_count, 2)  # only the two IPv4 probes
        self.assertIsNone(pair.v6)
        self.assertIn("IPv6 address lookup unavailable", pair.verdict)
        self.assertIn("temporary resolver error", pair.verdict)
        self.assertNotIn("IPv6 TCP probes had no successful connections", pair.verdict)
        summary = ipv6.summary([pair])
        self.assertIn("No IPv6 TCP probe results", summary)
        self.assertNotIn("Apps fall back", summary)

    def test_tcp_failure_does_not_claim_all_ipv6_or_application_fallback_failed(self):
        pair = ipv6.Pair("one target", samples(20), samples(0, failures=10))
        self.assertEqual(pair.verdict, "IPv6 TCP probes had no successful connections")
        summary = ipv6.summary([pair])
        self.assertIn("0/1 tested targets", summary)
        self.assertIn("do not establish network-wide IPv6 availability", summary)
        self.assertNotIn("IPv6 doesn't work from here", summary)
        self.assertNotIn("Apps fall back", summary)

    def test_no_paired_targets_does_not_claim_ipv6_is_not_slower(self):
        summary = ipv6.summary([ipv6.Pair("one target", samples(0, failures=10), samples(20))])
        self.assertIn("1/1 tested targets", summary)
        self.assertNotIn("higher for none", summary)
        self.assertNotIn("isn't slower", summary)

    def test_empty_series_is_not_an_observed_connection_failure(self):
        pair = ipv6.Pair("one target", samples(20), Series("synthetic"))
        self.assertEqual(pair.verdict, "no IPv6 TCP probes recorded")


class HistoricalObservationLimits(unittest.TestCase):
    def test_cli_history_never_recasts_an_old_partial_trace_as_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "history.sqlite"
            db = store.connect(db_path)
            db.execute("insert into trace values (?,?,?,?,?,?,?,?,?)",
                       ("t", "1.1.1.1", 2, "ISP access line", 0, 200, 200, 200, ""))
            db.commit()
            db.close()
            out = io.StringIO()
            with patch.object(cli, "DB", db_path), redirect_stdout(out):
                self.assertEqual(cli.cmd_report(argparse.Namespace()), 0)
        self.assertIn("last-reply ICMP RTT", out.getvalue())
        self.assertIn("History does not establish destination confirmation", out.getvalue())
        self.assertNotIn("ms end to end", out.getvalue())
        self.assertNotIn("ISP access line", out.getvalue())

    def test_zero_probe_rows_are_not_failures_or_evidence_of_historical_ipv6_probes(self):
        with tempfile.TemporaryDirectory() as temp:
            db = store.connect(Path(temp) / "history.sqlite")
            rows = [("2026-10-01T00:00:00+00:00", "target", 20, None, "no IPv6 TCP probes recorded"),
                    ("2026-10-01T00:05:00+00:00", "target", 20, None, "no IPv6 address")]
            db.executemany("insert into ipv6 values (?,?,?,?,?)", rows)
            item, = store.ipv6_summary(db)
            self.assertEqual((item.v6_failed, item.v6_unclassified), (0, 0))
            self.assertEqual([missing for _, missing in store.ipv6_runs(db)], [False, False])
            # A separate successful IPv6 observation still must not turn the
            # explicit zero-probe row into a connection failure.
            store.save_ipv6(db, "2026-10-01T00:10:00+00:00", [ipv6.Pair("target", samples(20), samples(20))])
            item, = store.ipv6_summary(db)
            self.assertEqual((item.v6_failed, item.v6_unclassified), (1, 1))
            self.assertFalse(store.ipv6_runs(db)[0][1])
            db.close()

    def test_legacy_ipv6_ambiguity_and_new_stages_survive_history_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temp:
            db = store.connect(Path(temp) / "history.sqlite")
            original = [
                ("2026-10-01T00:00:00+00:00", "target", 20, 21, "about the same"),
                ("2026-10-01T00:05:00+00:00", "target", 200, None, "no IPv6 address"),
            ]
            db.executemany("insert into ipv6 values (?,?,?,?,?)", original)
            store.save_ipv6(db, "2026-10-01T00:10:00+00:00", [
                ipv6.Pair("target", samples(200), None, v6_resolution_error="resolver error")])
            store.save_ipv6(db, "2026-10-01T00:15:00+00:00", [
                ipv6.Pair("target", samples(200), samples(0, failures=10))])
            item, = store.ipv6_summary(db)
            self.assertEqual((item.v6_failed, item.v6_lookup_unavailable, item.v6_tcp_failed, item.v6_unclassified),
                             (3, 1, 1, 1))
            self.assertEqual(db.execute("select * from ipv6 order by at limit 2").fetchall(), original)
            db.close()

    def test_run_failure_is_an_any_target_observation_not_all_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            db = store.connect(Path(temp) / "history.sqlite")
            at = "2026-10-01T00:05:00+00:00"
            store.save_ipv6(db, at, [ipv6.Pair("good", samples(20), samples(20)),
                                     ipv6.Pair("bad", samples(20), samples(0, failures=10))])
            run, = store.ipv6_runs(db)
            self.assertTrue(run[1])
            items = {s.target: s for s in store.ipv6_summary(db)}
            self.assertEqual((items["good"].v6_failed, items["bad"].v6_failed), (0, 1))
            db.close()
        start = datetime(2026, 10, 1)
        timeline = [(start + timedelta(minutes=5 * i), 2, rtt) for i, rtt in enumerate((20, 200, 200, 20, 20))]
        out = io.StringIO()
        with redirect_stdout(out):
            cli.print_slow_periods(timeline, [], [(start + timedelta(minutes=5), True)])
        self.assertIn("At least one target", out.getvalue())
        self.assertIn("run-level association", out.getvalue())
        self.assertNotIn("IPv6 failed in", out.getvalue())

    def test_old_trace_labels_are_softened_on_read_without_mutating_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            db = store.connect(Path(temp) / "history.sqlite")
            rows = [("t", "1.1.1.1", 1, "home router", 0, 2, 2, 2, ""),
                    ("t", "1.1.1.1", 2, "ISP access line", 0, 200, 200, 198, "")]
            db.executemany("insert into trace values (?,?,?,?,?,?,?,?,?)", rows)
            result = store.trace_summary(db)
            self.assertEqual(result, (1, 200, "early upstream hop", 1, 198))
            self.assertEqual(db.execute("select * from trace order by hop").fetchall(), rows)
            db.close()


class ObservationFlags(unittest.TestCase):
    def test_good_gateway_bad_external_probes_do_not_name_isp_as_root_cause(self):
        result = CheckResult(None, {"gateway": [samples(2)], "internet": [samples(200)]},
                             {"gateway": "ok", "internet": "degraded"}, ("degraded", "internet"))
        out = io.StringIO()
        with redirect_stdout(out):
            cli.print_check(result)
        self.assertIn("first flagged observation", out.getvalue())
        self.assertIn("before assigning a cause", out.getvalue())
        self.assertNotIn("likely the ISP", out.getvalue())
        self.assertNotIn("The router is fine", out.getvalue())

    def test_passing_selected_probes_does_not_certify_network_or_call(self):
        result = CheckResult(None, {}, {}, ("ok", None))
        out = io.StringIO()
        with redirect_stdout(out):
            cli.print_check(result)
        self.assertIn("selected probes", out.getvalue())
        self.assertNotIn("all layers ok", out.getvalue())

    def test_load_grade_does_not_predict_a_real_call_stutter_or_queue_location(self):
        for loaded in (40, 90, 200, 1000):
            grade, added, meaning = stats.bloat_grade(20, loaded)
            self.assertIn("probe latency under load", meaning)
            self.assertNotIn("calls", meaning)
            self.assertNotIn("queue", meaning)


if __name__ == "__main__":
    unittest.main()
