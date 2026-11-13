import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/SessionTotals.lua", "Classes/Util.lua", "Classes/BuffTracker.lua", "Classes/ManaDeficit.lua", "Classes/Segment.lua",
         "Classes/SegmentManager.lua", "Classes/StatParser.lua", "Classes/UnitManager.lua",
         "Parsers/Spells.lua", "Parsers/Spells_Generated.lua", "Parsers/Spells_Manual.lua", "Parsers/Talents_Generated.lua"]

TALENTS = {
    "PALADIN": 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5}, {name="Healing Light", rank=3, max=3} }}, {name="Protection", talents={ {name="Divine Intellect", rank=5, max=5} }}, {name="Retribution", talents={}} }',   # Divine Intellect is a Protection talent since 2026-10-30
    "DRUID": 'STUB.class = "DRUID"; STUB.talents = { {name="Balance", talents={}}, {name="Feral Combat", talents={}}, {name="Restoration", talents={ {name="Living Spirit", rank=3, max=3} }} }',
    "PRIEST": 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={ {name="Mental Strength", rank=5, max=5} }}, {name="Holy", talents={}} }',
    "SHAMAN": 'STUB.class = "SHAMAN"; STUB.talents = { {name="Elemental", talents={}}, {name="Enhancement", talents={}}, {name="Restoration", talents={ {name="Tidal Mastery", rank=5, max=5} }} }',
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
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdateEquipment(); a:UpdatePlayerStats()
        a.SegmentManager:Enqueue("fight"); a.UnitManager.units["Player-1"] = "player"
        function a.TestTotal(spell, amount)
            local seg, ttl = a.SegmentManager:Get(0), a.SegmentManager:Get("Total")
            a.StatParser:ApplyTotals(seg, {{ [spell] = amount }})
            seg.hits = {{}}; ttl.hits = {{}}
        end
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def heal(addon, ev, spell, amount, crit=False, dest="Player-1"):
    """One heal of `amount` on `dest`: counted at landing, priced from a session total of `amount`."""
    addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit)
    addon.TestTotal(spell, amount)


class Conversions(unittest.TestCase):
    def test_defaults_at_level_30(self):
        _, addon, _ = start("PALADIN")
        self.assertEqual((addon.CritConv, addon.HasteConv, addon.IntPerCrit, addon.RegenPerSpirit), (None, 100, 31.9, 0.125))   # crit is per 1% throughout: no rating conversion

    def test_int_per_crit_level_lookup_and_overrides(self):
        lua, addon, _ = start("DRUID", extra="STUB.level = 60")
        self.assertEqual(addon.IntPerCrit, 59.9)                 # level-60 datamine (foreverdb.net)
        lua.execute("STUB.level = 10")
        addon.SetupConversionFactors(addon)
        self.assertEqual(addon.IntPerCrit, 28.4)                 # below the lowest key: lowest key
        lua.execute("STUB.level = 45")
        addon.SetupConversionFactors(addon)
        self.assertAlmostEqual(addon.IntPerCrit, (28.4 + 59.9) / 2)   # halfway between the 30 and 60 keys
        lua.execute("STUB.level = 70")
        addon.SetupConversionFactors(addon)
        self.assertEqual(addon.IntPerCrit, 59.9)                 # above the highest key: highest key
        lua.execute("HSW_TEST_ADDON.hsw.db.global.intPerCritOverride.DRUID = 40; HSW_TEST_ADDON.hsw.db.global.hasteRatingPerPct = 10")
        addon.SetupConversionFactors(addon)
        self.assertEqual((addon.IntPerCrit, addon.HasteConv), (40, 1000))
        _, addon, _ = start("SHAMAN", extra="STUB.level = 29")
        self.assertAlmostEqual(addon.IntPerCrit, (26.3 + 28.2) / 2)   # between the level-28 measurement and the level-30 value
        _, addon, _ = start("SHAMAN", extra="STUB.level = 26")
        self.assertEqual(addon.IntPerCrit, 24.4)                 # measured in game 2026-11-12: 53 Int off, 2.168% crit less
        _, addon, _ = start("PALADIN", extra="STUB.level = 12")
        self.assertAlmostEqual(addon.IntPerCrit, 16.3 + 2 * (31.9 - 16.3) / 20)   # two levels past the level-10 measurement

    def test_unsupported_class_has_no_parser(self):
        _, addon = load(FILES, setup='STUB.class = "WARRIOR"; STUB.talents = { {name="Arms", talents={ {name="Deflection", rank=5, max=5} }} }')
        self.assertFalse(addon.StatParser.IsCurrentSpecSupported(addon.StatParser))
        addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, "SPELL_HEAL", "Player-1", HL, False)   # no parser: silently ignored, no error


