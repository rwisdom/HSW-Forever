import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/Util.lua", "Classes/BuffTracker.lua", "Classes/Segment.lua",
         "Classes/SegmentManager.lua", "Classes/StatParser.lua", "Classes/UnitManager.lua",
         "Parsers/Spells.lua", "Parsers/Spells_Generated.lua", "Parsers/Spells_Manual.lua"]

TALENTS = {
    "PALADIN": 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Divine Intellect", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }',
    "DRUID": 'STUB.class = "DRUID"; STUB.talents = { {name="Balance", talents={}}, {name="Feral Combat", talents={}}, {name="Restoration", talents={ {name="Living Spirit", rank=3, max=3} }} }',
    "PRIEST": 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={ {name="Mental Strength", rank=5, max=5} }}, {name="Holy", talents={}} }',
}

HL = 25292      # Holy Light R9: coeff .714, base 1580, 660 mana, 2.5s cast
REJUV = 25299   # Rejuvenation R11 tick: coeffTick .2, baseTick 194, instant
PWS = 10901     # Power Word: Shield R10: coeff .10 (manual), base 928, canCrit false


def start(cls, overrides="{}", extra=""):
    """Level-30 `cls` (stub defaults: SP 200, Holy crit 10% / Nature 12%, Int 110, Spirit 60, regen 10/3),
    parser registered with `overrides`, one live segment, player GUID cached."""
    lua, addon = load(FILES, setup=TALENTS[cls] + "\n" + extra)
    lua.execute(f"""
        local a = HSW_TEST_ADDON
        a.StatParser:Create(a:GetSpecId(), {overrides})
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.SegmentManager:Enqueue("fight"); a.UnitManager.units["Player-1"] = "player"
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def heal(addon, ev, spell, amount, crit=False, overheal=0, dest="Player-1"):
    addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit, amount, overheal)


class Conversions(unittest.TestCase):
    def test_defaults_at_level_30(self):
        _, addon, _ = start("PALADIN")
        self.assertEqual((addon.CritConv, addon.HasteConv, addon.IntPerCrit, addon.RegenPerSpirit), (14, 100, 31.9, 0.1))

    def test_int_per_crit_level_lookup_and_overrides(self):
        lua, addon, _ = start("DRUID", extra="STUB.level = 60")
        self.assertEqual(addon.IntPerCrit, 28.4)                 # nearest keyed level <= 60
        lua.execute("STUB.level = 10")
        addon.SetupConversionFactors(addon)
        self.assertEqual(addon.IntPerCrit, 28.4)                 # below the lowest key: lowest key
        lua.execute("HSW_TEST_ADDON.hsw.db.global.intPerCritOverride.DRUID = 40; HSW_TEST_ADDON.hsw.db.global.hasteRatingPerPct = 10")
        addon.SetupConversionFactors(addon)
        self.assertEqual((addon.IntPerCrit, addon.HasteConv), (40, 1000))

    def test_unsupported_class_has_no_parser(self):
        _, addon = load(FILES, setup='STUB.class = "WARRIOR"; STUB.talents = { {name="Arms", talents={ {name="Deflection", rank=5, max=5} }} }')
        self.assertFalse(addon.StatParser.IsCurrentSpecSupported(addon.StatParser))
        heal(addon, "SPELL_HEAL", HL, 1000)                      # no parser: silently ignored, no error


class PlayerStats(unittest.TestCase):
    def test_reads_stub_apis(self):
        _, addon, _ = start("PALADIN")                            # Human, Divine Intellect 5/5
        self.assertEqual((addon.ply_sp, addon.ply_crt, addon.ply_crtbonus, addon.ply_hst), (200, 0.10, 0.5, 0))
        self.assertEqual((addon.ply_int, addon.ply_spi, addon.ply_maxmana), (110, 60, 3000))
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (10, 3))
        self.assertAlmostEqual(addon.ply_castpct, 0.3)
        self.assertAlmostEqual(addon.ply_intmult, 1.10)
        self.assertAlmostEqual(addon.ply_spiritmult, 1.05)

    def test_crit_school_and_multipliers_by_class(self):
        lua, addon, _ = start("DRUID", extra='STUB.race = "Tauren"')   # Nature crit, Living Spirit 3/3
        self.assertAlmostEqual(addon.ply_crt, 0.12)
        self.assertAlmostEqual(addon.ply_intmult, 1.0)
        self.assertAlmostEqual(addon.ply_spiritmult, 1.15)
        lua.execute("STUB.regen = { base = 0, cast = 0 }")
        addon.UpdatePlayerStats(addon)
        self.assertEqual(addon.ply_castpct, 0)


class RegenCalibration(unittest.TestCase):
    def test_slope_needs_two_samples_20_spirit_apart(self):
        _, addon, _ = start("PALADIN")                            # UpdatePlayerStats sampled (60, 10)
        self.assertAlmostEqual(addon.GetRegenPerSpirit(addon), 0.1)
        addon.SampleRegen(addon, 70, 12)                          # < 20 apart: replaces the anchor
        self.assertAlmostEqual(addon.GetRegenPerSpirit(addon), 0.1)
        addon.SampleRegen(addon, 110, 20)                         # 40 apart: slope 8/40
        self.assertAlmostEqual(addon.GetRegenPerSpirit(addon), 0.2)
        cal = addon.hsw.db["global"].regenCal["PALADIN:30"]     # "global" is a Python keyword
        self.assertEqual((cal[1], cal[2], cal[3], cal[4]), (70, 12, 110, 20))
        addon.SetupConversionFactors(addon)
        self.assertAlmostEqual(addon.RegenPerSpirit, 0.2)


class Derivatives(unittest.TestCase):
    def test_healing_derivative_equals_coefficient(self):
        _, addon, seg = start("PALADIN")                          # SP 200
        expected = 1580 + 0.714 * 200
        heal(addon, "SPELL_HEAL", HL, expected)
        self.assertAlmostEqual(seg.t.heal, 0.714)
        heal(addon, "SPELL_HEAL", HL, expected * 1.1)             # +10% talent multiplier scales with it
        self.assertAlmostEqual(seg.t.heal, 0.714 + 0.714 * 1.1)

    def test_crit_int_haste_per_point(self):
        _, addon, seg = start("PALADIN")                          # crit 10%, haste 0
        heal(addon, "SPELL_HEAL", HL, 1000)
        per1 = 1000 * 0.5 / 1.05 / 100                            # value of +1% crit
        self.assertAlmostEqual(seg.t.crit, per1 / 14)
        self.assertAlmostEqual(seg.t.int, per1 / 31.9)
        self.assertAlmostEqual(seg.t.haste_hpct, 1000 / 100)
        self.assertEqual(seg.t.spirit, 0)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, seg.t.crit)

    def test_crit_heal_is_normalised(self):
        _, addon, seg = start("PALADIN")
        heal(addon, "SPELL_HEAL", HL, 1000)
        a = (seg.t.heal, seg.t.crit, seg.t.int, seg.t.haste_hpct)
        _, addon, seg = start("PALADIN")
        heal(addon, "SPELL_HEAL", HL, 1500, crit=True)
        b = (seg.t.heal, seg.t.crit, seg.t.int, seg.t.haste_hpct)
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y)

    def test_periodic_uses_tick_values(self):
        _, addon, seg = start("DRUID")                            # SP 200
        heal(addon, "SPELL_PERIODIC_HEAL", REJUV, 194 + 0.2 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.2)
        self.assertEqual(seg.t.haste_hpct, 0)                     # instant: no HPCT value
        self.assertGreater(seg.t.crit, 0)                         # HoT ticks crit on Forever

    def test_absorb_has_no_crit_value(self):
        _, addon, seg = start("PRIEST")
        addon.StatParser.DecompAbsorb(addon.StatParser, "Player-1", PWS, 928 + 0.10 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.10)
        self.assertEqual((seg.t.crit, seg.t.int, seg.t.haste_hpct), (0, 0, 0))

    def test_overheal_counts_in_totals_but_not_derivatives(self):
        _, addon, seg = start("PALADIN")
        heal(addon, "SPELL_HEAL", HL, 1000, overheal=50)
        self.assertEqual(seg.t.heal, 0)
        self.assertEqual((seg.totalHealing, seg.fillerHealing), (1000, 1000))

    def test_filter_rules(self):
        lua, addon, seg = start("PALADIN")
        heal(addon, "SPELL_HEAL", REJUV, 500)                     # druid spell on a paladin: ignored
        heal(addon, "SPELL_HEAL", HL, 500, dest="Creature-7")     # unknown unit: ignored
        self.assertEqual((seg.t.heal, seg.totalHealing), (0, 0))
        heal(addon, "SPELL_HEAL", 999999, 500)                    # unknown spell: discovered as IGNORED
        self.assertEqual(addon.Spells.Get(addon.Spells, 999999).spellType, -1)
        lua.execute("HSW_TEST_ADDON.hsw.db.global.excludeRaidHealingCooldowns = true")
        heal(addon, "SPELL_HEAL", 633, 500)                       # Lay on Hands: raid cooldown excluded
        self.assertEqual(seg.totalHealing, 0)


class Overrides(unittest.TestCase):
    def test_crit_chance_and_per_segment_extras(self):
        ov = """{
            CritChance = function(ev, s, destUnit, C) return 1.0 end,
            CriticalStrike = function(ev, s, heal, destUnit, C, CB, seg) return seg.id == "Total" and 2 or 1 end,
            Intellect = function(ev, s, heal, destUnit, _SP, seg) return _SP end,
            Spirit = function(ev, s, heal, destUnit, _SP, seg) return 0.5 * _SP end,
        }"""
        _, addon, seg = start("PALADIN", overrides=ov)
        heal(addon, "SPELL_HEAL", HL, 1000)
        per1 = 1000 * 0.5 / 1.5 / 100                             # crit chance overridden to 100%
        self.assertAlmostEqual(seg.t.crit, per1 / 14 + 1)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, per1 / 14 + 2)
        self.assertAlmostEqual(seg.t.int, per1 / 31.9 + seg.t.heal)
        self.assertAlmostEqual(seg.t.spirit, 0.5 * seg.t.heal)

    def test_heal_event_can_skip_allocation(self):
        ov = "{ HealEvent = function(ev, s, heal, overhealing, destUnit, f, origHeal) return heal < origHeal end }"
        _, addon, seg = start("PALADIN", overrides=ov)
        heal(addon, "SPELL_HEAL", HL, 1500, crit=True)            # normalised 1000 < 1500: skipped
        self.assertEqual((seg.t.heal, seg.totalHealing), (0, 1500))
        heal(addon, "SPELL_HEAL", HL, 1000)
        self.assertGreater(seg.t.heal, 0)
