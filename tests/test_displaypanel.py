import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Parsers/HolyPaladin.lua", "DisplayPanel.lua", "Core.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'
ALWAYS = "HSW_TEST_SAVED = { alwaysEnabled = true }"
HEAL = ('local a = HSW_TEST_ADDON; a.SegmentManager:Get(0):IncFillerCasts(660)'
        '; a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false)'
        '; a.StatParser:ApplyTotals(a.SegmentManager:Get(0), { [25292] = 1000 })')


def start(extra=""):
    lua, addon = load(FILES, setup=PALADIN + "\n" + extra)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.hsw:OnInitialize()
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
    """)
    return lua, addon


def seg(addon, which=0):
    return addon.SegmentManager.Get(addon.SegmentManager, which)


class ContentGates(unittest.TestCase):
    def test_instance_type_gates(self):
        lua, addon = start()
        self.assertFalse(addon.Enabled(addon))                                   # open world
        lua.execute('STUB.instance.type = "party"')
        self.assertTrue(addon.Enabled(addon))
        self.assertFalse(addon.InRaidInstance(addon))
        lua.execute('STUB.instance.type = "raid"')
        self.assertTrue((addon.Enabled(addon), addon.InRaidInstance(addon)) == (True, True))
        lua.execute('HSW_TEST_ADDON.hsw.db.global.enabledInRaids = false')
        self.assertFalse(addon.Enabled(addon))
        lua.execute('STUB.instance.type = "pvp"')
        self.assertFalse(addon.Enabled(addon))
        lua.execute('HSW_TEST_ADDON.hsw.db.global.enabledInBattlegrounds = true')
        self.assertTrue(addon.Enabled(addon))
        lua.execute('STUB.instance.type = "none"; HSW_TEST_ADDON.hsw.db.global.alwaysEnabled = true')
        self.assertTrue(addon.Enabled(addon))

    def test_unsupported_spec_never_enabled(self):
        lua, addon = start(extra='STUB.class = "WARRIOR"; STUB.talents = {}; ' + ALWAYS)
        self.assertFalse(addon.Enabled(addon))


class Fights(unittest.TestCase):
    def test_start_and_end_fight(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss", True)
        self.assertTrue(addon.inCombat)
        cur, ttl = seg(addon), seg(addon, "Total")
        self.assertEqual((cur.id, cur.bossFight), ("Boss", True))
        self.assertEqual((ttl.startTime, ttl.fsrLastAccum), (cur.startTime, cur.startTime))
        lua.execute(HEAL + "; STUB.time = 100")
        addon.EndFight(addon)
        self.assertFalse(addon.inCombat)
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertEqual(len(list(addon.pendingSegments.keys())), 0)            # no sessions in the stub: finalised at once
        self.assertAlmostEqual(cur.totalDuration, 100)
        self.assertAlmostEqual(ttl.totalDuration, 100)
        self.assertAlmostEqual(ttl.timeOutsideFSR, 100)
        addon.StartFight(addon, "Trash")
        addon.StartFight(addon, "Again")                                        # already in combat: ignored
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 2)
        self.assertEqual((seg(addon).id, seg(addon).bossFight), ("Trash", False))   # named is not boss


class ClassTotals(unittest.TestCase):
    """Boss Total and Trash Total: live segments beside the Total, fed by the fight's class."""

    def test_manager_holds_three_totals(self):
        lua, addon = start(extra=ALWAYS)
        self.assertEqual(seg(addon, "Total").id, "Total")
        self.assertEqual(seg(addon, "Bosses").id, "Boss Total")
        self.assertEqual(seg(addon, "Trash").id, "Trash Total")
        self.assertEqual((seg(addon, "Bosses").startTime, seg(addon, "Trash").startTime), (-1, -1))
        addon.SegmentManager.ResetAllSegments(addon.SegmentManager)
        self.assertEqual(seg(addon, "Bosses").id, "Boss Total")                 # recreated with the Total

    def test_for_each_live_includes_the_class_total(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss", True)
        lua.execute('HSW_TEST_ADDON.SegmentManager:Get(0).class = "Bosses"; SEEN = {}; HSW_TEST_ADDON.SegmentManager:ForEachLive(function(s) table.insert(SEEN, s.id) end)')
        self.assertEqual(list(lua.globals().SEEN.values()), ["Boss", "Total", "Boss Total"])
        lua.execute('HSW_TEST_ADDON.SegmentManager:Get(0).class = nil; SEEN = {}; HSW_TEST_ADDON.SegmentManager:ForEachLive(function(s) table.insert(SEEN, s.id) end)')
        self.assertEqual(list(lua.globals().SEEN.values()), ["Boss", "Total"])

    def fight(self, lua, addon, name, boss, session, healing, end_time):
        addon.StartFight(addon, name, boss)
        lua.execute(f'STUB.sessions[#STUB.sessions + 1] = {{ sessionID = {session}, name = "{name}", heals = {{ ["Player-1"] = {{ [25292] = {healing} }} }} }}; STUB.time = {end_time}')
        addon.EndFight(addon)

    def test_dungeon_boss_feeds_bosses_and_trash_feeds_trash(self):
        lua, addon = start(extra='STUB.instance = { name = "Deadmines", type = "party", difficultyId = 1 }')
        self.fight(lua, addon, "VanCleef", True, 1, 1000, 10)
        self.assertEqual(seg(addon, 0)["class"], "Bosses")
        self.assertEqual((seg(addon, "Total").totalHealing, seg(addon, "Bosses").totalHealing, seg(addon, "Trash").totalHealing), (1000, 1000, 0))
        self.assertEqual((seg(addon, "Total").fights, seg(addon, "Bosses").fights, seg(addon, "Trash").fights), (1, 1, 0))
        self.fight(lua, addon, None, False, 2, 300, 20)
        self.assertEqual(seg(addon, 0)["class"], "Trash")
        self.assertEqual((seg(addon, "Total").totalHealing, seg(addon, "Bosses").totalHealing, seg(addon, "Trash").totalHealing), (1300, 1000, 300))
        self.assertEqual((seg(addon, "Total").fights, seg(addon, "Bosses").fights, seg(addon, "Trash").fights), (2, 1, 1))
        self.assertAlmostEqual(seg(addon, "Trash").totalDuration, 10)              # live for its fight only
        self.assertAlmostEqual(seg(addon, "Bosses").totalDuration, 10)
        self.assertAlmostEqual(seg(addon, "Total").totalDuration, 20)

    def test_open_world_pull_feeds_the_total_only(self):
        lua, addon = start(extra=ALWAYS)
        self.fight(lua, addon, "Fleshripper", False, 1, 200, 10)
        self.assertIsNone(seg(addon, 0)["class"])                                  # right after EndFight the finished fight is still Get(0)
        self.assertEqual((seg(addon, "Total").totalHealing, seg(addon, "Bosses").totalHealing, seg(addon, "Trash").totalHealing), (200, 0, 0))
        self.assertEqual((seg(addon, "Bosses").startTime, seg(addon, "Trash").startTime), (-1, -1))

    def test_raid_trash_feeds_the_trash_total_but_is_not_logged(self):
        lua, addon = start(extra='STUB.instance = { name = "MC", type = "raid", difficultyId = 14 }')
        self.fight(lua, addon, "Core Hound", False, 1, 500, 10)
        self.assertEqual(addon.History.Size(addon.History), 0)
        self.assertEqual((seg(addon, "Trash").totalHealing, seg(addon, "Trash").fights), (500, 1))

    def test_manual_segment_counts_as_boss(self):
        lua, addon = start(extra=ALWAYS)
        addon.ToggleFight(addon)                                                 # the window button: boss flag set
        self.assertEqual(seg(addon)["class"], "Bosses")
        addon.EndFight(addon)

    def test_menu_rows_and_titles(self):
        lua, addon = start(extra=ALWAYS)
        lua.execute('MENU = nil; function HSW_TEST_ADDON.Compat.ShowContextMenu(items) MENU = items end')
        addon.StartFight(addon, "Boss", True)
        addon.SetCurrentSegment(addon, "Bosses")
        addon.SegmentMenu(addon)
        rows = [(r.text, r.checked) for r in lua.globals().MENU.values()]
        self.assertEqual([t for t, _ in rows], ["Select a Segment", "Total", "Boss Total", "Trash Total", "Current Fight"])   # the open fight is "Current Fight"; past fights follow
        self.assertEqual([t for t, c in rows if c], ["Boss Total"])
        addon.SetCurrentSegment(addon, "Trash")
        addon.SegmentMenu(addon)
        self.assertEqual([r.text for r in lua.globals().MENU.values() if r.checked], ["Trash Total"])
        addon.SetCurrentSegment(addon, 0)
        addon.SegmentMenu(addon)
        self.assertEqual([r.text for r in lua.globals().MENU.values() if r.checked], ["Current Fight"])
        addon.SetCurrentSegment(addon, 1)                                       # Get(1) is nil with one fight: no row checked
        addon.SegmentMenu(addon)
        self.assertEqual([r.text for r in lua.globals().MENU.values() if r.checked], [])
        lua.execute("TITLES = {}; function HSW_TEST_ADDON:UpdateDisplayTitle(t) table.insert(TITLES, t) end")
        addon.SetCurrentSegment(addon, "Bosses")
        addon.SetCurrentSegment(addon, "Trash")
        addon.SetCurrentSegment(addon, "Total")
        self.assertEqual(list(lua.globals().TITLES.values()), ["Boss Total", "Trash Total", "Total"])


class Display(unittest.TestCase):
    def test_stats_for_display_follow_current_segment(self):
        lua, addon = start(extra=ALWAYS)
        self.assertEqual(tuple(addon.GetStatsForDisplay(addon)), (1, 0, 0, 0, 0, 0))
        addon.StartFight(addon, "Boss")
        lua.execute(HEAL)
        addon.SetCurrentSegment(addon, 0)
        self.assertEqual(tuple(addon.GetStatsForDisplay(addon)), tuple(addon.GetStatsForSegment(addon, seg(addon))))
        addon.SetCurrentSegment(addon, "Total")
        self.assertEqual(tuple(addon.GetStatsForDisplay(addon)), tuple(addon.GetStatsForSegment(addon, seg(addon, "Total"))))
        self.assertGreater(addon.GetStatsForDisplay(addon)[1], 0)

    def test_update_display_stats_accumulates_fsr(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss")
        addon.lastManaSpend = 0
        lua.execute("STUB.time = 8")
        addon.UpdateDisplayStats(addon)                                          # no frame yet: still accumulates
        self.assertAlmostEqual(seg(addon).timeInFSR, 5)
        self.assertAlmostEqual(seg(addon).timeOutsideFSR, 3)

    def test_pawn_strings(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss")
        lua.execute(HEAL)
        addon.SetCurrentSegment(addon, 0)
        s = addon.GetPawnString(addon)
        self.assertTrue(s.startswith('( Pawn: v1: "Boss": Class=PALADIN, Spec=1, Healing=1.00, CritRating='), s)   # Pawn on Forever: "Healing"; scale named after the segment
        self.assertIn(", HasteRating=", s)                                       # Pawn's own names: it knows no "SpellHaste"
        self.assertNotIn("Spell", s)
        self.assertTrue(s.endswith(")") and "Mp5=" in s and "Versatility" not in s, s)
        lua.execute("STUB.time = 50")
        addon.EndFight(addon)
        h = addon.GetPawnStringFromHistory(addon, 0)
        self.assertTrue(h.startswith('( Pawn: v1: "Boss": Class=PALADIN, Spec=1, Healing=1.00'), h)

    def test_pawn_dialogs_fill_the_popup_edit_box(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss")
        lua.execute(HEAL)
        lua.execute("STUB.time = 50")
        addon.EndFight(addon)
        addon.SetCurrentSegment(addon, 0)
        lua.execute("""
            local a = HSW_TEST_ADDON
            local box = { SetText = function(self, s) self.text = s end }
            SHOWN = {}
            StaticPopupDialogs[a.PawnHistoryDialogName].OnShow({ EditBox = box })      -- Forever: GameDialog names it EditBox
            SHOWN[1] = box.text; box.text = nil
            StaticPopupDialogs["HSW_GETPAWNSTRING"].OnShow({ editBox = box })          -- older clients
            SHOWN[2] = box.text
        """)
        shown = lua.globals().SHOWN
        self.assertTrue(shown[1].startswith('( Pawn: v1: "Boss"'), shown[1])
        self.assertTrue(shown[2].startswith('( Pawn: v1: "Boss"'), shown[2])

    def test_chat_start_end_and_segment_menu(self):
        lua, addon = start()
        addon.hsw.ChatCommand(addon.hsw, "start")
        self.assertTrue(lua.globals().HSW_ENABLE_FOR_TESTING)
        self.assertTrue(addon.inCombat)
        self.assertEqual(seg(addon).id, "test")
        addon.SegmentMenu(addon)                                                 # EasyMenu stub: must not error
        addon.hsw.ChatCommand(addon.hsw, "end")
        self.assertFalse(addon.inCombat)
        self.assertIsNone(lua.globals().HSW_ENABLE_FOR_TESTING)              # debug mode ends with the test segment


FAKE_FRAME = """
    local noop = function() end
    FB = { textures = {} }
    function FB:SetNormalTexture(t) self.textures.normal = t end
    function FB:SetHighlightTexture(t) self.textures.highlight = t end
    HSW_TEST_ADDON.frame = { fightButton = FB, Show = noop, Hide = noop,
        textL = { SetText = noop }, textR = { SetFormattedText = noop }, textTitle = { SetFormattedText = noop } }
"""
GREEN = "Interface\\COMMON\\Indicator-Green"
RED = "Interface\\COMMON\\Indicator-Red"


def button(addon):
    b = addon.frame.fightButton
    return b.title, b.textures.normal, b.textures.highlight


class FightButton(unittest.TestCase):
    def test_no_frame_is_a_noop(self):
        lua, addon = start()
        addon.UpdateFightButton(addon)                                           # addon.frame is nil here
        self.assertIsNone(addon.frame)

    def test_auto_segment_flips_the_button(self):
        lua, addon = start(extra=ALWAYS)
        lua.execute(FAKE_FRAME)
        addon.UpdateFightButton(addon)
        self.assertEqual(button(addon), ("Start segment", GREEN, GREEN))
        addon.StartFight(addon, "Boss")                                          # regen/encounter path
        self.assertEqual(button(addon), ("End segment", RED, RED))
        self.assertIsNone(addon.manualFight)
        addon.EndFight(addon)
        self.assertEqual(button(addon), ("Start segment", GREEN, GREEN))

    def test_toggle_starts_and_ends_a_manual_segment(self):
        lua, addon = start()                                                     # open world, alwaysEnabled off
        lua.execute(FAKE_FRAME)
        addon.ToggleFight(addon)
        self.assertTrue(addon.inCombat)
        self.assertTrue(addon.manualFight)
        self.assertEqual(seg(addon).id, "Manual")
        self.assertEqual(button(addon), ("End segment", RED, RED))
        lua.execute(HEAL)                                                        # unhealed segments are not stored
        lua.execute("STUB.time = 50")
        addon.ToggleFight(addon)
        self.assertFalse(addon.inCombat)
        self.assertIsNone(addon.manualFight)
        self.assertEqual(button(addon), ("Start segment", GREEN, GREEN))
        self.assertEqual(addon.History.Size(addon.History), 1)

    def test_manual_segment_passes_the_instance_gate_only_while_live(self):
        lua, addon = start()
        self.assertFalse(addon.Enabled(addon))
        addon.ToggleFight(addon)
        self.assertTrue(addon.Enabled(addon))
        addon.ToggleFight(addon)
        self.assertFalse(addon.Enabled(addon))

    def test_visibility_follows_the_options_and_the_manual_segment(self):
        lua, addon = start()                                                     # open world, alwaysEnabled off
        lua.execute(FAKE_FRAME + '; HSW_TEST_ADDON.frame.Show = function() SHOWN = true end; HSW_TEST_ADDON.frame.Hide = function() SHOWN = false end')
        g = addon.hsw.db["global"]
        shown = lambda: lua.globals().SHOWN
        addon.AdjustVisibility(addon)
        self.assertFalse(shown())                                                # not enabled here
        g.alwaysShow = True
        addon.AdjustVisibility(addon)
        self.assertTrue(shown())
        g.neverShow = True
        addon.AdjustVisibility(addon)
        self.assertFalse(shown())                                                # never wins over always
        g.neverShow = False; g.alwaysShow = False
        addon.ToggleFight(addon)
        self.assertTrue(shown())                                                 # a manual segment shows the panel
        addon.ToggleFight(addon)
        self.assertFalse(shown())                                                # and hides it again when it ends

    def test_unsupported_spec_refuses_with_a_message(self):
        lua, addon = start()
        lua.execute("""
            MSGS = {}
            function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end
            function HSW_TEST_ADDON.StatParser:IsCurrentSpecSupported() return false end
        """)
        addon.ToggleFight(addon)
        self.assertFalse(addon.inCombat)
        self.assertIsNone(addon.manualFight)
        self.assertEqual(list(lua.globals().MSGS.values()), ["Current spec is not supported."])


SESSION = """STUB.sessions = { { sessionID = 7, name = "Mob", durationSeconds = 9, heals = { ["Player-1"] = { [25292] = 1000 } } } }"""


class Finaliser(unittest.TestCase):
    """EndFight parks the segment; the ticker prices it once the session totals are readable."""

    def tickers(self, lua):
        return len(list(lua.globals().STUB.tickers.keys()))

    def test_segment_is_priced_from_the_sessions_opened_during_the_fight(self):
        lua, addon = start(extra=ALWAYS + '; STUB.sessions = { { sessionID = 3, name = "Earlier", heals = { ["Player-1"] = { [25292] = 5000 } } } }')
        addon.SessionTotals.Advance()                                            # out of combat: the earlier session is nobody's
        addon.StartFight(addon, "Boss", True)
        self.assertEqual(seg(addon).sessionFrom, 3)
        lua.execute('local a = HSW_TEST_ADDON; a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false)')
        lua.execute('STUB.sessions[2] = { sessionID = 4, name = "Mob", heals = { ["Player-1"] = { [25292] = 1000 } } }; STUB.time = 30')
        cur = seg(addon)
        addon.EndFight(addon)
        self.assertEqual(cur.sessionTo, 4)
        self.assertEqual(cur.totalHealing, 1000)                                 # session 3 was before the fight
        self.assertGreater(cur.t.heal, 0)
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertEqual(self.tickers(lua), 0)
        self.assertIsNone(cur.pendingSince)

    def test_secret_totals_keep_the_segment_pending_until_released(self):
        lua, addon = start(extra=ALWAYS + "; STUB.secret = true")                  # in combat: ids and amounts secret
        addon.StartFight(addon, "Boss", True)
        self.assertEqual(seg(addon).sessionFrom, 0)                                 # watermark: nothing seen yet
        lua.execute(SESSION + "; STUB.time = 10")                                   # session 7 opened during the fight
        cur = seg(addon)
        addon.EndFight(addon)
        self.assertFalse(addon.inCombat)
        self.assertIsNone(cur.sessionTo)                                            # list unreadable at the boundary
        self.assertEqual(addon.History.Size(addon.History), 0)
        self.assertEqual(self.tickers(lua), 1)
        self.assertIsNotNone(cur.pendingSince)
        lua.execute("STUB.tick()")                                                  # still secret
        self.assertEqual(addon.History.Size(addon.History), 0)
        lua.execute("STUB.secret = false; STUB.restriction = 1; STUB.tick()")       # readable but the client still restricts addons
        self.assertEqual(addon.History.Size(addon.History), 0)
        lua.execute("STUB.restriction = 0; STUB.lockdown = true; STUB.tick()")
        self.assertEqual(addon.History.Size(addon.History), 0)
        lua.execute("STUB.lockdown = false; STUB.tick()")
        self.assertEqual(cur.sessionTo, 7)                                          # resolved once readable
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertEqual(cur.totalHealing, 1000)
        self.assertEqual(addon.SessionTotals.watermark, 7)
        self.assertEqual(self.tickers(lua), 0)

    def test_session_already_open_when_the_fight_starts_is_included(self):
        # Dungeon 2026-11-07: the meter had opened session 29 before PLAYER_REGEN_DISABLED, StartFight read it as
        # "before the fight" and the pull priced to nothing. The fight starts at the watermark, not at "newest".
        lua, addon = start(extra=ALWAYS + '; STUB.sessions = { { sessionID = 28, name = "Earlier", heals = { ["Player-1"] = { [25292] = 5000 } } } }')
        addon.SessionTotals.Advance()                                            # 28 seen out of combat
        lua.execute('STUB.sessions[2] = { sessionID = 29, name = "Pull", heals = { ["Player-1"] = { [25292] = 1000 } } }')   # opened as combat begins
        addon.StartFight(addon, "Boss", True)
        self.assertEqual(seg(addon).sessionFrom, 28)
        cur = seg(addon)
        lua.execute("STUB.time = 20")
        addon.EndFight(addon)
        self.assertEqual((cur.sessionTo, cur.totalHealing), (29, 1000))

    def test_fight_after_a_meter_reset_is_priced(self):
        # Deadmines 2026-11-10: sessionFrom = 10 (open-world watermark), sessionTo = 7 (the meter had
        # restarted its ids), so four fights priced nothing. A segment that ends below its start reads
        # from 0, and the watermark restarts with it.
        lua, addon = start(extra=ALWAYS + '; STUB.sessions = { { sessionID = 10, name = "Boar", heals = { ["Player-1"] = { [25292] = 5000 } } } }')
        addon.SessionTotals.Advance()
        lua.execute("STUB.sessions = {}")                                         # the meter resets
        addon.StartFight(addon, "First", True)
        first = seg(addon)
        self.assertEqual(first.sessionFrom, 10)                                   # stale watermark
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 1000 } } }; STUB.time = 10')
        addon.EndFight(addon)
        self.assertEqual((first.sessionTo, first.totalHealing), (1, 1000))
        self.assertEqual(addon.SessionTotals.watermark, 1)
        addon.StartFight(addon, "Second", True)
        second = seg(addon)
        lua.execute('STUB.sessions[2] = { sessionID = 2, name = "B", heals = { ["Player-1"] = { [25292] = 200 } } }; STUB.time = 20')
        addon.EndFight(addon)
        self.assertEqual(second.totalHealing, 200)

    def test_two_fights_pending_across_a_meter_reset_read_its_sessions_once(self):
        # Both fights began on the pre-reset watermark and are priced in one pass. The first reads from
        # 0; the second starts where the first ended, not at 0 again, or the Total counts twice.
        lua, addon = start(extra=ALWAYS + '; STUB.sessions = { { sessionID = 10, name = "Boar", heals = { ["Player-1"] = { [25292] = 5000 } } } }')
        addon.SessionTotals.Advance()
        lua.execute("STUB.sessions = {}; STUB.secret = true")                     # the meter resets; ids secret in combat
        addon.StartFight(addon, "First", True)
        first = seg(addon)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 1000 } } }; STUB.time = 10')
        addon.EndFight(addon)
        addon.StartFight(addon, "Second", True)
        second = seg(addon)
        self.assertEqual(second.sessionFrom, 10)                                  # stale watermark
        lua.execute('STUB.sessions[2] = { sessionID = 2, name = "B", heals = { ["Player-1"] = { [25292] = 200 } } }; STUB.time = 20')
        addon.EndFight(addon)
        lua.execute("STUB.secret = false; STUB.tick()")                           # both priced in one pass
        self.assertEqual((first.sessionFrom, first.sessionTo), (0, 2))
        self.assertEqual((second.sessionFrom, second.sessionTo), (2, 2))
        self.assertEqual((first.totalHealing, second.totalHealing), (1200, 0))    # chained within the release delay: all in the first
        self.assertEqual(seg(addon, "Total").totalHealing, 1200)
        self.assertEqual(addon.SessionTotals.watermark, 2)

    def test_stale_pending_segment_is_dropped(self):
        lua, addon = start(extra=ALWAYS + "; " + SESSION + "; STUB.secret = true")
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        addon.StartFight(addon, "Boss", True)
        lua.execute("STUB.time = 10")
        addon.EndFight(addon)
        lua.execute("STUB.time = 71; STUB.tick()")
        self.assertEqual(addon.History.Size(addon.History), 0)
        self.assertEqual(self.tickers(lua), 0)
        self.assertTrue(any("dropped" in m for m in lua.globals().MSGS.values()))

    def test_hits_counted_but_no_meter_healing_is_reported(self):
        # Westfall 2026-11-08: a fight the meter opened no session for finalised to nothing with no word
        # about it. Discover mode now says the meter had no healing when the matcher counted hits.
        lua, addon = start(extra=ALWAYS)
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        addon.StartFight(addon, "Boss", True)
        lua.execute('local s = HSW_TEST_ADDON.SegmentManager:Get(0); s:CountHeal(25292, "SPELL_HEAL", "Hop", false); s:CountHeal(25292, "SPELL_HEAL", "Hop", true); STUB.time = 10')
        addon.EndFight(addon)
        msgs = list(lua.globals().MSGS.values())
        self.assertTrue(any("meter recorded no healing (2 hits counted)" in m for m in msgs), msgs)
        self.assertEqual(addon.History.Size(addon.History), 0)
        lua.execute("MSGS = {}")
        addon.StartFight(addon, "Priced", True)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 100 } } }; HSW_TEST_ADDON.SegmentManager:Get(0):CountHeal(25292, "SPELL_HEAL", "Hop", false); STUB.time = 20')
        addon.EndFight(addon)
        msgs = list(lua.globals().MSGS.values())
        self.assertFalse(any("no healing" in m for m in msgs), msgs)
        self.assertTrue(any("segment Priced finalised." in m for m in msgs), msgs)

    def saved(self, addon):
        return list(addon.hsw.db["global"].discoverLog.values())

    def test_discover_mode_saves_what_the_finaliser_read(self):
        # A14: the session range and the meter's list were chat and /hsw debug only; a run is now read from the saved variables
        lua, addon = start(extra=ALWAYS + '; STUB.sessions = { { sessionID = 3, name = "Earlier", durationSeconds = 5 } }')
        addon.SessionTotals.Advance()
        addon.discoverSpells = True
        addon.StartFight(addon, "Boss", True)
        lua.execute('HSW_TEST_ADDON.SegmentManager:Get(0):CountHeal(25292, "SPELL_HEAL", "Hop", false)'
                    '; STUB.sessions[2] = { sessionID = 4, name = "Mob", durationSeconds = 9, heals = { ["Player-1"] = { [25292] = 1000 } } }; STUB.time = 30')
        addon.EndFight(addon)
        saved = self.saved(addon)
        self.assertTrue(any(s.endswith(" segment Boss finalised.") for s in saved), saved)
        self.assertTrue(saved[-1].endswith(" segment Boss: sessions 3 to 4, healing 1000, 1 hits; meter: 3 Earlier 5s, 4 Mob 9s."), saved)

    def test_discover_mode_saves_the_range_of_a_fight_that_priced_nothing(self):
        lua, addon = start(extra=ALWAYS)
        addon.discoverSpells = True
        addon.StartFight(addon, "Boss", True)
        lua.execute('local s = HSW_TEST_ADDON.SegmentManager:Get(0); s:CountHeal(25292, "SPELL_HEAL", "Hop", false); s:CountHeal(25292, "SPELL_HEAL", "Hop", true); STUB.time = 10')
        addon.EndFight(addon)
        self.assertEqual(addon.History.Size(addon.History), 0)                   # no history entry: the log is the only record
        self.assertTrue(self.saved(addon)[-1].endswith(" segment Boss: sessions 0 to 0, healing 0, 2 hits; meter: none."), self.saved(addon))

    def test_discover_mode_saves_the_range_of_a_dropped_segment(self):
        lua, addon = start(extra=ALWAYS + "; " + SESSION + "; STUB.secret = true")
        addon.discoverSpells = True
        addon.StartFight(addon, "Boss", True)
        lua.execute("STUB.time = 10")
        addon.EndFight(addon)
        lua.execute("STUB.time = 71; STUB.tick()")
        self.assertTrue(self.saved(addon)[-1].endswith(" segment Boss: sessions 0 to ?, healing 0, 0 hits; meter: ? Mob ?s."), self.saved(addon))

    def test_unnamed_fight_takes_the_meter_sessions_name_when_priced(self):
        # Dungeon trash: the hostile's name is secret at PLAYER_REGEN_DISABLED, so the fight starts "Trash".
        # The meter names its session after the mob, readable once the totals are.
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, None)
        first = seg(addon)
        self.assertEqual(first.id, "Trash")
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "Defias Pillager", durationSeconds = 4, heals = { ["Player-1"] = { [25292] = 50 } } }'
                    '; STUB.sessions[2] = { sessionID = 2, name = "Defias Trapper", durationSeconds = 9, heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 10')
        addon.EndFight(addon)
        self.assertEqual(first.id, "Defias Trapper")                             # the longest session names the pull
        self.assertEqual(addon.History.Get(addon.History, 0).Segment, "Defias Trapper")
        addon.StartFight(addon, None)
        second = seg(addon)
        lua.execute('STUB.sessions[3] = { sessionID = 3, name = "Defias Trapper", durationSeconds = 5, heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 20')
        addon.EndFight(addon)
        self.assertEqual(second.id, "Defias Trapper(2)")                          # numbered like a named repeat
        addon.StartFight(addon, "Boss", True)
        third = seg(addon)
        lua.execute('STUB.sessions[4] = { sessionID = 4, name = "Trash", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 30')
        addon.EndFight(addon)
        self.assertEqual(third.id, "Boss")                                       # a named fight keeps its name
        addon.StartFight(addon, None)
        fourth = seg(addon)
        lua.execute("STUB.time = 40")
        addon.EndFight(addon)
        self.assertEqual(fourth.id, "Trash")                                     # no session: nothing to name it after

    def test_consecutive_fights_with_readable_boundaries_get_their_own_sessions(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "First", True)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 10')
        first = seg(addon)
        addon.EndFight(addon)
        addon.StartFight(addon, "Second", True)
        self.assertEqual(seg(addon).sessionFrom, 1)
        lua.execute('STUB.sessions[2] = { sessionID = 2, name = "B", heals = { ["Player-1"] = { [25292] = 200 } } }; STUB.time = 20')
        second = seg(addon)
        addon.EndFight(addon)
        self.assertEqual((first.totalHealing, second.totalHealing), (100, 200))
        self.assertEqual(addon.History.Size(addon.History), 2)

    def test_a_pull_chained_into_the_meters_open_session_is_priced_from_what_it_added(self):
        # Blackfathom Deeps 2026-11-13: a pull 5 s after the last one opened no new session. Session 10
        # read 28 s at the first fight's end and 40 s at the second's, and the second fight ended
        # `Trash: sessions 10 to 10, healing 0, 1 hits`.
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, None)
        first = seg(addon)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "Blackfathom Myrmidon", durationSeconds = 28, heals = { ["Player-1"] = { [25292] = 336 } } }; STUB.time = 26')
        addon.EndFight(addon)
        self.assertEqual((first.id, first.totalHealing), ("Blackfathom Myrmidon", 336))
        addon.StartFight(addon, None)
        second = seg(addon)
        lua.execute('STUB.sessions[1].durationSeconds = 40; STUB.sessions[1].heals["Player-1"][25292] = 500; STUB.time = 38')   # no new session: the open one grew
        addon.EndFight(addon)
        self.assertEqual((second.sessionFrom, second.sessionTo), (1, 1))
        self.assertEqual(second.totalHealing, 164)
        self.assertEqual(second.id, "Blackfathom Myrmidon(2)")                    # named after the session it sat in
        self.assertEqual(seg(addon, "Total").totalHealing, 500)
        self.assertEqual(addon.History.Size(addon.History), 2)
        addon.StartFight(addon, None)
        third = seg(addon)
        lua.execute("STUB.time = 50")
        addon.EndFight(addon)
        self.assertEqual((third.id, third.totalHealing), ("Trash", 0))            # nothing added: not that session's fight

    def test_a_fight_started_while_one_is_pending_begins_after_it(self):
        # Both boundaries secret: the second fight starts on the stale watermark, so the finaliser moves
        # its start to the first fight's resolved end. Sessions opened before the first fight is priced
        # land in the first fight; that is the accepted limit of a pull chained within the release delay.
        lua, addon = start(extra=ALWAYS + "; STUB.secret = true")
        addon.StartFight(addon, "First", True)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 10')
        first = seg(addon)
        addon.EndFight(addon)
        addon.StartFight(addon, "Second", True)
        second = seg(addon)
        self.assertEqual(second.sessionFrom, 0)                                   # stale watermark
        lua.execute("STUB.secret = false; STUB.tick()")                           # first is priced: sessions up to 1
        self.assertEqual((first.sessionTo, first.totalHealing), (1, 100))
        self.assertEqual(second.sessionFrom, 1)                                   # moved past the first fight
        lua.execute('STUB.sessions[2] = { sessionID = 2, name = "B", heals = { ["Player-1"] = { [25292] = 200 } } }; STUB.time = 20')
        addon.EndFight(addon)
        self.assertEqual(second.totalHealing, 200)

    def test_total_counts_priced_fights_with_healing(self):
        lua, addon = start(extra=ALWAYS)
        ttl = seg(addon, "Total")
        self.assertEqual(ttl.fights, 0)
        addon.StartFight(addon, "A", True)
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "A", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 10')
        addon.EndFight(addon)
        self.assertEqual(ttl.fights, 1)
        addon.StartFight(addon, "B", True)                                       # no healing: not a fight that counts
        lua.execute("STUB.time = 20")
        addon.EndFight(addon)
        self.assertEqual(ttl.fights, 1)

    def test_total_int_weight_of_equal_fights_matches_one_fight(self):
        lua, addon = start(extra=ALWAYS + "; STUB.regen = { base = 0, cast = 0 }")
        fights = []
        for i in (1, 2):
            addon.StartFight(addon, "F%d" % i, True)
            # 600 of the stub's 3000 mana: a 0.2 share per fight
            lua.execute('HSW_TEST_ADDON.SegmentManager:ForEachLive(function(s) s:IncFillerCasts(50) end); HSW_TEST_ADDON.ManaDeficit:Spend(600)')
            lua.execute('STUB.sessions[%d] = { sessionID = %d, name = "F", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = %d' % (i, i, 10 * i))
            fights.append(seg(addon))
            addon.EndFight(addon)
        self.assertGreater(fights[0].GetIntManaValue(fights[0]), 0)
        one = addon.GetStatsForSegment(addon, fights[0])[3]
        self.assertAlmostEqual(addon.GetStatsForSegment(addon, seg(addon, "Total"))[3], one)

    def test_fight_end_fixes_the_pool_share_and_adds_it_to_the_totals(self):
        lua, addon = start(extra=ALWAYS + '; STUB.instance.type = "party"; STUB.maxMana = 1000; STUB.regen = { base = 0, cast = 0 }')
        spend = 'HSW_TEST_ADDON.ManaDeficit:Spend(%d)'
        addon.StartFight(addon, "Boss", True)
        lua.execute(spend % 400 + "; STUB.time = 10")
        boss = seg(addon)
        self.assertEqual(boss.poolShare, 0)                                       # live: not known yet
        addon.EndFight(addon)
        self.assertAlmostEqual(boss.poolShare, 0.4)
        self.assertEqual((boss.deficitStart, boss.deficitEnd), (0, 400))
        addon.StartFight(addon, None)                                             # dungeon trash
        lua.execute(spend % 250 + "; STUB.time = 20")
        trash = seg(addon)
        addon.EndFight(addon)
        self.assertAlmostEqual(trash.poolShare, 0.25)
        self.assertAlmostEqual(seg(addon, "Total").poolShare, 0.65)               # the sum, not an estimate over 650 mana
        self.assertAlmostEqual(seg(addon, "Bosses").poolShare, 0.4)
        self.assertAlmostEqual(seg(addon, "Trash").poolShare, 0.25)

    def test_open_world_fight_adds_its_pool_share_to_the_total_only(self):
        lua, addon = start(extra=ALWAYS + "; STUB.maxMana = 1000; STUB.regen = { base = 0, cast = 0 }")
        addon.StartFight(addon, None)
        lua.execute('HSW_TEST_ADDON.ManaDeficit:Spend(300); STUB.time = 10')
        addon.EndFight(addon)
        self.assertAlmostEqual(seg(addon, "Total").poolShare, 0.3)
        self.assertEqual((seg(addon, "Bosses").poolShare, seg(addon, "Trash").poolShare), (0, 0))

    def test_a_fight_pulled_below_full_counts_only_what_it_emptied(self):
        lua, addon = start(extra=ALWAYS + "; STUB.maxMana = 1000; STUB.regen = { base = 0, cast = 0 }")
        lua.execute("HSW_TEST_ADDON.ManaDeficit:Spend(300)")                      # a heal between pulls
        addon.StartFight(addon, "Boss", True)
        lua.execute("HSW_TEST_ADDON.ManaDeficit:Spend(200); STUB.time = 10")
        boss = seg(addon)
        addon.EndFight(addon)
        self.assertEqual((boss.deficitStart, boss.deficitEnd), (300, 500))
        self.assertAlmostEqual(boss.poolShare, 0.2)

    def test_fight_end_reads_the_buffs_and_credits_water_shield_globes_spent_in_the_fight(self):
        lua, addon = start(extra=ALWAYS + "; STUB.maxMana = 1000; STUB.regen = { base = 0, cast = 0 }; STUB.auras = { { id = 408510, count = 3 } }")
        addon.ScanPlayerBuffs(addon)                                              # three globes up before the pull
        addon.StartFight(addon, "Boss", True)
        lua.execute("HSW_TEST_ADDON.foughtSinceBuffs = true")                     # PLAYER_REGEN_DISABLED (Events.lua): globes can go unseen
        lua.execute("HSW_TEST_ADDON.ManaDeficit:Spend(400); STUB.auras = { { id = 408510, count = 1 } }; STUB.time = 10")
        boss = seg(addon)
        addon.EndFight(addon)
        self.assertEqual(boss.manaRestore, 40)                                    # two globes of 2% went to hits in the fight
        self.assertEqual(boss.deficitEnd, 360)
        self.assertAlmostEqual(boss.poolShare, 0.36)

    def test_a_fight_that_regenerates_more_than_it_spends_has_no_share(self):
        lua, addon = start(extra=ALWAYS + "; STUB.maxMana = 1000; STUB.regen = { base = 10, cast = 10 }")
        lua.execute("HSW_TEST_ADDON.ManaDeficit:Spend(500)")
        addon.StartFight(addon, "Boss", True)
        lua.execute("STUB.time = 20")
        boss = seg(addon)
        addon.EndFight(addon)
        self.assertEqual((boss.deficitStart, boss.deficitEnd), (500, 300))
        self.assertEqual(boss.poolShare, 0)

    def test_testing_flag_outlives_a_pending_test_segment(self):
        lua, addon = start(extra=SESSION + "; STUB.secret = true")
        addon.hsw.ChatCommand(addon.hsw, "start")
        lua.execute("STUB.time = 5")
        addon.hsw.ChatCommand(addon.hsw, "end")
        self.assertFalse(addon.inCombat)
        self.assertTrue(lua.globals().HSW_ENABLE_FOR_TESTING)                   # still pending: allocate lines must print
        lua.execute("STUB.secret = false; STUB.tick()")
        self.assertIsNone(lua.globals().HSW_ENABLE_FOR_TESTING)


