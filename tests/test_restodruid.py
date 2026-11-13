import unittest
from parsers import start, heal, crit_per_pct

FILES = ["Parsers/RestoDruid.lua"]
RESTO = [("Balance", []), ("Feral Combat", []), ("Restoration", [("Improved Regrowth", 5)])]
REGROWTH = 9858   # R9: coeff .286 base 1021, coeffTick .071 baseTick 142
REJUV = 25299     # R11 tick: coeffTick .2 baseTick 194


class RestoDruidTests(unittest.TestCase):
    def test_parser_and_info_registered(self):
        _, addon, _ = start("DRUID", RESTO, FILES)
        self.assertIsNotNone(addon.StatParser[105])
        self.assertTrue(addon.SpecInfo[105][1].value.startswith("https://"))

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

    def test_natural_instinct_turns_intellect_into_healing(self):
        resto = [("Balance", []), ("Feral Combat", [("Natural Instinct", 2)]), ("Restoration", [("Gift of Nature", 5), ("Living Spirit", 3)])]
        _, addon, seg = start("DRUID", resto, FILES)
        heal(addon, "SPELL_PERIODIC_HEAL", REJUV, 194 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.2)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(194 + 0.2 * 200, 0.12) / 28.4 + 0.25 * 0.2)   # 25% of Int at 2/2
        resto[1] = ("Feral Combat", [("Natural Instinct", 1)])
        _, addon, seg = start("DRUID", resto, FILES)
        heal(addon, "SPELL_PERIODIC_HEAL", REJUV, 194 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(194 + 0.2 * 200, 0.12) / 28.4 + 0.12 * 0.2)   # 12% at 1/2
        resto[2] = ("Restoration", [("Heart of the Wild", 5)])
        _, addon, seg = start("DRUID", resto, FILES)
        heal(addon, "SPELL_PERIODIC_HEAL", REJUV, 194 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.int, (crit_per_pct(194 + 0.2 * 200, 0.12) / 28.4 + 0.12 * 0.2) * 1.10)   # +10% Int: on the crit and on the +Healing

    def test_without_talent(self):
        _, addon, seg = start("DRUID", [("Balance", []), ("Feral Combat", []), ("Restoration", [("Living Spirit", 1)])], FILES)
        heal(addon, "SPELL_HEAL", REGROWTH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.12) / 14)
