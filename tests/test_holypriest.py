import unittest
from parsers import start, heal, set_auras, crit_per_pct

FILES = ["Parsers/HolyPriest.lua"]
HOLY = [("Discipline", []), ("Holy", [("Spiritual Guidance", 5)])]
FH = 10917      # Flash Heal R7: coeff .429 base 841
RENEW = 25315   # Renew R10 tick: coeffTick .2 baseTick 166
INNER_FOCUS = 14751


class HolyPriestTests(unittest.TestCase):
    def test_spec_detection_and_shared_functions(self):
        _, addon, _ = start("PRIEST", HOLY, FILES)
        self.assertTrue(addon.IsHolyPriest(addon))
        self.assertTrue(addon.SpecInfo[257][1].value.startswith("https://"))
        self.assertIsNotNone(addon.Priest.CritChance)
        self.assertIsNotNone(addon.Priest.Spirit)

    def test_spiritual_guidance_scales_with_healing_derivative(self):
        _, addon, seg = start("PRIEST", HOLY, FILES)
        heal(addon, "SPELL_HEAL", FH, 841 + 0.429 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.429)
        self.assertAlmostEqual(seg.t.spirit, 0.25 * 0.429)
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 166 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.spirit, 0.25 * 0.429 + 0.25 * 0.2)

    def test_inner_focus_only_on_direct_heals(self):
        lua, addon, seg = start("PRIEST", HOLY, FILES)         # Holy crit 10%
        set_auras(lua, INNER_FOCUS)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.35) / 14)
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 500)
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(1000, 0.35) + crit_per_pct(500, 0.10)) / 14)
        set_auras(lua)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(1000, 0.35) + crit_per_pct(500, 0.10) + crit_per_pct(1000, 0.10)) / 14)

    def test_without_spiritual_guidance(self):
        _, addon, seg = start("PRIEST", [("Discipline", []), ("Holy", [("Spiritual Healing", 3)])], FILES)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertEqual(seg.t.spirit, 0)
