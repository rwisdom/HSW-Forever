import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Parsers/HolyPaladin.lua", "DisplayPanel.lua", "Core.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'
ALWAYS = "HSW_TEST_SAVED = { alwaysEnabled = true }"
HEAL = 'local a = HSW_TEST_ADDON; a.SegmentManager:Get(0):IncFillerCasts(660); a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false, 1000, 0)'


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
        addon.StartFight(addon, "Boss")
        self.assertTrue(addon.inCombat)
        cur, ttl = seg(addon), seg(addon, "Total")
        self.assertEqual((cur.id, cur.bossFight), ("Boss", True))
        self.assertEqual((ttl.startTime, ttl.fsrLastAccum), (cur.startTime, cur.startTime))
        lua.execute(HEAL + "; STUB.time = 100")
        addon.EndFight(addon)
        self.assertFalse(addon.inCombat)
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertAlmostEqual(cur.totalDuration, 100)
        self.assertAlmostEqual(ttl.totalDuration, 100)
        self.assertAlmostEqual(ttl.timeOutsideFSR, 100)
        addon.StartFight(addon, "Trash")
        addon.StartFight(addon, "Again")                                        # already in combat: ignored
        self.assertEqual(addon.SegmentManager.Size(addon.SegmentManager), 2)
        self.assertEqual(seg(addon).id, "Trash")


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
