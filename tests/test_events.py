import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Events.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'
PRIEST = 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={ {name="Meditation", rank=3, max=3} }}, {name="Holy", talents={}} }'
SHAMAN = 'STUB.class = "SHAMAN"; STUB.talents = { {name="Elemental", talents={}}, {name="Enhancement", talents={}}, {name="Restoration", talents={ {name="Tidal Mastery", rank=1, max=5} }} }'
PARTY = 'STUB.group = "party"; STUB.groupSize = 1; STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"'
HL = 25292     # Holy Light R9, 660 mana, filler, 2.5 s cast
FH = 10917     # Flash Heal R7, filler
PWS = 10901    # Power Word: Shield R10
INNER_FOCUS, WEAKENED_SOUL, WATER_SHIELD = 14751, 6788, 408510


def start(setup=PALADIN, spec=65, extra=""):
    """In combat, parser registered for `spec`, unit events wired to a stub frame, one unnamed live segment."""
    lua, addon = load(FILES, setup=setup + "\n" + extra)
    lua.execute(f"""
        local a = HSW_TEST_ADDON
        a.StatParser:Create({spec}, {{}})
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.frame = CreateFrame(); a:SetupUnitEvents()
        a.SegmentManager:Enqueue(); a.UnitManager:Cache()
        a.inCombat = true
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def fire(addon, event, *args):
    """Delivers a unit event the way the client would: through the frame's OnEvent script."""
    addon.frame.OnEvent(addon.frame, event, *args)


def cast(addon, spell, target=""):
    fire(addon, "UNIT_SPELLCAST_SENT", "player", target, "cast-guid", spell)
    fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-guid", spell)


class UnitEvents(unittest.TestCase):
    def test_heal_and_crit_heal_are_decomposed(self):
        lua, addon, seg = start()
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 1000, 2)
        self.assertGreater(seg.t.heal, 0)
        self.assertEqual((seg.totalHealing, seg.fillerHealing), (1000, 1000))
        before = seg.t.crit
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "CRITICAL", 1500, 2)   # crit for 1500 == non-crit 1000
        self.assertAlmostEqual(seg.t.crit, before * 2)

    def test_heals_on_others_need_a_cast_on_them(self):
        lua, addon, seg = start(extra=PARTY)
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)           # not ours
        self.assertEqual(seg.totalHealing, 0)
        cast(addon, HL, "Bob")
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)
        self.assertEqual(seg.totalHealing, 1000)

    def test_filler_cast_records_mana(self):
        lua, addon, seg = start()
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HL)          # no cost API in stub -> table cost 660
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (1, 660))
        lua.execute(f"STUB.spellCost[{HL}] = 500")                           # cost API wins (talent reductions, downranks)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HL)
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (2, 1160))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 633)         # Lay on Hands: not a filler
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 424242)      # unknown spell
        self.assertEqual(seg.fillerCasts, 2)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.fillerManaSpent, 1160)

    def test_shield_cast_is_credited_at_cast_with_weakened_soul(self):
        lua, addon, seg = start(PRIEST, 256)
        cast(addon, PWS)
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)
        self.assertGreater(seg.t.heal, 0)
        self.assertTrue(addon.BuffTracker.TargetHas(addon.BuffTracker, "player", WEAKENED_SOUL))
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 500, 1)             # no expectation was opened for the shield
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)

    def test_self_cast_buffs_are_marked_and_inner_focus_consumed(self):
        lua, addon, seg = start(PRIEST, 256)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", INNER_FOCUS)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, INNER_FOCUS), 1)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)          # free cast: spends Inner Focus, no FSR
        self.assertIsNone(addon.lastManaSpend)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, INNER_FOCUS), 0)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)
        self.assertEqual(addon.lastManaSpend, 0)
        lua, addon, seg = start(SHAMAN, 264)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", WATER_SHIELD)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, WATER_SHIELD), 1)

    def test_failed_cast_opens_no_heal(self):
        lua, addon, seg = start()
        fire(addon, "UNIT_SPELLCAST_SENT", "player", "", "g", HL)
        fire(addon, "UNIT_SPELLCAST_FAILED", "player", "g", HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 1000, 2)
        self.assertEqual(seg.totalHealing, 0)

    def test_ignored_out_of_combat(self):
        lua, addon, seg = start()
        addon.inCombat = False
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 1000, 2)
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

    def test_combat_log_and_retail_handlers_are_gone(self):
        _, addon, _ = start()
        for name in ("COMBAT_LOG_EVENT_UNFILTERED", "CHALLENGE_MODE_START", "CHALLENGE_MODE_COMPLETED", "CHALLENGE_MODE_RESET", "PLAYER_SPECIALIZATION_CHANGED"):
            self.assertIsNone(addon.hsw[name])