class PlayerStats(unittest.TestCase):
    def test_reads_stub_apis(self):
        _, addon, _ = start("PALADIN")                            # Human, Divine Intellect 5/5
        self.assertEqual((addon.ply_sp, addon.ply_crt, addon.ply_crtbonus, addon.ply_hst), (200, 0.10, 0.5, 0))
        self.assertEqual((addon.ply_int, addon.ply_spi, addon.ply_maxmana), (110, 60, 3000))
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (10, 3))
        self.assertAlmostEqual(addon.ply_castpct, 0.3)
        self.assertAlmostEqual(addon.ply_intmult, 1.10)
        self.assertAlmostEqual(addon.ply_spiritmult, 1.10)        # The Human Spirit: 10% since the 26 Oct racial pass

    def test_crit_school_and_multipliers_by_class(self):
        lua, addon, _ = start("DRUID", extra='STUB.race = "Tauren"')   # Nature crit, Living Spirit 3/3
        self.assertAlmostEqual(addon.ply_crt, 0.12)
        self.assertAlmostEqual(addon.ply_intmult, 1.0)
        self.assertAlmostEqual(addon.ply_spiritmult, 1.15)
        lua.execute("STUB.regen = { base = 0, cast = 0 }")
        addon.UpdatePlayerStats(addon)
        self.assertEqual(addon.ply_castpct, 0)

    def test_secret_values_in_combat_keep_last_reading(self):
        # Forever hides +Healing and crit behind secret numbers in combat; the stub marks -777 as secret.
        lua, addon, _ = start("PALADIN")
        lua.execute("issecretvalue = function(v) return v == -777 end; STUB.sp = -777; STUB.critPct[2] = -777; STUB.haste = -777; STUB.stats[4][2] = 150")
        addon.UpdatePlayerStats(addon)
        self.assertEqual((addon.ply_sp, addon.ply_crt, addon.ply_hst), (200, 0.10, 0))   # kept
        self.assertEqual(addon.ply_int, 150)                                               # still readable: updated


