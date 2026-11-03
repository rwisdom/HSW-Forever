import unittest
from parsers import start, heal, crit_per_pct

FILES = ["Parsers/HolyPaladin.lua"]
HOLY = [("Holy", [("Illumination", 5), ("Holy Power", 5), ("Boundless Light", 2)]), ("Protection", []), ("Retribution", [])]
HL = 25292          # Holy Light R9: 660 mana, 2.5s
HS_HEAL = 25903     # Holy Shock R4 heal event -> book 20930, 325 mana
LV = 1310911        # Light's Vigil R1: 730 mana, heal coeff .143
OATH = 1328548      # Oath of Light
CB = 0.75           # Holy Power 5/5 raises the 50% crit healing bonus by 50%


class HolyPaladinTests(unittest.TestCase):
    def test_parser_and_info_registered(self):
        _, addon, _ = start("PALADIN", HOLY, FILES)
        self.assertIsNotNone(addon.StatParser[65])
        self.assertTrue(addon.SpecInfo[65][1].value.startswith("https://"))

    def test_holy_power_raises_the_crit_bonus_and_illumination(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)          # Holy crit 10% (Holy Power no longer adds crit chance)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_HEAL", HL, 1000)                     # fillerHealing 1000 -> HPM 1000/660
        illumination = 0.01 * (0.2 * 5) * 0.5 * 660 * (1000 / 660) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, CB) / 14 + illumination)
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1000, 0.10, CB) / 31.9)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, crit_per_pct(1000, 0.10, CB) / 14)   # Total has no filler mana yet -> HPM 0

    def test_crit_heals_are_normalised_with_the_raised_bonus(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        heal(addon, "SPELL_HEAL", HL, 1000)
        a = (seg.t.heal, seg.t.int)
        _, addon, seg = start("PALADIN", HOLY, FILES)
        heal(addon, "SPELL_HEAL", HL, 1750, crit=True)          # 1000 x 1.75
        for x, y in zip(a, (seg.t.heal, seg.t.int)):
            self.assertAlmostEqual(x, y)

    def test_boundless_light_on_holy_shock_off_the_oath_target(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 325)
        heal(addon, "SPELL_HEAL", HS_HEAL, 1000)                # no Oath on the target: 10% + 30%
        illumination = 0.01 * 1.0 * 0.5 * 325 * (1000 / 325) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.40, CB) / 14 + illumination)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", OATH, 300)
        before = seg.t.crit
        heal(addon, "SPELL_HEAL", HS_HEAL, 1000)                # Oath target: sheet crit
        illumination = 0.01 * 1.0 * 0.5 * 325 * (2000 / 325) / 14
        self.assertAlmostEqual(seg.t.crit - before, crit_per_pct(1000, 0.10, CB) / 14 + illumination)

    def test_oath_flat_bonus_comes_off_the_healing_derivative_only(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        heal(addon, "SPELL_HEAL", HL, 1000)
        plain_heal, plain_int = seg.t.heal, seg.t.int
        _, addon, seg = start("PALADIN", HOLY, FILES)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", OATH, 300)
        heal(addon, "SPELL_HEAL", HL, 1400)                     # 1000 + the Oath's 400 on Holy Light
        self.assertAlmostEqual(seg.t.heal, plain_heal)          # +Healing did not produce the 400
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1400, 0.10, CB) / 14)   # the 400 crits with the rest
        self.assertAlmostEqual(seg.t.int, crit_per_pct(1400, 0.10, CB) / 31.9)
        heal(addon, "SPELL_HEAL", HL, 2450, crit=True)          # (1000 + 400) x 1.75
        self.assertAlmostEqual(seg.t.heal, 2 * plain_heal)

    def test_oath_amounts_per_spell_and_target(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        addon.BuffTracker.MarkTarget(addon.BuffTracker, "Me", OATH, 300)
        get = lambda spell: addon.Spells.Get(addon.Spells, spell)
        for spell, amount in ((HL, 400), (HS_HEAL, 230), (LV, 0)):   # Light's Vigil is not in the Oath
            self.assertEqual(addon.StatParser[65].FlatBonus("SPELL_HEAL", get(spell), "player"), amount)
        fol = get(19943)                                          # Flash of Light R6
        self.assertEqual(addon.StatParser[65].FlatBonus("SPELL_HEAL", fol, "player"), 115)
        self.assertEqual(addon.StatParser[65].FlatBonus("SPELL_PERIODIC_HEAL", fol, "player"), 0)
        self.assertEqual(addon.StatParser[65].FlatBonus("SPELL_HEAL", fol, "party1"), 0)   # no Oath there

    def test_boundless_light_leaves_other_spells_alone(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        heal(addon, "SPELL_HEAL", HL, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, CB) / 14)

    def test_lights_vigil_uses_its_own_cost(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 730)
        heal(addon, "SPELL_HEAL", LV, 1000)
        illumination = 0.01 * 1.0 * 0.5 * 730 * (1000 / 730) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, CB) / 14 + illumination)

    def test_no_illumination_on_ticks_or_without_talent(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_PERIODIC_HEAL", HL, 1000)            # periodic: crit value, no Illumination
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, CB) / 14)
        _, addon, seg = start("PALADIN", [("Holy", [("Holy Power", 2)]), ("Protection", []), ("Retribution", [])], FILES)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_HEAL", HL, 1000)
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, 0.60) / 14)   # 2/5: 50% x 1.2

    def test_illumination_mana_comes_off_the_filler_cost(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        seg.IncFillerCasts(seg, 660)
        heal(addon, "SPELL_HEAL", HL, 1750, crit=True)             # 330 back before the crit is valued: HPM 1750/330
        self.assertAlmostEqual(seg.GetFillerHPM(seg), 1750 / 330)
        illumination = 0.01 * 1.0 * 0.5 * 660 * (1750 / 330) / 14
        self.assertAlmostEqual(seg.t.crit, crit_per_pct(1000, 0.10, CB) / 14 + illumination)

    def test_illumination_mana_is_credited_on_crits(self):
        _, addon, seg = start("PALADIN", HOLY, FILES)
        heal(addon, "SPELL_HEAL", HL, 1500, crit=True)             # 5/5: 100% chance x 50% of 660
        self.assertEqual(seg.manaRestore, 330)
        heal(addon, "SPELL_HEAL", HL, 1000)                        # no crit: nothing
        heal(addon, "SPELL_PERIODIC_HEAL", HL, 1500, crit=True)    # ticks never proc it
        self.assertEqual(seg.manaRestore, 330)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.manaRestore, 330)
