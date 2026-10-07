import struct
import unittest

from homenet import dns, ipv6, path
from homenet.path import Hop
from homenet.stats import Series

TRACERT = """
Tracing route to 1.1.1.1 over a maximum of 15 hops

  1   121 ms     1 ms     1 ms  10.0.0.1
  2    12 ms    10 ms    10 ms  203.0.113.9
  3     *        *        *     Request timed out.
  4    15 ms    15 ms    16 ms  1.1.1.1

Trace complete.
"""

TRACEROUTE = """traceroute to 1.1.1.1 (1.1.1.1), 30 hops max, 60 byte packets
 1  192.168.1.1  0.512 ms  0.402 ms  0.390 ms
 2  100.64.0.1  9.1 ms  9.3 ms  9.0 ms
 3  * * *
 4  1.1.1.1  15.2 ms  15.0 ms  15.1 ms
"""


def s(p50, loss=0.0, n=20):
    x = Series("t")
    lost = round(n * loss / 100)
    x.rtts = [p50] * (n - lost)
    x.sent = n
    return x


class TraceParsing(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(path.parse_traceroute(TRACERT),
                         [Hop(1, "10.0.0.1"), Hop(2, "203.0.113.9"), Hop(3, None), Hop(4, "1.1.1.1")])

    def test_linux(self):
        self.assertEqual(path.parse_traceroute(TRACEROUTE),
                         [Hop(1, "192.168.1.1"), Hop(2, "100.64.0.1"), Hop(3, None), Hop(4, "1.1.1.1")])

    def test_segments(self):
        self.assertEqual(path.segment(Hop(1, "10.0.0.1")), "home router")
        self.assertEqual(path.segment(Hop(2, "203.0.113.9")), "ISP access line")
        self.assertEqual(path.segment(Hop(2, "100.64.0.1")), "ISP (carrier NAT)")
        self.assertEqual(path.segment(Hop(5, "198.51.100.7")), "ISP / internet")
        self.assertEqual(path.segment(Hop(3, None)), "unknown")


HOPS = [Hop(1, "10.0.0.1"), Hop(2, "96.1.1.1"), Hop(3, "96.2.2.2"), Hop(4, None), Hop(5, "1.1.1.1")]


class PathAnalysis(unittest.TestCase):
    def test_finds_where_latency_is_added(self):
        v = path.analyze(HOPS, {1: s(2), 2: s(16), 3: s(17), 5: s(18)})
        self.assertEqual(v.biggest_step.hop.index, 2)
        self.assertAlmostEqual(v.biggest_step.added_ms, 14)
        self.assertIsNone(v.loss_at)
        self.assertIn("hop 2 (ISP access line): +14 ms", v.text)

    def test_a_slow_middle_hop_is_not_blamed(self):
        # Hop 3 answers its own pings slowly, but the destination is fast: deprioritized ICMP.
        v = path.analyze(HOPS, {1: s(2), 2: s(16), 3: s(80), 5: s(18)})
        hop3 = v.rows[2]
        self.assertEqual(hop3.effective_ms, 18)
        self.assertIn("slow only here", hop3.note)
        self.assertEqual(v.biggest_step.hop.index, 2)

    def test_loss_only_at_a_middle_hop_is_rate_limiting(self):
        v = path.analyze(HOPS, {1: s(2), 2: s(16), 3: s(17, loss=40), 5: s(18)})
        self.assertIsNone(v.loss_at)
        self.assertIn("rate-limited", v.rows[2].note)

    def test_loss_that_carries_through_is_reported(self):
        v = path.analyze(HOPS, {1: s(2), 2: s(16, loss=20), 3: s(17, loss=25), 5: s(18, loss=20)})
        self.assertEqual(v.loss_at.hop.index, 2)
        self.assertIn("Loss starts at hop 2", v.text)

    def test_silent_hop_is_explained(self):
        v = path.analyze(HOPS, {1: s(2), 2: s(16), 3: s(17), 5: s(18)})
        self.assertIn("silent", v.rows[3].note)
        self.assertIn("traffic still passes", v.rows[3].note)
        v2 = path.analyze([Hop(1, "10.0.0.1"), Hop(2, "96.1.1.1")], {1: s(2)})  # hop 2 traced, never pinged back
        self.assertEqual(v2.rows[1].note, "answers traceroute but not pings")

    def test_nothing_answered(self):
        v = path.analyze(HOPS, {})
        self.assertIsNone(v.biggest_step)
        self.assertIn("can't analyze", v.text)


class DnsWire(unittest.TestCase):
    def test_build_query(self):
        q = dns.build_query("zoom.us", 0x1234)
        self.assertEqual(q[:12], struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0))
        self.assertEqual(q[12:], b"\x04zoom\x02us\x00" + struct.pack("!HH", 1, 1))

    def test_parse_reply(self):
        reply = struct.pack("!HHHHHH", 0x1234, 0x8180, 1, 2, 0, 0)  # response, RD+RA, rcode 0, 2 answers
        self.assertEqual(dns.parse_reply(reply, 0x1234), (0, 2))
        nx = struct.pack("!HHHHHH", 0x1234, 0x8183, 1, 0, 0, 0)
        self.assertEqual(dns.parse_reply(nx, 0x1234), (3, 0))
        self.assertIsNone(dns.parse_reply(reply, 0x9999))  # someone else's answer
        self.assertIsNone(dns.parse_reply(struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0), 0x1234))  # a query
        self.assertIsNone(dns.parse_reply(b"short", 0x1234))


