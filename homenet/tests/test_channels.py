import unittest

from homenet import channels, measure
from homenet.channels import ChannelStat, count_by_channel
from homenet.measure import Bss

SCAN = """
SSID 1 : NeighborOne
    Network type            : Infrastructure
    BSSID 1                 : aa:aa:aa:aa:aa:01
         Signal             : 22%
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 157
         Bss Load:
             Connected Stations:         0
             Channel Utilization:        107 (41 %)
    BSSID 2                 : aa:aa:aa:aa:aa:02
         Signal             : 46%
         Radio type         : 802.11be
         Band               : 5 GHz
         Channel            : 40
SSID 2 : NeighborTwo
    BSSID 1                 : bb:bb:bb:bb:bb:01
         Signal             : 60%
         Radio type         : 802.11ax
         Band               : 2.4 GHz
         Channel            : 1
         Colocated APs:    : 3
            BSSID: cc:cc:cc:cc:cc:03,  Band: 6 GHz,  Channel: 69
"""


def ap(band, channel, signal, util=None):
    return Bss(band=band, channel=channel, signal_pct=signal, radio="802.11ax", utilization_pct=util, stations=None)


class ScanParsing(unittest.TestCase):
    def test_reads_each_access_point(self):
        found = measure.parse_bss(SCAN)
        self.assertEqual([(b.band, b.channel, b.signal_pct) for b in found],
                         [("5 GHz", 157, 22), ("5 GHz", 40, 46), ("2.4 GHz", 1, 60)])
        self.assertEqual(found[0].utilization_pct, 41)
        self.assertIsNone(found[1].utilization_pct)

    def test_never_keeps_names_or_addresses(self):
        text = repr(measure.parse_bss(SCAN, own_bssid="aa:aa:aa:aa:aa:09"))
        for secret in ("Neighbor", "aa:aa", "bb:bb", "cc:cc"):
            self.assertNotIn(secret, text)

    def test_marks_our_own_router(self):
        # Our router broadcasts aa:aa:aa:aa:aa:01 and :02 (two networks, one box).
        found = measure.parse_bss(SCAN, own_bssid="AA:AA:AA:AA:AA:01")
        self.assertEqual([b.own for b in found], [True, True, False])
        self.assertEqual([b.own for b in measure.parse_bss(SCAN)], [False, False, False])

    def test_connected_bssid(self):
        out = "    SSID                   : Home\n    BSSID                  : aa:aa:aa:aa:aa:01\n"
        self.assertEqual(measure.connected_bssid(out), "aa:aa:aa:aa:aa:01")
        win11 = "    SSID                   : Home\n    AP BSSID               : aa:aa:aa:aa:aa:01\n"
        self.assertEqual(measure.connected_bssid(win11), "aa:aa:aa:aa:aa:01")
        self.assertIsNone(measure.connected_bssid("    State : disconnected\n"))

    def test_same_radio(self):
        self.assertTrue(measure.same_radio("aa:aa:aa:aa:aa:01", "AA:AA:AA:AA:AA:7F"))
        # A virtual network with the locally-administered bit set in the first byte.
        self.assertTrue(measure.same_radio("a8:aa:aa:aa:aa:01", "aa:aa:aa:aa:aa:05"))
        self.assertFalse(measure.same_radio("aa:aa:aa:aa:ab:01", "aa:aa:aa:aa:aa:01"))
        self.assertFalse(measure.same_radio("aa:aa:aa:aa:aa:01", None))
        self.assertFalse(measure.same_radio("not-a-mac", "not-a-mac"))


# --- count_by_channel ------------------------------------------------------------------


class CountByChannel(unittest.TestCase):
    def test_empty_scan(self):
        self.assertEqual(count_by_channel([]), {})

    def test_one_access_point(self):
        self.assertEqual(count_by_channel([ap("5 GHz", 44, 22)]), {("5 GHz", 44): ChannelStat(1, 22)})

    def test_counts_and_keeps_the_strongest(self):
        result = count_by_channel([ap("5 GHz", 44, 22), ap("5 GHz", 44, 70), ap("5 GHz", 44, 35)])
        self.assertEqual(result[("5 GHz", 44)], ChannelStat(count=3, strongest=70))

    def test_same_channel_number_on_different_bands_is_different(self):
        # Channel 1 exists in 2.4 GHz and in 6 GHz; they don't interfere.
        result = count_by_channel([ap("2.4 GHz", 1, 60), ap("6 GHz", 1, 30)])
        self.assertEqual(result, {("2.4 GHz", 1): ChannelStat(1, 60), ("6 GHz", 1): ChannelStat(1, 30)})

    def test_skips_unknown_band_or_channel(self):
        result = count_by_channel([ap(None, 44, 50), ap("5 GHz", None, 50), ap("5 GHz", 36, 10)])
        self.assertEqual(result, {("5 GHz", 36): ChannelStat(1, 10)})

    def test_missing_signal_counts_but_does_not_change_strongest(self):
        result = count_by_channel([ap("5 GHz", 44, None), ap("5 GHz", 44, 15)])
        self.assertEqual(result[("5 GHz", 44)], ChannelStat(count=2, strongest=15))


# --- Built on top of it -------------------------------------------------------------


class Blocks(unittest.TestCase):
    def test_block_of(self):
        self.assertEqual(channels.block_of(44), (36, 40, 44, 48))
        self.assertEqual(channels.block_of(157), (149, 153, 157, 161))
        self.assertIsNone(channels.block_of(165))

    def test_quietest_block_first_and_dfs_loses_ties(self):
        stats = {("5 GHz", 44): ChannelStat(3, 70), ("5 GHz", 157): ChannelStat(5, 20)}
        loads = channels.block_loads(stats)
        # Empty non-DFS blocks don't exist besides 36-48 and 149-161, so the empty DFS blocks come first.
        self.assertEqual(loads[0].strongest, 0)
        self.assertTrue(loads[0].dfs)
        ranked = [b.block[0] for b in loads if b.count]
        self.assertEqual(ranked, [149, 36])  # weaker strongest neighbor wins over fewer neighbors

    def test_advice_ignores_our_own_router(self):
        mine = Bss("5 GHz", 44, 88, "802.11ax", None, None, own=True)
        aps = [mine, ap("5 GHz", 40, 20), ap("5 GHz", 157, 60)]
        advice = channels.advise(aps, "5 GHz", 44)
        self.assertEqual((advice.my_block.count, advice.my_block.strongest), (1, 20))

    def test_utilization_on_my_channel(self):
        aps = [ap("5 GHz", 44, 22, util=39), ap("5 GHz", 44, 30, util=12), ap("5 GHz", 40, 46, util=80)]
        self.assertEqual(channels.utilization_on(aps, "5 GHz", 44), 39)
        self.assertIsNone(channels.utilization_on(aps, "5 GHz", 36))


if __name__ == "__main__":
    unittest.main()
