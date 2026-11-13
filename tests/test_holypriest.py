import unittest
from parsers import start, heal, set_auras, crit_per_pct, crits, sp_per

FILES = ["Parsers/HolyPriest.lua"]
HOLY = [("Discipline", []), ("Holy", [("Spiritual Guidance", 5)])]
FH = 10917      # Flash Heal R7: coeff .429 base 841
RENEW = 25315   # Renew R10 tick: coeffTick .2 baseTick 166
INNER_FOCUS = 14751


class HolyPriestTests(unittest.TestCase):
    def test_parser_info_and_shared_functions_registered(self):
        _, addon, _ = start("PRIEST", HOLY, FILES)
        self.assertIsNotNone(addon.StatParser[257])
        self.assertEqual(addon.SpecInfo[257][1].key, "Holy Priest")
        self.assertIsNotNone(addon.Priest.CritChance)
        self.assertIsNotNone(addon.Priest.Spirit)

    def test_spiritual_guidance_scales_with_healing_derivative(self):
        _, addon, seg = start("PRIEST", HOLY, FILES)           # Holy crit 10%
        heal(addon, "SPELL_HEAL", FH, 841 + 0.429 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.429 * crits(0.10))
        self.assertAlmostEqual(seg.t.spirit, 0.25 * 0.429 * crits(0.10))
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 166 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.spirit, (0.25 * 0.429 + 0.25 * 0.2) * crits(0.10))

    def test_inner_focus_only_on_direct_heals(self):
        lua, addon, seg = start("PRIEST", HOLY, FILES)         # Holy crit 10%
        set_auras(lua, INNER_FOCUS)
        heal(addon, "SPELL_HEAL", FH, 1000)
        direct, tick = sp_per(addon, FH, 1000), sp_per(addon, RENEW, 500, tick=True)
        self.assertAlmostEqual(seg.t.heal, direct * crits(0.35))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 500)
        self.assertAlmostEqual(seg.t.heal, direct * crits(0.35) + tick * crits(0.10))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1500))
        set_auras(lua)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.heal, direct * crits(0.35) + tick * crits(0.10) + direct * crits(0.10))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(2500))

    def test_holy_specialization_adds_crit_on_every_holy_heal(self):
        _, addon, seg = start("PRIEST", [("Discipline", []), ("Holy", [("Holy Specialization", 5)])], FILES)   # Holy crit 10% on the sheet
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.heal, sp_per(addon, FH, 1000) * crits(0.15))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 500)
        self.assertAlmostEqual(seg.t.heal, (sp_per(addon, FH, 1000) + sp_per(addon, RENEW, 500, tick=True)) * crits(0.15))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1500))

    def test_without_spiritual_guidance(self):
        _, addon, seg = start("PRIEST", [("Discipline", []), ("Holy", [("Spiritual Healing", 3)])], FILES)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertEqual(seg.t.spirit, 0)
