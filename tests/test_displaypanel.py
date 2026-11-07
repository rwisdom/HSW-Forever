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
        self.assertTrue(s.startswith('( Pawn: v1: "PALADIN-HSW-Boss": Class=PALADIN, Spec=1, HealingPower=1.00, SpellCritRating='), s)
        self.assertTrue(s.endswith(")") and "Mp5=" in s and "Versatility" not in s, s)
        lua.execute("STUB.time = 50")
        addon.EndFight(addon)
        h = addon.GetPawnStringFromHistory(addon, 0)
        self.assertTrue(h.startswith('( Pawn: v1: "Boss": Class=PALADIN, Spec=1, HealingPower=1.00'), h)

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
        self.assertTrue(shown[2].startswith('( Pawn: v1: "PALADIN-HSW-Boss"'), shown[2])

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
        self.assertEqual(addon.sessionWatermark, 7)
        self.assertEqual(self.tickers(lua), 0)

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

    def test_testing_flag_outlives_a_pending_test_segment(self):
        lua, addon = start(extra=SESSION + "; STUB.secret = true")
        addon.hsw.ChatCommand(addon.hsw, "start")
        lua.execute("STUB.time = 5")
        addon.hsw.ChatCommand(addon.hsw, "end")
        self.assertFalse(addon.inCombat)
        self.assertTrue(lua.globals().HSW_ENABLE_FOR_TESTING)                   # still pending: allocate lines must print
        lua.execute("STUB.secret = false; STUB.tick()")
        self.assertIsNone(lua.globals().HSW_ENABLE_FOR_TESTING)


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