IPCONFIG = """
Windows IP Configuration

Ethernet adapter vEthernet (Default Switch):

   IPv4 Address. . . . . . . . . . . : 172.20.0.1(Preferred)
   Default Gateway . . . . . . . . . :
   DNS Servers . . . . . . . . . . . : fec0:0:0:ffff::1%1

Wireless LAN adapter Wi-Fi:

   IPv4 Address. . . . . . . . . . . : 10.0.0.50(Preferred)
   Default Gateway . . . . . . . . . : fe80::1%21
                                       10.0.0.1
   DNS Servers . . . . . . . . . . . : 2001:db8::53
                                       192.0.2.53
                                       192.0.2.54
   NetBIOS over Tcpip. . . . . . . . : Enabled
"""


class DnsServers(unittest.TestCase):
    def test_picks_the_adapter_with_an_ipv4_gateway(self):
        self.assertEqual(dns.parse_ipconfig_dns(IPCONFIG), ["2001:db8::53", "192.0.2.53", "192.0.2.54"])

    def test_no_gateway_anywhere(self):
        self.assertEqual(dns.parse_ipconfig_dns("Ethernet adapter X:\n\n   DNS Servers . . . : 1.1.1.1\n"), [])

    def test_ties(self):
        def result(label, p50):
            return dns.ResolverResult(label, "x", s(p50), s(p50))
        ranked = dns.rank([result("B", 24), result("A", 20), result("C", 31)])
        self.assertEqual([r.label for r in ranked], ["A", "B", "C"])
        self.assertEqual([r.label for r in dns.tied_with_best(ranked)], ["A", "B"])


class Ipv6Verdicts(unittest.TestCase):
    def test_pair_verdicts(self):
        self.assertEqual(ipv6.Pair("x", s(20), None).verdict, "no IPv6 address")
        self.assertEqual(ipv6.Pair("x", s(20), s(21)).verdict, "about the same")
        self.assertEqual(ipv6.Pair("x", s(20), s(35)).verdict, "IPv6 15 ms slower")
        self.assertEqual(ipv6.Pair("x", s(25), s(20)).verdict, "IPv6 5 ms faster")
        dead = Series("x")
        dead.sent = 10
        self.assertEqual(ipv6.Pair("x", s(20), dead).verdict, "IPv6 fails")

    def test_summary(self):
        self.assertIn("slower for zoom.us", ipv6.summary([ipv6.Pair("zoom.us", s(21), s(36)),
                                                           ipv6.Pair("google", s(20), s(20))]))
        dead = Series("x")
        dead.sent = 10
        self.assertIn("doesn't work", ipv6.summary([ipv6.Pair("a", s(20), dead)]))
        self.assertIn("None of the targets", ipv6.summary([ipv6.Pair("a", s(20), None)]))


if __name__ == "__main__":
    unittest.main()