class SpiritRegen(unittest.TestCase):
    """Forever regen is min(Spirit / 4, 6.25 + Spirit / 8) mana/s once gear MP5 is taken out
    (level-10 paladin and level-28 shaman, 2026-10-22/23): a point of Spirit is worth 0.25 under 50 Spirit, 0.125 from 50."""

    def test_rate_per_spirit_has_a_knee_at_50(self):
        _, addon, _ = start("PALADIN")                            # stub Spirit 60
        self.assertEqual(addon.RegenPerSpirit, 0.125)
        rate = lambda s: addon.GetRegenPerSpirit(addon, s)
        self.assertEqual((rate(29), rate(49), rate(50), rate(146)), (0.25, 0.25, 0.125, 0.125))

    def test_a_gear_swap_across_the_knee_updates_the_rate_in_use(self):
        lua, addon, _ = start("PALADIN")
        lua.execute("STUB.stats[5] = {30, 42, 12, 0}")            # 42 Spirit on
        addon.UpdatePlayerStats(addon)                            # PLAYER_EQUIPMENT_CHANGED path
        self.assertEqual(addon.RegenPerSpirit, 0.25)

    def test_gear_mp5_is_taken_off_both_regen_rates(self):
        # Forever folds gear MP5 into both GetManaRegen rates; C_Item.GetItemStats reports it per item (probe 2026-10-22)
        gear = ('STUB.regen = { base = 11, cast = 4 }'                       # 10 / 3 from Spirit plus 5 MP5 = 1 mana/s
                '; function GetInventoryItemLink(_, slot) return slot <= 2 and ("item" .. slot) or nil end'
                '; C_Item = { GetItemStats = function(link) return ({ item1 = { ITEM_MOD_MANA_REGENERATION_SHORT = 3 },'
                ' item2 = { ITEM_MOD_MANA_REGENERATION_SHORT = 2, ITEM_MOD_SPIRIT_SHORT = 6 } })[link] end }')
        lua, addon, _ = start("PALADIN", extra=gear)
        self.assertEqual(addon.ply_mp5, 5)
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (10, 3))
        self.assertAlmostEqual(addon.ply_castpct, 0.3)
        lua.execute("HSW_TEST_ADDON.inCombat = true; STUB.regen = { base = 21, cast = 9 }")   # a flat buff in combat: gear MP5 stays cached
        addon.UpdatePlayerStats(addon)
        self.assertEqual(addon.ply_mp5, 5)
        self.assertAlmostEqual(addon.ply_flat, 7.25)                         # 21 less the 13.75 of 60 Spirit: the gear's 1.0 and 6.25 more
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (13.75, 1.75))

    def test_what_the_base_rate_holds_above_spirit_is_flat_and_comes_off_both_rates(self):
        # Seen in game 2026-11-11: Might of Stormwind (10 MP5) raised both GetManaRegen() rates by 2.0 and the
        # casting share read 0.56 for 0.50. Spirit alone gives min(Spirit / 4, 6.25 + Spirit / 8).
        lua, addon, _ = start("PALADIN", extra="STUB.regen = { base = 15.75, cast = 5 }")   # 60 Spirit alone: 13.75
        self.assertAlmostEqual(addon.ply_flat, 2.0)
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (13.75, 3))
        self.assertAlmostEqual(addon.ply_castpct, 3 / 13.75)                 # the buff does not raise the casting share
        lua.execute("STUB.regen = { base = 13.75, cast = 3 }")
        addon.UpdatePlayerStats(addon)
        self.assertEqual(addon.ply_flat, 0)
        lua.execute("STUB.regen = { base = 10, cast = 3 }")                  # under the Spirit figure: nothing flat, the client's rate stands
        addon.UpdatePlayerStats(addon)
        self.assertEqual((addon.ply_flat, addon.ply_regen_base), (0, 10))
        lua.execute("STUB.stats[5] = {30, 40, 10, 0}; STUB.regen = { base = 12, cast = 3 }")   # under the knee: 40 / 4 = 10
        addon.UpdatePlayerStats(addon)
        self.assertAlmostEqual(addon.ply_flat, 2.0)
        self.assertEqual((addon.ply_regen_base, addon.ply_regen_cast), (10, 1))
        lua.execute("issecretvalue = function(v) return v == -777 end; STUB.regen = { base = -777, cast = -777 }")
        addon.UpdatePlayerStats(addon)                                       # unreadable in combat: the last reading stays
        self.assertEqual((addon.ply_flat, addon.ply_regen_base, addon.ply_regen_cast), (2, 10, 1))

    def test_a_swap_in_combat_is_read_once_combat_ends(self):
        lua, addon, _ = start("PALADIN", extra='function GetInventoryItemLink(_, slot) return slot == 1 and "item1" or nil end'
                                                '; C_Item = { GetItemStats = function() return { ITEM_MOD_MANA_REGENERATION_SHORT = 4 } end }')
        self.assertEqual(addon.ply_mp5, 4)
        lua.execute("HSW_TEST_ADDON.inCombat = true; C_Item.GetItemStats = function() return { ITEM_MOD_MANA_REGENERATION_SHORT = 9 } end")
        addon.UpdateEquipment(addon)                              # PLAYER_EQUIPMENT_CHANGED in combat: deferred
        addon.UpdatePlayerStats(addon)
        self.assertEqual(addon.ply_mp5, 4)
        lua.execute("HSW_TEST_ADDON.inCombat = false")
        addon.UpdatePlayerStats(addon)                            # first stats refresh out of combat picks it up
        self.assertEqual(addon.ply_mp5, 9)


