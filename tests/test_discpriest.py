import unittest
from parsers import start, heal, set_auras, crit_per_pct

FILES = ["Parsers/HolyPriest.lua", "Parsers/DiscPriest.lua"]
DISC = [("Discipline", [("Renewed Hope", 5), ("Divine Aegis", 3), ("Mental Strength", 5)]), ("Holy", [("Spiritual Guidance", 2)])]
FH = 10917          # Flash Heal R7
RENEW = 25315       # Renew R10 tick
PENANCE = 402174    # Penance R1
PWS = 10901         # Power Word: Shield R10
WEAKENED_SOUL, INNER_FOCUS = 6788, 14751


def aegis(heal_amount, rank=3, CB=0.5):
    """Per-rating value of Divine Aegis: +1% crit -> 0.05*rank of the crit amount absorbed."""
    return 0.01 * 0.05 * rank * heal_amount * (1 + CB) / 14


class DiscPriestTests(unittest.TestCase):
    def test_spec_detection(self):
        _, addon, _ = start("PRIEST", DISC, FILES)
        self.assertTrue(addon.IsDiscPriest(addon))
        self.assertFalse(addon.IsHolyPriest(addon))
        self.assertTrue(addon.SpecInfo[256][1].value.startswith("https://"))

    def test_renewed_hope_needs_weakened_soul(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)           # Holy crit 10%
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10) / 14 + aegis(1000))
        set_auras(lua, WEAKENED_SOUL)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(1000, 0.10) + crit_per_pct(1000, 0.20)) / 14 + 2 * aegis(1000))

    def test_penance_bolts_get_renewed_hope_renew_ticks_do_not(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)
        set_auras(lua, WEAKENED_SOUL)
        heal(addon, "SPELL_PERIODIC_HEAL", PENANCE, 500)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(500, 0.20) / 14 + aegis(500))
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 500)           # Aegis still applies: ticks crit
        self.assertAlmostEqual(seg.t.crit, (crit_per_pct(500, 0.20) + crit_per_pct(500, 0.10)) / 14 + 2 * aegis(500))

    def test_inner_focus_and_spiritual_guidance_shared_with_holy(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)
        set_auras(lua, INNER_FOCUS)
        heal(addon, "SPELL_HEAL", FH, 841 + 0.429 * 200)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(841 + 0.429 * 200, 0.35) / 14 + aegis(841 + 0.429 * 200))
        self.assertAlmostEqual(seg.t.spirit, 0.10 * 0.429)
        self.assertAlmostEqual(addon.ply_intmult, 1.15)

    def test_absorbs_have_no_aegis(self):
        _, addon, seg = start("PRIEST", DISC, FILES)
        addon.StatParser.DecompAbsorb(addon.StatParser, "Player-1", PWS, 1000)
        self.assertEqual(seg.t.crit, 0)
        self.assertGreater(seg.t.heal, 0)

    def test_without_talents(self):
        lua, addon, seg = start("PRIEST", [("Discipline", [("Meditation", 3)]), ("Holy", [])], FILES)
        set_auras(lua, WEAKENED_SOUL)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10) / 14)
        self.assertEqual(seg.t.spirit, 0)
