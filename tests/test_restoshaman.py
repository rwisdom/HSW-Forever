import unittest
from parsers import start, heal, count, set_auras, crit_per_pct, crits, sp_per

FILES = ["Parsers/RestoShaman.lua"]
RESTO = [("Elemental", []), ("Enhancement", [("Mental Quickness", 2)]), ("Restoration", [("Tidal Mastery", 5)])]
HW = 25357          # Healing Wave R10: coeff .857 base 1615, 620 mana
CHAIN = 10623       # Chain Heal R3
WATER_SHIELD = 408510


class RestoShamanTests(unittest.TestCase):
    def test_parser_and_info_registered(self):
        _, addon, _ = start("SHAMAN", RESTO, FILES)
        self.assertIsNotNone(addon.StatParser[264])
        self.assertEqual(addon.SpecInfo[264][1].key, "Resto Shaman")

    def test_tidal_mastery_and_mental_quickness(self):
        _, addon, seg = start("SHAMAN", RESTO, FILES)           # Nature crit 12% + 5%
        amount = 1615 + 0.857 * 200
        heal(addon, "SPELL_HEAL", HW, amount)
        self.assertAlmostEqual(seg.t.heal, 0.857 * crits(0.17))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(amount))
        self.assertAlmostEqual(seg.t.int, crit_per_pct(amount) / 28.2 + 0.30 * 0.857 * crits(0.17))
        self.assertEqual(seg.t.spirit, 0)

    def test_water_shield_crit_mana(self):
        lua, addon, seg = start("SHAMAN", RESTO, FILES)         # max mana 3000
        seg.IncFillerCasts(seg, 620)
        heal(addon, "SPELL_HEAL", HW, 1000)                     # HPM 1000/620, no shield -> no extra
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))
        set_auras(lua, WATER_SHIELD)
        heal(addon, "SPELL_HEAL", CHAIN, 1000)                  # HPM now 2000/620
        shield = 0.01 * 0.02 * 3000 * (2000 / 620)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(2000) + shield)
        self.assertAlmostEqual(seg.t.int, (crit_per_pct(2000) + shield) / 28.2 + 0.30 * seg.t.heal)   # crit from Int spends globes too
        ttl =addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, crit_per_pct(2000))   # Total: no filler mana -> HPM 0

    def test_a_fight_of_several_hits_counts_the_shield_on_each_at_the_fights_hpm(self):
        lua, addon, seg = start("SHAMAN", RESTO, FILES)
        set_auras(lua, WATER_SHIELD)
        for _ in range(10):
            seg.IncFillerCasts(seg, 620)
            count(addon, "SPELL_HEAL", HW)
        for _ in range(3):                                      # one Chain Heal, three hits
            count(addon, "SPELL_HEAL", CHAIN)
        seg.IncFillerCasts(seg, 620)
        # both spells in one pricing, as a fight ends: whichever is priced first, each hit sees the fight's HPM
        lua.execute(f"local a = HSW_TEST_ADDON; a.StatParser:ApplyTotals(a.SegmentManager:Get(0), {{ [{HW}] = 10000, [{CHAIN}] = 3000 }})")
        shield = 0.01 * 0.02 * 3000 * (13000 / (11 * 620))      # per hit
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(13000) + 13 * shield)

    def test_without_talents(self):
        _, addon, seg = start("SHAMAN", [("Elemental", []), ("Enhancement", []), ("Restoration", [("Purification", 5)])], FILES)
        heal(addon, "SPELL_HEAL", HW, 1000)
        self.assertAlmostEqual(seg.t.heal, sp_per(addon, HW, 1000) * crits(0.12))   # sheet crit only
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1000) / 28.2)

    def test_water_shield_mana_is_credited_on_crits(self):
        lua, addon, seg = start("SHAMAN", RESTO, FILES)         # max mana 3000
        heal(addon, "SPELL_HEAL", HW, 1500, crit=True)
        self.assertEqual(seg.manaRestore, 0)                    # no shield up
        bt = addon.BuffTracker
        bt.MarkCast(bt, WATER_SHIELD, 600, 3)
        heal(addon, "SPELL_HEAL", HW, 1500, crit=True)
        self.assertEqual((seg.manaRestore, bt.Get(bt, WATER_SHIELD)), (60, 2))   # 2% of 3000, and the crit spent a globe
        heal(addon, "SPELL_HEAL", HW, 1500, crit=True)
        heal(addon, "SPELL_HEAL", HW, 1500, crit=True)
        self.assertEqual((seg.manaRestore, bt.Get(bt, WATER_SHIELD)), (180, 0))
        heal(addon, "SPELL_HEAL", HW, 1500, crit=True)          # no globe left: nothing more, though the 10 min have not run out
        self.assertEqual(seg.manaRestore, 180)

    def test_crit_is_worth_water_shield_mana_only_while_a_globe_remains(self):
        lua, addon, seg = start("SHAMAN", RESTO, FILES)
        bt = addon.BuffTracker
        seg.IncFillerCasts(seg, 620)
        bt.MarkCast(bt, WATER_SHIELD, 600, 3)
        for _ in range(3):
            bt.UseCharge(bt, WATER_SHIELD)
        heal(addon, "SPELL_HEAL", HW, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))   # no shield part