class Derivatives(unittest.TestCase):
    def test_healing_derivative_is_the_coefficient_with_its_crits(self):
        _, addon, seg = start("PALADIN")                          # SP 200, crit 10%: 1.05 real healing per non-crit point
        expected = 1580 + 0.714 * 200
        heal(addon, "SPELL_HEAL", HL, expected)
        self.assertAlmostEqual(seg.t.heal, 0.714 * 1.05)
        heal(addon, "SPELL_HEAL", HL, expected * 1.1)             # +10% talent multiplier scales with it
        self.assertAlmostEqual(seg.t.heal, (0.714 + 0.714 * 1.1) * 1.05)

    def test_crit_int_haste_per_point(self):
        _, addon, seg = start("PALADIN")                          # crit 10%, haste 0
        heal(addon, "SPELL_HEAL", HL, 1000)
        per1 = 1000 * 0.5 / 100                                   # value of +1% crit: one more crit in a hundred heals
        self.assertAlmostEqual(seg.t.crit, per1)
        self.assertAlmostEqual(seg.t.int, per1 / 31.9 * 1.10)     # Divine Intellect 5/5: 1 Int on gear is 1.10 on the sheet
        self.assertAlmostEqual(seg.t.haste_hpct, 1000 * 1.05 / 100)   # haste speeds the crits up too
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
        self.assertAlmostEqual(seg.t.heal, 0.2 * 1.06)            # Nature crit 12%
        self.assertEqual(seg.t.haste_hpct, 0)                     # instant: no HPCT value
        self.assertGreater(seg.t.crit, 0)                         # HoT ticks crit on Forever

    def test_percent_of_base_mana_spell_is_filler_only_when_the_client_prices_it(self):
        # Swiftmend costs "20% of base mana": the table has no absolute cost, so its healing is filler
        # only when the cost API answers (the cast side records filler mana under the same condition).
        lua, addon, seg = start("DRUID")
        heal(addon, "SPELL_HEAL", 18562, 900)
        self.assertEqual((seg.totalHealing, seg.fillerHealing), (900, 0))
        lua.execute("STUB.spellCost[18562] = 250")
        heal(addon, "SPELL_HEAL", 18562, 900)
        self.assertEqual((seg.totalHealing, seg.fillerHealing), (1800, 900))

    def test_heals_log_ticks_shields_and_skip_excluded_cooldowns(self):
        lua, addon, seg = start("PRIEST")
        heal(addon, "SPELL_PERIODIC_HEAL", 25315, 200)                      # Renew R10 tick
        addon.StatParser.DecompShieldCast(addon.StatParser, "Player-1", PWS)
        lua.execute("HSW_TEST_ADDON.hsw.db.global.excludeRaidHealingCooldowns = true")
        heal(addon, "SPELL_HEAL", 19236, 300)                               # Desperate Prayer: excluded, not logged
        self.assertEqual(list(seg.events.values()), ["0.00,tick,25315,Renew,Me,,0,",
                                                     "0.00,total,25315,Renew,,200,,",
                                                     "0.00,heal,10901,Power Word: Shield,Me,948,0,"])

    def test_tick_without_a_coefficient_counts_in_totals_only(self):
        _, addon, seg = start("SHAMAN")
        heal(addon, "SPELL_PERIODIC_HEAL", 5394, 6)                # Healing Stream Totem: no coefficient yet
        self.assertEqual((seg.totalHealing, seg.fillerHealing, seg.t.heal), (6, 6, 0))

    def test_shield_cast_has_no_crit_value(self):
        _, addon, seg = start("PRIEST")
        addon.StatParser.DecompShieldCast(addon.StatParser, "Player-1", PWS)     # expected size 928 + 0.10 * 200
        self.assertAlmostEqual(seg.t.heal, 0.10)                  # cannot crit: nothing on top
        self.assertEqual((seg.t.crit, seg.t.int, seg.t.haste_hpct), (0, 0, 0))

    def test_filter_rules(self):
        lua, addon, seg = start("PALADIN")
        heal(addon, "SPELL_HEAL", REJUV, 500)                     # druid spell on a paladin: ignored
        self.assertEqual((seg.t.heal, seg.totalHealing), (0, 0))
        heal(addon, "SPELL_HEAL", HL, 500, dest="Creature-7")     # unknown unit: not counted, but the total is ours
        self.assertEqual(seg.totalHealing, 500)
        self.assertEqual(len(list(seg.hits.keys())), 0)
        heal(addon, "SPELL_HEAL", 999999, 500)                    # unknown spell: discovered as IGNORED
        self.assertEqual(addon.Spells.Get(addon.Spells, 999999).spellType, -1)
        lua.execute("HSW_TEST_ADDON.hsw.db.global.excludeRaidHealingCooldowns = true")
        heal(addon, "SPELL_HEAL", 633, 500)                       # Lay on Hands: raid cooldown excluded
        self.assertEqual(seg.totalHealing, 500)


