import unittest
from parsers import start, heal, crit_per_pct

FILES = ["Parsers/RestoDruid.lua"]
RESTO = [("Balance", []), ("Feral Combat", []), ("Restoration", [("Improved Regrowth", 5)])]
REGROWTH = 9858   # R9: coeff .286 base 1021, coeffTick .071 baseTick 142
REJUV = 25299     # R11 tick: coeffTick .2 baseTick 194


class RestoDruidTests(unittest.TestCase):
    def test_spec_detection_and_info(self):
        _, addon, _ = start("DRUID", RESTO, FILES)
        self.assertTrue(addon.IsRestoDruid(addon))
        self.assertTrue(addon.SpecInfo[105][1].value.startswith("https://"))
        self.assertIsNotNone(addon.StatParser[105])

    def test_improved_regrowth_on_direct_and_tick(self):
        _, addon, seg = start("DRUID", RESTO, FILES)           # Nature crit 12% + 50%
        heal(addon, "SPELL_HEAL", REGROWTH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.62) / 14)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1000, 0.62) / 28.4)
        heal(addon, "SPELL_PERIODIC_HEAL", REGROWTH, 500)
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(1000, 0.62) + crit_per_pct(500, 0.62)) / 14)

    def test_other_spells_use_sheet_crit(self):
        _, addon, seg = start("DRUID", RESTO, FILES)
        heal(addon, "SPELL_PERIODIC_HEAL", REJUV, 194 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.2)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(194 + 0.2 * 200, 0.12) / 14)
        self.assertEqual(seg.t.spirit, 0)

    def test_without_talent(self):
        _, addon, seg = start("DRUID", [("Balance", []), ("Feral Combat", []), ("Restoration", [("Living Spirit", 1)])], FILES)
        heal(addon, "SPELL_HEAL", REGROWTH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.12) / 14)
