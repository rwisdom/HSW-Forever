import unittest
from parsers import start, heal, crit_per_pct

FILES = ["Parsers/HolyPaladin.lua"]
HOLY = [("Holy", [("Illumination", 5), ("Holy Power", 5)]), ("Protection", []), ("Retribution", [])]
HL = 25292          # Holy Light R9: 660 mana, 2.5s
HS_HEAL = 25903     # Holy Shock R4 heal event -> book 20930, 325 mana
LV = 1310911        # Light's Vigil R1: 730 mana, heal coeff .143


class HolyPaladinTests(unittest.TestCase):
    def test_spec_detection_and_info(self):
        _, addon, _ = start("PALADIN", HOLY, FILES)
        self.assertTrue(addon.IsHolyPaladin(addon))
        self.assertTrue(addon.SpecInfo[65][1].value.startswith("https://"))

    def test_holy_power_and_illumination(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)          # Holy crit 10% + 5% (Holy Power on non-Holy Shock)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_HEAL", HL, 1000)                     # fillerHealing 1000 -> HPM 1000/660
        illumination = 0.01 * (0.2 * 5) * 0.5 * 660 * (1000 / 660) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.15) / 14 + illumination)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1000, 0.15) / 31.9)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, crit_per_pct(1000, 0.15) / 14)   # Total has no filler mana yet -> HPM 0

    def test_holy_shock_gets_15_percent(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 325)
        heal(addon, "SPELL_HEAL", HS_HEAL, 1000)
        illumination = 0.01 * 1.0 * 0.5 * 325 * (1000 / 325) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.25) / 14 + illumination)

    def test_lights_vigil_uses_its_own_cost(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 730)
        heal(addon, "SPELL_HEAL", LV, 1000)
        illumination = 0.01 * 1.0 * 0.5 * 730 * (1000 / 730) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.15) / 14 + illumination)

    def test_no_illumination_on_ticks_or_without_talent(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_PERIODIC_HEAL", HL, 1000)            # periodic: crit value, no Illumination
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.15) / 14)
        _, addon, seg = start("PALADIN", [("Holy", [("Holy Power", 2)]), ("Protection", []), ("Retribution", [])], FILES)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_HEAL", HL, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.12) / 14)