class Overrides(unittest.TestCase):
    def test_crit_chance_and_per_segment_extras(self):
        ov = """{
            CritChance = function(ev, s, destUnit, C) return 1.0 end,
            CritBonus = function(ev, s, destUnit, CB) return 1.0 end,
            CriticalStrike = function(ev, s, heal, destUnit, C, CB, seg) return seg.id == "Total" and 2 or 1 end,
            Intellect = function(ev, s, heal, destUnit, _SP, seg) return _SP end,
            Spirit = function(ev, s, heal, destUnit, _SP, seg) return 0.5 * _SP end,
        }"""
        _, addon, seg = start("PALADIN", overrides=ov)
        heal(addon, "SPELL_HEAL", HL, 1000)
        per1 = 1000 * 1.0 / 100                                   # crit chance and crit bonus overridden to 100%
        self.assertAlmostEqual(seg.t.heal, 0.714 * 1000 / (1580 + 0.714 * 200) * 2)   # every heal a crit of twice the size
        self.assertAlmostEqual(seg.t.crit, per1 + 1)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.crit, per1 + 2)
        # Int buys crit with its extras (31.9 Int = 1%), and all of it scales with Divine Intellect 5/5
        self.assertAlmostEqual(seg.t.int, ((per1 + 1) / 31.9 + seg.t.heal) * 1.10)
        self.assertAlmostEqual(seg.t.spirit, 0.5 * seg.t.heal)
        heal(addon, "SPELL_HEAL", HL, 2000, crit=True)            # a crit heal is normalised with the overridden bonus
        self.assertAlmostEqual(seg.t.heal, 2 * 0.714 * 1000 / (1580 + 0.714 * 200) * 2)

    def test_per_hit_extras_are_counted_on_every_hit_of_the_fight(self):
        ov = """{
            CriticalStrike = function(ev, s, heal, destUnit, C, CB, seg) return heal / 100 + 1 end,
            FlatBonus = function(ev, s, destUnit) return 100 end,
        }"""
        _, addon, seg = start("PALADIN", overrides=ov)
        for crit in (False, False, True):
            addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, "SPELL_HEAL", "Player-1", HL, crit)
        addon.TestTotal(HL, 3500)                                 # 3 hits, 1 crit: 1000 a hit before crits
        self.assertAlmostEqual(seg.t.crit, 3000 * 0.5 / 100 + 3 * (1000 / 100 + 1))   # the override sees one hit's amount
        self.assertAlmostEqual(seg.t.heal, 0.714 * (3000 - 3 * 100) / (1580 + 0.714 * 200) * 1.05)


