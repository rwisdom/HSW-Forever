import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/Util.lua", "Classes/Segment.lua"]
SETUP = """
HSW_TEST_ADDON.ManaPerInt = 15
HSW_TEST_ADDON.FSR_SECONDS = 5
HSW_TEST_ADDON.HasteConv = 100
HSW_TEST_ADDON.RegenPerSpirit = 0.1
HSW_TEST_ADDON.ply_intmult = 1
HSW_TEST_ADDON.ply_spiritmult = 1
HSW_TEST_ADDON.ply_castpct = 0
HSW_TEST_ADDON.ply_hst = 0
"""


class SegmentTests(unittest.TestCase):
    def seg(self, extra=""):
        lua, addon = load(FILES, setup=SETUP + extra)
        return lua, addon, addon.Segment.Create("test")

    def test_mp5_and_int_mana(self):
        lua, addon, s = self.seg()
        s.IncFillerHealing(s, 1000)
        s.IncFillerCasts(s, 200)
        lua.execute("STUB.time = 100")
        self.assertAlmostEqual(s.GetFillerHPM(s), 5.0)
        self.assertAlmostEqual(s.GetMP5(s), 100.0)          # 100s/5 * 5 healing per mana
        self.assertAlmostEqual(s.GetIntManaValue(s), 75.0)  # 15 mana * HPM 5
        addon.ply_intmult = 1.1
        self.assertAlmostEqual(s.GetIntManaValue(s), 82.5)

    def test_no_filler_means_zero(self):
        _, _, s = self.seg()
        self.assertEqual(s.GetMP5(s), 0)
        self.assertEqual(s.GetIntManaValue(s), 0)
        self.assertEqual(s.GetSpiritRegenValue(s), 0)

    def test_fsr_split(self):
        _, addon, s = self.seg()
        addon.lastManaSpend = 0
        s.AccumulateFSR(s, 8)
        self.assertAlmostEqual(s.timeInFSR, 5)
        self.assertAlmostEqual(s.timeOutsideFSR, 3)
        s.AccumulateFSR(s, 10)                      # 8..10 is all outside the FSR
        self.assertAlmostEqual(s.timeInFSR, 5)
        self.assertAlmostEqual(s.timeOutsideFSR, 5)
        s.AccumulateFSR(s, 9)                       # going backwards is ignored
        self.assertAlmostEqual(s.timeOutsideFSR, 5)

    def test_fsr_without_any_spend_is_all_outside(self):
        _, _, s = self.seg()
        s.AccumulateFSR(s, 7)
        self.assertEqual(s.timeInFSR, 0)
        self.assertAlmostEqual(s.timeOutsideFSR, 7)

    def test_spirit_regen_value(self):
        _, addon, s = self.seg()
        s.IncFillerHealing(s, 1000); s.IncFillerCasts(s, 200)   # HPM 5
        addon.lastManaSpend = 0
        addon.ply_castpct = 0.5
        s.AccumulateFSR(s, 10)                      # 5 in (at 50%) + 5 out -> 7.5 effective seconds
        self.assertAlmostEqual(s.GetSpiritRegenValue(s), 0.1 * 1 * 7.5 * 5)
        addon.ply_spiritmult = 1.15
        self.assertAlmostEqual(s.GetSpiritRegenValue(s), 0.1 * 1.15 * 7.5 * 5)

    def test_cast_pct_is_time_weighted(self):
        _, addon, s = self.seg()
        addon.ply_castpct = 1.0; s.AccumulateFSR(s, 2)
        addon.ply_castpct = 0.0; s.AccumulateFSR(s, 4)
        self.assertAlmostEqual(s.castPctWeighted / (s.timeInFSR + s.timeOutsideFSR), 0.5)

    def test_allocate_and_merge(self):
        lua, addon, s = self.seg()
        s.AllocateHeal(s, 1, 2, 3, 4, 5, 123)
        self.assertEqual((s.t.heal, s.t.crit, s.t.haste_hpct, s.t.int, s.t.spirit), (1, 2, 3, 4, 5))
        other = addon.Segment.Create("o")
        other.AllocateHeal(other, 1, 1, 1, 1, 1, 1)
        other.IncFillerCasts(other, 50)
        lua.execute("STUB.time = 10")
        s.End(s); other.End(other)                  # both: 0..10 outside the FSR
        s.MergeSegment(s, other)
        self.assertEqual(s.t.heal, 2)
        self.assertEqual(s.fillerManaSpent, 50)
        self.assertAlmostEqual(s.timeOutsideFSR, 20)
        self.assertAlmostEqual(s.totalDuration, 20)

    def test_haste_hpct_estimate_is_capped(self):
        _, addon, s = self.seg()
        s.IncFillerHealing(s, 1000); s.IncFillerCasts(s, 10)   # 1 filler cast, 1000 per cast
        s.AllocateHeal(s, 0, 0, 3.0, 0, 0, 1)                  # upper bound 3.0
        s.IncChainCasts(s)                                     # 1 chain cast at 0 haste -> 1000/1/100 = 10 > cap
        self.assertAlmostEqual(s.GetHasteHPCT(s), 3.0)
        s.t.haste_hpct = 50.0
        self.assertAlmostEqual(s.GetHasteHPCT(s), 10.0)

    def test_end_and_instance_info_work_without_retail_globals(self):
        lua, _, s = self.seg()
        lua.execute('STUB.instance = { name = "Scarlet Monastery", type = "party", difficultyId = 1 }')
        s.SetupInstanceInfo(s, False)
        self.assertEqual((s.instance.name, s.instance.type, s.instance.difficultyId, s.instance.bossFight), ("Scarlet Monastery", "party", 1, False))
        s.End(s)   # must not touch MAX_TALENT_TIERS / C_ChallengeMode
        self.assertTrue(s.talentsSnapshot)
