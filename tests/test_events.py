import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Events.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'
PRIEST = 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={ {name="Meditation", rank=3, max=3} }}, {name="Holy", talents={}} }'
HL = 25292     # Holy Light R9, 660 mana, filler
PWS = 10901    # Power Word: Shield R10


def start(setup=PALADIN, spec=65, extra=""):
    """In combat, parser registered for `spec`, one unnamed live segment, player GUID cached."""
    lua, addon = load(FILES, setup=setup + "\n" + extra)
    lua.execute(f"""
        local a = HSW_TEST_ADDON
        a.StatParser:Create({spec}, {{}})
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.SegmentManager:Enqueue(); a.UnitManager.units["Player-1"] = "player"
        a.inCombat = true
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def fire(lua, addon, payload):
    """`payload` is the Lua list CombatLogGetCurrentEventInfo() should return (22 slots, trailing nils allowed)."""
    lua.execute(f"CLEU = {{ {payload} }}; function CombatLogGetCurrentEventInfo() return unpack(CLEU, 1, 22) end")
    addon.hsw.COMBAT_LOG_EVENT_UNFILTERED(addon.hsw)


SRC = '0, "%s", false, "Player-1", "Me", 0, 0, '                       # timestamp, event, hideCaster, source
HEAL = SRC % "SPELL_HEAL" + '"Player-1", "Me", 0, 0, %d, "x", 2, %d, %d, 0, %s'   # dest..., spellID, amount, overhealing, critFlag


class CombatLog(unittest.TestCase):
    def test_heal_and_crit_heal_are_decomposed(self):
        lua, addon, seg = start()
        fire(lua, addon, HEAL % (HL, 1000, 0, "false"))
        self.assertGreater(seg.t.heal, 0)
        self.assertEqual((seg.totalHealing, seg.fillerHealing), (1000, 1000))
        before = seg.t.crit
        fire(lua, addon, HEAL % (HL, 1500, 0, "true"))          # crit for 1500 == non-crit 1000
        self.assertAlmostEqual(seg.t.crit, before * 2)

    def test_overheal_is_subtracted_from_amount(self):
        lua, addon, seg = start()
        fire(lua, addon, HEAL % (HL, 1000, 200, "false"))       # effective 800, overheal 200 -> no derivatives
        self.assertEqual((seg.t.heal, seg.totalHealing), (0, 800))

    def test_summon_heals_count_other_sources_do_not(self):
        lua, addon, seg = start()
        other = '0, "SPELL_HEAL", false, "Creature-5", "Totem", 0, 0, "Player-1", "Me", 0, 0, %d, "x", 2, %d, %d, 0, %s'
        fire(lua, addon, other % (HL, 1000, 0, "false"))
        self.assertEqual(seg.totalHealing, 0)
        fire(lua, addon, SRC % "SPELL_SUMMON" + '"Creature-5", "Totem", 0, 0, 5394, "Healing Stream Totem", 8')
        fire(lua, addon, other % (HL, 1000, 0, "false"))
        self.assertEqual(seg.totalHealing, 1000)

    def test_filler_cast_records_mana(self):
        lua, addon, seg = start()
        cast = SRC % "SPELL_CAST_SUCCESS" + '"", "", 0, 0, %d, "x", 2'
        fire(lua, addon, cast % HL)                              # no cost API in stub -> table cost 660
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (1, 660))
        lua.execute(f"STUB.spellCost[{HL}] = 500")               # cost API wins (talent reductions, downranks)
        fire(lua, addon, cast % HL)
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (2, 1160))
        fire(lua, addon, cast % 633)                             # Lay on Hands: not a filler
        fire(lua, addon, cast % 424242)                          # unknown spell
        self.assertEqual(seg.fillerCasts, 2)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.fillerManaSpent, 1160)

    def test_energize_from_mana_return_spells(self):
        lua, addon, seg = start()
        energize = SRC % "SPELL_ENERGIZE" + '"Player-1", "Me", 0, 0, %d, "x", 2, 330, 0'
        fire(lua, addon, energize % 20272)                       # Illumination
        self.assertEqual(seg.manaRestore, 330)
        fire(lua, addon, energize % 424242)                      # not a tracked mana return
        self.assertEqual(seg.manaRestore, 330)
        innervate = '0, "SPELL_ENERGIZE", false, "Player-7", "Druid", 0, 0, "Player-1", "Me", 0, 0, 29166, "Innervate", 8, 100, 0'
        fire(lua, addon, innervate)                              # from someone else, to the player
        self.assertEqual(seg.manaRestore, 430)
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        fire(lua, addon, energize % 424242)                      # discovery mode reports an untracked mana return once
        fire(lua, addon, energize % 424242)
        self.assertEqual(len(list(lua.globals().MSGS.keys())), 1)
        self.assertIn("424242", lua.globals().MSGS[1])

    def test_absorbs_both_layouts(self):
        lua, addon, seg = start(PRIEST, 256)
        spell_layout = '0, "SPELL_ABSORBED", false, "Creature-9", "Mob", 0, 0, "Player-1", "Me", 0, 0, 100, "Fireball", 4, "Player-1", "Me", 0, 0, %d, "Power Word: Shield", 2, 300'
        swing_layout = '0, "SPELL_ABSORBED", false, "Creature-9", "Mob", 0, 0, "Player-1", "Me", 0, 0, "Player-1", "Me", 0, 0, %d, "Power Word: Shield", 2, 300'
        fire(lua, addon, spell_layout % PWS)
        self.assertEqual(seg.totalHealing, 300)
        fire(lua, addon, swing_layout % PWS)
        self.assertEqual(seg.totalHealing, 600)
        self.assertGreater(seg.t.heal, 0)
        fire(lua, addon, swing_layout % 424242)                  # some other absorb
        self.assertEqual(seg.totalHealing, 600)

    def test_segment_named_from_first_enemy(self):
        lua, addon, seg = start()
        fire(lua, addon, '0, "SWING_DAMAGE", false, "Creature-9", "Scarlet Monk", 0, 0, "Player-1", "Me", 0, 0, 50')
        self.assertEqual(seg.id, "Scarlet Monk")
        fire(lua, addon, '0, "SPELL_DAMAGE", false, "Player-1", "Me", 0, 0, "Creature-10", "Other", 0, 0, 100, "x", 2, 50')
        self.assertEqual(seg.id, "Scarlet Monk")                 # first name sticks

    def test_ignored_out_of_combat(self):
        lua, addon, seg = start()
        addon.inCombat = False
        fire(lua, addon, HEAL % (HL, 1000, 0, "false"))
        self.assertEqual(seg.totalHealing, 0)


class FiveSecondRule(unittest.TestCase):
    def test_mana_cast_starts_fsr_and_accumulates(self):
        lua, addon, seg = start()
        self.assertIsNone(addon.lastManaSpend)
        addon.OnPlayerSpellcast(addon, HL)                       # t=0, table cost 660
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.time = 8")
        addon.OnPlayerSpellcast(addon, HL)
        self.assertEqual(addon.lastManaSpend, 8)
        self.assertAlmostEqual(seg.timeInFSR, 5)
        self.assertAlmostEqual(seg.timeOutsideFSR, 3)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.timeInFSR, 5)

    def test_free_casts_and_unknown_costs_do_not(self):
        lua, addon, seg = start()
        addon.OnPlayerSpellcast(addon, 633)                      # Lay on Hands: no mana cost
        addon.OnPlayerSpellcast(addon, 424242)                   # unknown spell, no cost API
        self.assertIsNone(addon.lastManaSpend)
        lua.execute("STUB.spellCost[424242] = 10")
        addon.OnPlayerSpellcast(addon, 424242)                   # unknown spell but the client says it costs mana
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.time = 3; STUB.auras = { {id=14751} }; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs()")
        addon.OnPlayerSpellcast(addon, HL)                       # Inner Focus up: free cast
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.auras = {}; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs(); STUB.spellCost[%d] = 0" % HL)
        addon.OnPlayerSpellcast(addon, HL)                       # client reports 0 cost (e.g. Clearcasting consumed)
        self.assertEqual(addon.lastManaSpend, 0)
        addon.inCombat = False
        lua.execute("STUB.spellCost[%d] = nil" % HL)
        addon.OnPlayerSpellcast(addon, HL)                       # out of combat: ignored
        self.assertEqual(addon.lastManaSpend, 0)


class Handlers(unittest.TestCase):
    def test_entering_world_and_talent_change_rebuild_state(self):
        lua, addon, _ = start()
        lua.execute("STUB.talents[1].talents[1].rank = 3")
        addon.hsw.PLAYER_ENTERING_WORLD(addon.hsw)
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 3)
        lua.execute("STUB.talents[1].talents[1].rank = 1; HSW_TEST_ADDON.hsw.db.global.intPerCritOverride.PALADIN = 50")
        addon.hsw.CHARACTER_POINTS_CHANGED(addon.hsw)
        self.assertEqual((addon.GetTalentRank(addon, "Illumination"), addon.IntPerCrit), (1, 50))
        addon.hsw.PLAYER_TALENT_UPDATE(addon.hsw)
        lua.execute("STUB.talents[1].talents[1].rank = 2")
        addon.hsw.TRAIT_TREE_CURRENCY_INFO_UPDATED(addon.hsw, "TRAIT_TREE_CURRENCY_INFO_UPDATED", 1082)   # the event Forever fires on a point spend
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 2)
        addon.hsw.PLAYER_EQUIPMENT_CHANGED(addon.hsw)
        addon.hsw.COMBAT_RATING_UPDATE(addon.hsw)
        self.assertEqual(addon.ply_sp, 200)

    def test_retail_handlers_are_gone(self):
        _, addon, _ = start()
        for name in ("CHALLENGE_MODE_START", "CHALLENGE_MODE_COMPLETED", "CHALLENGE_MODE_RESET", "PLAYER_SPECIALIZATION_CHANGED"):
            self.assertIsNone(addon.hsw[name])