class ApplyTotals(unittest.TestCase):
    """Pricing a finished segment from per-spell effective totals and the hits counted during the fight."""

    def count(self, addon, spell, ev="SPELL_HEAL", crit=False, dest="Player-1"):
        addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit)

    def apply(self, lua, spell, amount):
        lua.execute(f"local a = HSW_TEST_ADDON; a.StatParser:ApplyTotals(a.SegmentManager:Get(0), {{ [{spell}] = {amount} }})")

    def test_total_without_hits_is_priced_as_one_non_crit_heal(self):
        lua, addon, seg = start("PALADIN")
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        self.apply(lua, HL, 1580 + 0.714 * 200)
        self.assertAlmostEqual(seg.t.heal, 0.714 * 1.05)
        self.assertEqual(seg.totalHealing, 1580 + 0.714 * 200)
        self.assertIn("had no matched heals", lua.globals().MSGS[1])

    def test_crits_normalise_the_total(self):
        lua, addon, seg = start("PALADIN")                       # CB 0.5
        for crit in (False, True, True, False):
            self.count(addon, HL, crit=crit)
        self.apply(lua, HL, 5000)                                 # 4 hits, 2 crits: about h * (4 + 2 * 0.5) = 5 h
        _, addon2, seg2 = start("PALADIN")                         # four non-crit heals of 1000 must price the same
        heal(addon2, "SPELL_HEAL", HL, 1000); heal(addon2, "SPELL_HEAL", HL, 1000)
        heal(addon2, "SPELL_HEAL", HL, 1000); heal(addon2, "SPELL_HEAL", HL, 1000)
        self.assertAlmostEqual(seg.t.heal, seg2.t.heal)
        self.assertAlmostEqual(seg.t.crit, seg2.t.crit)
        self.assertEqual(seg.totalHealing, 5000)                   # totals keep the effective amount

    def test_direct_and_tick_parts_split_by_expected_size(self):
        lua, addon, seg = start("DRUID")                           # SP 200; Regrowth R9: direct 1021 + .286 sp, tick 142 + .071 sp
        self.count(addon, 9858)
        for _ in range(7):
            self.count(addon, 9858, ev="SPELL_PERIODIC_HEAL")
        ed, et = 1021 + 0.286 * 200, 142 + 0.071 * 200
        self.apply(lua, 9858, ed + 7 * et)
        self.assertAlmostEqual(seg.t.heal, (0.286 + 7 * 0.071) * 1.06)   # Nature crit 12%
        self.assertAlmostEqual(seg.t.haste_hpct, (ed + 7 * et) * 1.06 / 100)   # a cast-time spell carries haste on both parts, as before

    def test_tick_only_and_direct_only_spells(self):
        lua, addon, seg = start("DRUID")
        for _ in range(4):
            self.count(addon, REJUV, ev="SPELL_PERIODIC_HEAL")
        self.apply(lua, REJUV, 4 * (194 + 0.2 * 200))
        self.assertAlmostEqual(seg.t.heal, 0.8 * 1.06)
        lua, addon, seg = start("PALADIN")
        self.count(addon, HL)
        self.apply(lua, HL, 1000)
        self.assertEqual(seg.hits[HL].tick.n, 0)
        self.assertEqual(seg.totalHealing, 1000)

    def test_alias_unknown_and_filtered_ids(self):
        lua, addon, seg = start("PALADIN")
        self.apply(lua, 25903, 1000)                               # Holy Shock R4 heal id -> book 20930
        self.assertGreater(seg.t.heal, 0)
        self.apply(lua, 999999, 1000)                              # unknown: discovered, not priced
        self.assertEqual(addon.Spells.Get(addon.Spells, 999999).spellType, -1)
        before = seg.totalHealing
        self.apply(lua, REJUV, 1000)                               # a druid spell on a paladin
        lua.execute("HSW_TEST_ADDON.hsw.db.global.excludeRaidHealingCooldowns = true")
        self.apply(lua, 633, 1000)                                 # Lay on Hands under the exclusion
        self.assertEqual(seg.totalHealing, before)

    def test_top_target_drives_the_destination_unit(self):
        lua, addon, seg = start("PALADIN", overrides='{ FlatBonus = function(ev, s, destUnit) return destUnit == "party1" and 400 or 0 end }',
                                extra='STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"')
        lua.execute('local a = HSW_TEST_ADDON; a.UnitManager.units["Player-2"] = "party1"; a.UnitManager.names = { Me = "player", Bob = "party1" }')
        self.count(addon, HL, dest="Player-2"); self.count(addon, HL, dest="Player-2"); self.count(addon, HL)
        self.apply(lua, HL, 3000)
        self.assertAlmostEqual(seg.t.heal, 0.714 * (3000 - 3 * 400) / (1580 + 0.714 * 200) * 1.05)   # Bob is the top target: the Oath's 400 comes off each of the three hits

    def test_total_segment_is_credited_once(self):
        lua, addon, seg = start("PALADIN")
        self.count(addon, HL)
        self.apply(lua, HL, 1000)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.t.heal, seg.t.heal)
        self.assertEqual(ttl.totalHealing, 1000)

    def test_mana_return_is_credited_at_the_crit(self):
        ov = '{ ManaReturn = function(ev, s, heal, destUnit) return 50 end }'
        lua, addon, seg = start("PALADIN", overrides=ov)
        self.count(addon, HL)
        self.assertEqual(seg.manaRestore, 0)
        self.count(addon, HL, crit=True)
        self.assertEqual(seg.manaRestore, 50)                      # before any total arrives

    def test_count_logs_and_prints_under_testing(self):
        lua, addon, seg = start("PALADIN")
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_ENABLE_FOR_TESTING = true')
        self.count(addon, HL, crit=True)
        self.assertEqual(list(seg.events.values()), ["0.00,heal,25292,Holy Light,Me,,1,"])
        self.assertEqual(lua.globals().MSGS[1], "count spellid=25292 destunit=player tick=0 crit=1")
        self.apply(lua, HL, 1500)
        self.assertEqual(lua.globals().MSGS[2], "allocate spellid=25292 destunit=player amount=1000")
