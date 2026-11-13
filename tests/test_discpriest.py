import unittest
from parsers import start, heal, count, set_auras, crit_per_pct, crits, sp_per

FILES = ["Parsers/HolyPriest.lua", "Parsers/DiscPriest.lua"]
DISC = [("Discipline", [("Renewed Hope", 5), ("Divine Aegis", 3), ("Mental Strength", 5)]), ("Holy", [("Spiritual Guidance", 2)])]
FH = 10917          # Flash Heal R7
RENEW = 25315       # Renew R10 tick
PENANCE = 402174    # Penance R1
PWS = 10901         # Power Word: Shield R10
WEAKENED_SOUL, INNER_FOCUS = 6788, 14751


def aegis(heal_amount, rank=3, CB=0.5):
    """Value of Divine Aegis per 1% crit on one heal: 0.05*rank of the crit amount absorbed, up to 1,200."""
    return 0.01 * min(0.05 * rank * heal_amount * (1 + CB), 1200)


class DiscPriestTests(unittest.TestCase):
    def test_parser_and_info_registered(self):
        _, addon, _ = start("PRIEST", DISC, FILES)
        self.assertIsNotNone(addon.StatParser[256])
        self.assertEqual(addon.SpecInfo[256][1].key, "Discipline Priest")

    def test_renewed_hope_needs_weakened_soul(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)           # Holy crit 10%
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.heal, sp_per(addon, FH, 1000) * crits(0.10))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000) + aegis(1000))
        # crit from Int absorbs through Divine Aegis too; Mental Strength 5/5 makes 1 Int on gear 1.10 on the sheet
        self.assertAlmostEqual(seg.t.int, (crit_per_pct(1000) + aegis(1000)) / 26.9 * 1.10)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", WEAKENED_SOUL, 15)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.heal, sp_per(addon, FH, 1000) * (crits(0.10) + crits(0.20)))   # 10% more crits on the second
        self.assertAlmostEqual(seg.t.crit, 2 * crit_per_pct(1000) + 2 * aegis(1000))

    def test_binding_heal_is_gone(self):
        _, addon, seg = start("PRIEST", DISC, FILES)
        self.assertIsNone(addon.Spells.Get(addon.Spells, 1240774))   # Binding Heal R6: removed from the game (Blizzard's notes of 2 Nov 2026)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", WEAKENED_SOUL, 15)
        heal(addon, "SPELL_HEAL", 1240774, 1000)                 # an unknown spell credits nothing
        self.assertEqual(seg.t.crit, 0)

    def test_penance_bolts_get_renewed_hope_and_aegis_renew_ticks_do_not(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", WEAKENED_SOUL, 15)
        heal(addon, "SPELL_PERIODIC_HEAL", PENANCE, 500)
        bolt = sp_per(addon, PENANCE, 500, tick=True) * crits(0.20)
        self.assertAlmostEqual(seg.t.heal, bolt)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(500) + aegis(500))
        heal(addon, "SPELL_PERIODIC_HEAL", RENEW, 500)           # ticks crit, but Aegis is non-periodic only
        self.assertAlmostEqual(seg.t.heal, bolt + sp_per(addon, RENEW, 500, tick=True) * crits(0.10))
        self.assertAlmostEqual(seg.t.crit, 2 * crit_per_pct(500) + aegis(500))

    def test_aegis_absorb_caps_at_1200(self):
        _, addon, seg = start("PRIEST", DISC, FILES)
        heal(addon, "SPELL_HEAL", FH, 10000)                     # 0.15 * 15000 = 2250 absorb -> capped
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(10000) + 0.01 * 1200)

    def test_aegis_and_its_cap_are_per_heal_in_a_fight_of_several(self):
        _, addon, seg = start("PRIEST", DISC, FILES)
        for _ in range(4):
            count(addon, "SPELL_HEAL", FH)
        addon.TestTotal(FH, 4 * 1000)                            # four heals of 1000: none near the cap, though the total is
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(4000) + 4 * aegis(1000))
        _, addon, seg = start("PRIEST", DISC, FILES)
        for _ in range(5):
            count(addon, "SPELL_HEAL", FH)
        addon.TestTotal(FH, 5 * 10000)                           # five that each cap
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(50000) + 5 * 0.01 * 1200)

    def test_inner_focus_and_spiritual_guidance_shared_with_holy(self):
        lua, addon, seg = start("PRIEST", DISC, FILES)
        set_auras(lua, INNER_FOCUS)
        heal(addon, "SPELL_HEAL", FH, 841 + 0.429 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.429 * crits(0.35))
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(841 + 0.429 * 200) + aegis(841 + 0.429 * 200))
        self.assertAlmostEqual(seg.t.spirit, 0.10 * 0.429 * crits(0.35))
        self.assertAlmostEqual(addon.ply_intmult, 1.10)        # Mental Strength 2%/rank

    def test_shield_credited_at_cast_has_no_aegis(self):
        _, addon, seg = start("PRIEST", DISC, FILES)
        addon.StatParser.DecompShieldCast(addon.StatParser, "Player-1", PWS)
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)    # base + coeff x +Healing
        self.assertEqual(seg.t.crit, 0)
        self.assertGreater(seg.t.heal, 0)
        addon.StatParser.DecompShieldCast(addon.StatParser, "Player-1", 424242)   # unknown: ignored
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)

    def test_without_talents(self):
        lua, addon, seg = start("PRIEST", [("Discipline", [("Meditation", 3)]), ("Holy", [])], FILES)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", WEAKENED_SOUL, 15)
        heal(addon, "SPELL_HEAL", FH, 1000)
        self.assertAlmostEqual(seg.t.heal, sp_per(addon, FH, 1000) * crits(0.10))   # no Renewed Hope
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000))
        self.assertEqual(seg.t.spirit, 0)
