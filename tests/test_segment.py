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


class SegmentManagerTests(unittest.TestCase):
    def test_for_each_live_visits_the_current_fight_and_total(self):
        from harness import CORE_FILES
        lua, addon = load(CORE_FILES)
        sm = addon.SegmentManager
        seen = lambda: lua.eval("(function() local t = {} HSW_TEST_ADDON.SegmentManager:ForEachLive(function(s) t[#t + 1] = s.id end) return table.concat(t, ',') end)()")
        self.assertEqual(seen(), "Total")                       # no fight yet: Total only
        sm.Enqueue(sm, "Boss")
        self.assertEqual(seen(), "Boss,Total")

    def test_boss_flag_is_explicit_and_numbering_resets_with_the_list(self):
        from harness import CORE_FILES
        lua, addon = load(CORE_FILES)
        sm = addon.SegmentManager
        sm.Enqueue(sm, "Boss", True)
        sm.Enqueue(sm, "Boss")
        self.assertEqual((sm.Get(sm, 1).bossFight, sm.Get(sm, 0).bossFight), (True, False))
        self.assertEqual(sm.Get(sm, 0).id, "Boss(2)")
        sm.ResetAllSegments(sm)
        sm.Enqueue(sm, "Boss")
        self.assertEqual(sm.Get(sm, 0).id, "Boss")


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
        self.assertEqual(s.GetIntManaValue(s), 0)           # no pool share until the fight ends
        s.poolShare = 1
        self.assertAlmostEqual(s.GetIntManaValue(s), 75.0)  # 15 mana * HPM 5 * one full pool
        s.poolShare = 0.4
        self.assertAlmostEqual(s.GetIntManaValue(s), 30.0)
        s.poolShare = 2.3                                   # a total: the sum of its fights' shares
        self.assertAlmostEqual(s.GetIntManaValue(s), 172.5)
        addon.ply_intmult = 1.1
        self.assertAlmostEqual(s.GetIntManaValue(s), 189.75)

    def test_returned_mana_comes_off_filler_mana(self):
        _, _, s = self.seg()
        s.IncFillerHealing(s, 1000); s.IncFillerCasts(s, 200)
        s.IncManaRestore(s, 50)
        self.assertAlmostEqual(s.GetFillerHPM(s), 1000 / 150)
        s.IncManaRestore(s, 150)
        self.assertEqual(s.GetFillerHPM(s), 0)              # more returned than spent so far: no rate yet

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

    def test_pool_share_is_spending_less_returns_and_regen_over_max_mana(self):
        lua, addon, s = self.seg()
        addon.ply_maxmana = 2000; addon.ply_regen_base = 10; addon.ply_mp5 = 25
        addon.lastManaSpend = 0
        addon.ply_castpct = 0.5
        s.IncManaSpent(s, 1000); s.IncManaSpent(s, 300)     # heals, shocks, totems: 1300 spent
        s.IncManaRestore(s, 100)                            # returned on crits
        lua.execute("STUB.time = 10")
        s.AccumulateFSR(s, 10)                              # 5 s in the FSR at 50% + 5 s outside: 7.5 effective seconds
        self.assertAlmostEqual(s.EffectiveRegenSeconds(s), 7.5)
        # regen = 10 * 7.5 + 25 / 5 * 10 = 125; drain = 1300 - 100 - 125 = 1075
        self.assertAlmostEqual(s.EstimatePoolShare(s), 1075 / 2000)

    def test_pool_share_is_clamped_and_needs_a_max_mana(self):
        lua, addon, s = self.seg()
        addon.ply_maxmana = 1000; addon.ply_regen_base = 0; addon.ply_mp5 = 0
        self.assertEqual(s.EstimatePoolShare(s), 0)         # nothing spent
        s.IncManaSpent(s, 2500)
        self.assertEqual(s.EstimatePoolShare(s), 1)         # more than a pool (a potion, Mana Tide): capped
        addon.ply_regen_base = 100
        lua.execute("STUB.time = 60")
        s.AccumulateFSR(s, 60)                              # 60 s outside the FSR: 6000 regen
        self.assertEqual(s.EstimatePoolShare(s), 0)         # regen covers the spending
        addon.ply_regen_base = 0; addon.ply_maxmana = 0
        self.assertEqual(s.EstimatePoolShare(s), 0)         # max mana unknown

    def test_cast_pct_is_time_weighted(self):
        _, addon, s = self.seg()
        addon.ply_castpct = 1.0; s.AccumulateFSR(s, 2)
        addon.ply_castpct = 0.0; s.AccumulateFSR(s, 4)
        self.assertAlmostEqual(s.castPctWeighted / (s.timeInFSR + s.timeOutsideFSR), 0.5)

    def test_allocate(self):
        lua, addon, s = self.seg()
        s.AllocateHeal(s, 1, 2, 3, 4, 5, 123)
        self.assertEqual((s.t.heal, s.t.crit, s.t.haste_hpct, s.t.int, s.t.spirit), (1, 2, 3, 4, 5))

    def test_haste_hpct_estimate_is_capped(self):
        _, addon, s = self.seg()
        s.IncFillerHealing(s, 1000); s.IncFillerCasts(s, 10)   # 1 filler cast, 1000 per cast
        s.AllocateHeal(s, 0, 0, 3.0, 0, 0, 1)                  # upper bound 3.0
        s.IncChainCasts(s)                                     # 1 chain cast at 0 haste -> 1000/1/100 = 10 > cap
        self.assertAlmostEqual(s.GetHasteHPCT(s), 3.0)
        s.t.haste_hpct = 50.0
        self.assertAlmostEqual(s.GetHasteHPCT(s), 10.0)

    def test_end_snapshots_talents(self):
        lua, _, s = self.seg()
        self.assertFalse(s.bossFight)
        s.End(s)
        self.assertTrue(s.talentsSnapshot)

    def test_count_heal_buckets_direct_and_tick_with_crits_and_targets(self):
        lua, _, s = self.seg()
        self.assertEqual(len(list(s.hits.keys())), 0)
        s.CountHeal(s, 331, "SPELL_HEAL", "Bob", False)
        s.CountHeal(s, 331, "SPELL_HEAL", "Bob", True)
        s.CountHeal(s, 331, "SPELL_PERIODIC_HEAL", "Me", False)
        s.CountHeal(s, 331, "SPELL_HEAL", None, False)                 # a secret target name: counted, no target
        h = s.hits[331]
        self.assertEqual((h.direct.n, h.direct.crit, h.tick.n, h.tick.crit), (3, 1, 1, 0))
        self.assertEqual((h.targets.Bob, h.targets.Me), (2, 1))
        self.assertEqual(s.TopTarget(s, 331), "Bob")
        self.assertIsNone(s.TopTarget(s, 547))

    def test_hits_are_per_segment(self):
        lua, addon, s = self.seg()
        s.CountHeal(s, 331, "SPELL_HEAL", "Me", False)
        other = addon.Segment.Create("other")
        self.assertEqual(len(list(other.hits.keys())), 0)
