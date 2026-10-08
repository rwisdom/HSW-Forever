import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import gen_spells as g  # noqa: E402


class ParseCoefficient(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(g.parse_co("71.4% of spell power (heal)"), (0.714, None))
        self.assertEqual(g.parse_co("28.6% of spell power (heal), 7.1% of spell power (per tick)"), (0.286, 0.071))
        self.assertEqual(g.parse_co("42.9% of spell power (direct), 42.9% of spell power (heal)"), (0.429, None))
        self.assertEqual(g.parse_co("20% of spell power (per tick)"), (None, 0.2))
        self.assertEqual(g.parse_co(None), (None, None))


class ParseDescription(unittest.TestCase):
    def test_direct_heals(self):
        self.assertEqual(g.parse_desc("Holy Light", "Heals a friendly target for 1,495 to 1,665."), (1580, None))
        self.assertEqual(g.parse_desc("Holy Shock", "Blasts the target with Holy energy, causing 129 to 139 Holy damage to an enemy, or 110 to 118 healing to an ally."), (114, None))
        self.assertEqual(g.parse_desc("Holy Nova", "Causes an explosion of holy light around the caster, causing 26 to 30 Holy damage to all enemy targets within 10 yards and healing all party members within 10 yards for 49 to 57. These effects cause no threat."), (53, None))
        self.assertEqual(g.parse_desc("Light's Vigil", "Applies Light's Vigil to the target for 30 sec. Your next Holy Shock cast on them triggers no cooldown and causes enemy targets to suffer 175 to 189 Holy damage and refund 75% of Light's Vigil's Mana cost, or allied targets to heal their party for 325 to 343."), (334, None))
        self.assertEqual(g.parse_desc("Penance", "Launches a volley of holy light at the target, causing 81 Holy damage to an enemy, or 184 healing to an ally, instantly and every 1 sec for 2 sec."), (184, None))
        self.assertEqual(g.parse_desc("Power Word: Shield", "Draws on the soul of the party member to shield them, absorbing 928 damage. Lasts 30 sec."), (928, None))
        self.assertEqual(g.parse_desc("Prayer of Mending", "Places a spell on the target that heals them for 172 the next time they take damage or receive non-periodic healing."), (172, None))
        self.assertEqual(g.parse_desc("Lay on Hands", "Heals a friendly target for an amount equal to the Paladin's maximum health and restores 250 of their mana."), (None, None))

    def test_periodic_heals(self):
        self.assertEqual(g.parse_desc("Rejuvenation", "Heals the target for 32 over 12 sec."), (None, 8))
        self.assertEqual(g.parse_desc("Renew", "Heals the target of 45 damage over 15 sec."), (None, 9))
        self.assertEqual(g.parse_desc("Regrowth", "Heals a friendly target for 965 to 1,077 and another 994 over 21 sec."), (1021, 142))
        self.assertEqual(g.parse_desc("Riptide", "Heals a friendly target for 485 to 533, an additional 445 over 15 sec, and increases the effectiveness of your Chain Heal casts directly on that target by 25%."), (509, 89))
        self.assertEqual(g.parse_desc("Wild Growth", "Heals the target and their party for 336 over 7 sec. Party members must be within 43 yards of target."), (None, 48))
        self.assertEqual(g.parse_desc("Tranquility", "Regenerates all nearby party members within 20 yards for 90 every 2 sec for 10 sec. Druid must channel to maintain the spell."), (None, 90))
        self.assertEqual(g.parse_desc("Healing Stream Totem", "Summons a Healing Stream Totem with 5 health at the feet of the caster for 5 min that heals group members within 30 yards for 5 every 2 seconds."), (None, 5))


class ParseCells(unittest.TestCase):
    def test_cells(self):
        self.assertEqual(g.parse_l([["660 Mana", "40 yd range"], ["2.5 sec cast", ""]]), {"mana": 660, "cast": 2.5})
        self.assertEqual(g.parse_l([["", "Enemy: 20 yd range"], ["1,000 Mana", "Friendly: 40 yd range"], ["1.5 sec cast", "6 sec cooldown"]]), {"mana": 1000, "cast": 1.5})
        self.assertEqual(g.parse_l([["375 Mana", ""], ["Channeled", "5 min cooldown"]]), {"mana": 375, "cast": -1})
        self.assertEqual(g.parse_l([["20% of base mana", "40 yd range"], ["Instant", "15 sec cooldown"]]), {"manaPct": 0.2})
        self.assertEqual(g.parse_l([["Instant", "10 min cooldown"]]), {})
        self.assertEqual(g.parse_l(None), {})


class ParseHot(unittest.TestCase):
    def test_periodic_timing(self):
        self.assertEqual(g.parse_hot("Rejuvenation", "Heals the target for 32 over 12 sec."), (12, 3))
        self.assertEqual(g.parse_hot("Regrowth", "Heals a friendly target for 965 to 1,077 and another 994 over 21 sec."), (21, 3))
        self.assertEqual(g.parse_hot("Wild Growth", "Heals the target and their party for 336 over 7 sec. Party members must be within 43 yards of target."), (7, 1))
        self.assertEqual(g.parse_hot("Tranquility", "Regenerates all nearby party members within 20 yards for 90 every 2 sec for 10 sec. Druid must channel to maintain the spell."), (10, 2))
        self.assertEqual(g.parse_hot("Penance", "Launches a volley of holy light at the target, causing 81 Holy damage to an enemy, or 184 healing to an ally, instantly and every 1 sec for 2 sec."), (2, 1))
        self.assertEqual(g.parse_hot("Healing Stream Totem", "Summons a Healing Stream Totem with 5 health at the feet of the caster for 5 min that heals group members within 30 yards for 5 every 2 seconds."), (300, 2))
        self.assertEqual(g.parse_hot("Holy Light", "Heals a friendly target for 1,495 to 1,665."), (None, None))
        self.assertEqual(g.parse_hot("Unknown HoT", "Heals the target for 32 over 12 sec."), (None, None))   # no interval known: no timing


class BuildAndRender(unittest.TestCase):
    def test_holy_light(self):
        e = g.build_entry("PALADIN", "Holy Light", "Rank 9", {"id": 25292, "l": [["660 Mana", "40 yd range"], ["2.5 sec cast", ""]], "co": "71.4% of spell power (heal)", "d": "Heals a friendly target for 1,495 to 1,665."})
        self.assertEqual(g.render_entry(e), 'S:Define(25292, T.PALADIN, "Holy Light", { coeff = 0.714, base = 1580, mana = 660, cast = 2.5 }); -- Rank 9')

    def test_penance_tick_base_defaults_to_direct_base(self):
        e = g.build_entry("PRIEST", "Penance", "Rank 1", {"id": 402174, "l": [["", "Enemy: 36 yd range"], ["100 Mana", "Friendly: 40 yd range"], ["Channeled", "12 sec cooldown"]], "co": "28.5% of spell power (heal), 28.5% of spell power (per tick)", "d": "Launches a volley of holy light at the target, causing 81 Holy damage to an enemy, or 184 healing to an ally, instantly and every 1 sec for 2 sec."})
        self.assertEqual(e["opts"], {"coeff": 0.285, "base": 184, "coeffTick": 0.285, "baseTick": 184, "mana": 100, "cast": -1, "duration": 2, "tick": 1})

    def test_flags_and_notes(self):
        e = g.build_entry("PALADIN", "Lay on Hands", "Rank 1", {"id": 633, "l": [["", "40 yd range"], ["Instant", "20 min cooldown"]], "d": "Heals a friendly target for an amount equal to the Paladin's maximum health."})
        self.assertEqual(g.render_entry(e), 'S:Define(633, T.PALADIN, "Lay on Hands", { cd = true, canCrit = false }); -- Rank 1 (no coefficient in JSON; tooltip not parsed)')
        e = g.build_entry("DRUID", "Swiftmend", "", {"id": 18562, "l": [["20% of base mana", "40 yd range"], ["Instant", "15 sec cooldown"]], "d": "Instantly heals a target with an active Rejuvenation or Regrowth effect."})
        self.assertEqual(g.render_entry(e), 'S:Define(18562, T.DRUID, "Swiftmend", { manaPct = 0.2 }); -- (no coefficient in JSON; tooltip not parsed)')


class RealData(unittest.TestCase):
    def test_spot_values_from_json(self):
        text = g.render(g.collect())
        for line in [
            'S:Define(25292, T.PALADIN, "Holy Light", { coeff = 0.714, base = 1580, mana = 660, cast = 2.5 }); -- Rank 9',
            'S:Define(774, T.DRUID, "Rejuvenation", { coeffTick = 0.2, baseTick = 8, mana = 25, duration = 12, tick = 3 }); -- Rank 1',
            'S:Define(9858, T.DRUID, "Regrowth", { coeff = 0.286, base = 1021, coeffTick = 0.071, baseTick = 142, mana = 525, cast = 2, duration = 21, tick = 3 }); -- Rank 9',
            'S:Define(10623, T.SHAMAN, "Chain Heal", { coeff = 0.714, base = 506, mana = 405, cast = 2.5, targets = 3 }); -- Rank 3',
            'S:Define(740, T.DRUID, "Tranquility", { baseTick = 90, mana = 375, cast = -1, cd = true, duration = 10, tick = 2, party = true }); -- Rank 1 (no coefficient in JSON)',
            'S:Define(10901, T.PRIEST, "Power Word: Shield", { base = 928, mana = 500, canCrit = false }); -- Rank 10 (no coefficient in JSON)',
            'S:Define(402174, T.PRIEST, "Penance", { coeff = 0.285, base = 184, coeffTick = 0.285, baseTick = 184, mana = 100, cast = -1, duration = 2, tick = 1 }); -- Rank 1',
            'S:Define(5394, T.SHAMAN, "Healing Stream Totem", { baseTick = 5, mana = 40, duration = 300, tick = 2, party = true }); -- Rank 1 (no coefficient in JSON)',
        ]:
            self.assertIn(line, text)
        self.assertGreaterEqual(text.count("S:Define("), 160)   # 168 rank entries at export 2026-10-06
        self.assertTrue(text.startswith("-- GENERATED"))
