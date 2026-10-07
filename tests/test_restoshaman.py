import unittest
from parsers import start, heal, set_auras, crit_per_pct

FILES = ["Parsers/RestoShaman.lua"]
RESTO = [("Elemental", []), ("Enhancement", [("Mental Quickness", 2)]), ("Restoration", [("Tidal Mastery", 5)])]
HW = 25357          # Healing Wave R10: coeff .857 base 1615, 620 mana
CHAIN = 10623       # Chain Heal R3
WATER_SHIELD = 408510


class RestoShamanTests(unittest.TestCase):
    def test_spec_detection(self):
        _, addon, _ = start("SHAMAN", RESTO, FILES)
        self.assertTrue(addon.IsRestoShaman(addon))
        self.assertTrue(addon.SpecInfo[264][1].value.startswith("https://"))

    def test_tidal_mastery_and_mental_quickness(self):
        _, addon, seg = start("SHAMAN", RESTO, FILES)           # Nature crit 12% + 5%
        amount = 1615 + 0.857 * 200
        heal(addon, "SPELL_HEAL", HW, amount)
        self.assertAlmostEqual(seg.t.heal, 0.857)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(amount, 0.17) / 14)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(amount, 0.17) / 28.2 + 0.30 * 0.857)
        self.assertEqual(seg.t.spirit, 0)

    def test_water_shield_crit_mana(self):
        lua, addon, seg = start("SHAMAN", RESTO, FILES)         # max mana 3000
        seg.IncFillerCasts(seg, 620)
        heal(addon, "SPELL_HEAL", HW, 1000)                     # HPM 1000/620, no shield -> no extra
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.17) / 14)
        set_auras(lua, WATER_SHIELD)
        heal(addon, "SPELL_HEAL", CHAIN, 1000)                  # HPM now 2000/620
        shield = 0.01 * 0.02 * 3000 * (2000 / 620) / 14
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(1000, 0.17) * 2) / 14 + shield)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, (crit_per_pct(1000, 0.17) * 2) / 14)   # Total: no filler mana -> HPM 0

    def test_without_talents(self):
        _, addon, seg = start("SHAMAN", [("Elemental", []), ("Enhancement", []), ("Restoration", [("Purification", 5)])], FILES)
        heal(addon, "SPELL_HEAL", HW, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.12) / 14)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1000, 0.12) / 28.2)