class ClearSegments(unittest.TestCase):
    """The Clear button archives the Total to history before the reset."""

    def fight(self, lua, addon, name, session, healing, end_time):
        addon.StartFight(addon, name, True)
        lua.execute(f'STUB.sessions[#STUB.sessions + 1] = {{ sessionID = {session}, name = "{name}", heals = {{ ["Player-1"] = {{ [25292] = {healing} }} }} }}; STUB.time = {end_time}')
        addon.EndFight(addon)

    def test_total_is_archived_then_reset(self):
        lua, addon = start(extra=ALWAYS)
        self.fight(lua, addon, "A", 1, 100, 10)
        self.fight(lua, addon, "B", 2, 300, 40)                                  # 10 + 30 seconds of fights
        ttl = seg(addon, "Total")
        heal_per_pct = ttl.totalHealing / 100 / ttl.t.heal
        addon.ClearAllSegments(addon)
        self.assertEqual(addon.History.Size(addon.History), 4)                  # Total, Boss Total, B, A
        h = addon.History.Get(addon.History, 0)
        self.assertEqual((h.Segment, h.tab, h.Duration, h.Heal), ("Total (2 fights)", "", "0:40", 1))
        self.assertAlmostEqual(h.HealPct, heal_per_pct)
        self.assertTrue(h.IsTotal)
        self.assertIn("each fight's casts and heals are in that fight's entry", addon.EventsCSV(addon, h))
        self.assertEqual(addon.History.Get(addon.History, 1).Segment, "Boss Total (2 fights)")
        b = addon.History.Get(addon.History, 2)
        self.assertEqual((b.Segment, b.IsTotal), ("B", None))
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 0)
        new_total = seg(addon, "Total")
        self.assertEqual((new_total.fights, new_total.t.heal), (0, 0))
        self.assertEqual(addon.currentSegment, 0)

    def test_one_fight_is_singular(self):
        lua, addon = start(extra=ALWAYS)
        self.fight(lua, addon, "A", 1, 100, 10)
        addon.ClearAllSegments(addon)
        self.assertEqual(addon.History.Get(addon.History, 0).Segment, "Total (1 fight)")

    def test_raid_trash_is_skipped_but_the_total_is_kept(self):
        lua, addon = start(extra='STUB.instance = { name = "MC", type = "raid", difficultyId = 14 }')
        addon.StartFight(addon, "Trash")                                          # not a boss: raid trash
        lua.execute('STUB.sessions[1] = { sessionID = 1, name = "Trash", heals = { ["Player-1"] = { [25292] = 100 } } }; STUB.time = 10')
        addon.EndFight(addon)
        self.assertEqual(addon.History.Size(addon.History), 0)
        addon.ClearAllSegments(addon)
        self.assertEqual(addon.History.Size(addon.History), 2)
        self.assertEqual(addon.History.Get(addon.History, 0).Segment, "Total (1 fight)")
        self.assertEqual(addon.History.Get(addon.History, 1).Segment, "Trash Total (1 fight)")

    def test_empty_total_adds_nothing_and_still_resets(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "A", True)
        lua.execute("STUB.time = 10")
        addon.EndFight(addon)                                                     # nothing healed
        addon.ClearAllSegments(addon)
        self.assertEqual(addon.History.Size(addon.History), 0)
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 0)

    def test_in_combat_nothing_happens(self):
        lua, addon = start(extra=ALWAYS)
        self.fight(lua, addon, "A", 1, 100, 10)
        addon.StartFight(addon, "B", True)
        addon.ClearAllSegments(addon)
        self.assertEqual(addon.History.Size(addon.History), 1)                     # fight A only
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 2)
        self.assertTrue(addon.inCombat)

    def test_dialog_text_says_totals_are_saved(self):
        lua, addon = start()
        self.assertIn("Totals are saved to history first", lua.globals().StaticPopupDialogs["HSW_CLEARALLSEGMENTS"].text)

    def test_class_totals_are_archived_with_the_total(self):
        lua, addon = start(extra='STUB.instance = { name = "Deadmines", type = "party", difficultyId = 1 }')
        self.fight(lua, addon, "VanCleef", 1, 1000, 10)                          # boss (fight() sets the boss flag)
        addon.StartFight(addon, None)                                             # trash
        lua.execute('STUB.sessions[#STUB.sessions + 1] = { sessionID = 2, name = "Defias Pillager", heals = { ["Player-1"] = { [25292] = 300 } } }; STUB.time = 20')
        addon.EndFight(addon)
        addon.StartFight(addon, None)                                             # trash
        lua.execute('STUB.sessions[#STUB.sessions + 1] = { sessionID = 3, name = "Defias Trapper", heals = { ["Player-1"] = { [25292] = 200 } } }; STUB.time = 30')
        addon.EndFight(addon)
        addon.ClearAllSegments(addon)
        names = [addon.History.Get(addon.History, i).Segment for i in range(addon.History.Size(addon.History))]
        self.assertEqual(names[:3], ["Total (3 fights)", "Boss Total (1 fight)", "Trash Total (2 fights)"])
        self.assertEqual(len(names), 6)
        for i in range(3):
            h = addon.History.Get(addon.History, i)
            self.assertTrue(h.IsTotal)
            self.assertEqual(h.tab, "")
        self.assertEqual(addon.History.Get(addon.History, 2).Duration, "0:20")   # the two trash fights
        for which in ("Total", "Bosses", "Trash"):
            self.assertEqual((seg(addon, which).fights, seg(addon, which).t.heal), (0, 0))

    def test_empty_class_total_is_not_archived(self):
        lua, addon = start(extra=ALWAYS)
        self.fight(lua, addon, "A", 1, 100, 10)                                   # open world: Total and (boss flag) Boss Total
        addon.ClearAllSegments(addon)
        names = [addon.History.Get(addon.History, i).Segment for i in range(addon.History.Size(addon.History))]
        self.assertEqual(names, ["Total (1 fight)", "Boss Total (1 fight)", "A"])


class Encounters(unittest.TestCase):
    """Events.lua on top of the real StartFight/EndFight: a boss pulled during trash gets its own segment."""

    def test_boss_pulled_mid_trash_is_logged_under_its_own_name(self):
        lua, addon = load(FILES + ["Events.lua"], setup=PALADIN + '\nSTUB.instance = { name = "MC", type = "raid", difficultyId = 14 }'
                          '; function UnitExists() return true end; function UnitCanAttack() return true end; STUB.names.target = "Core Hound"')
        lua.execute("local a = HSW_TEST_ADDON; a.hsw:OnInitialize(); a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()")
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)                               # trash: named after the hostile target
        lua.execute(HEAL)
        self.assertEqual((seg(addon).id, seg(addon).bossFight), ("Core Hound", False))
        addon.hsw.ENCOUNTER_START(addon.hsw, "ENCOUNTER_START", 663, "Lucifron")
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 2)
        self.assertEqual((seg(addon).id, seg(addon).bossFight), ("Lucifron", True))
        self.assertEqual(seg(addon, 1).id, "Core Hound")
        self.assertEqual(addon.History.Size(addon.History), 0)                   # raid trash is not logged
        lua.execute(HEAL + "; STUB.time = 60")
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)                                # mid-boss flicker: ignored
        self.assertTrue(addon.inCombat)
        addon.hsw.ENCOUNTER_END(addon.hsw)
        self.assertFalse(addon.inCombat)
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertEqual(addon.History.Get(addon.History, 0).Segment, "Lucifron")
