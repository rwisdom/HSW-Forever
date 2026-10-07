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
        self.assertIsNone(addon.InMythicPlus)

    def test_unsupported_spec_never_enabled(self):
        lua, addon = start(extra='STUB.class = "WARRIOR"; STUB.talents = {}; ' + ALWAYS)
        self.assertFalse(addon.Enabled(addon))


class Fights(unittest.TestCase):
    def test_start_and_end_fight(self):
        lua, addon = start(extra=ALWAYS)
        addon.StartFight(addon, "Boss")
        self.assertTrue(addon.inCombat)
        cur, ttl = seg(addon), seg(addon, "Total")
        self.assertEqual((cur.id, cur.instance.bossFight), ("Boss", True))
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
        self.assertIsNone(addon.GetQELiveStringRaw)
        self.assertIsNone(addon.QELiveDialogName)

    def test_chat_start_end_and_segment_menu(self):
        lua, addon = start()
        addon.hsw.ChatCommand(addon.hsw, "start")
        self.assertTrue(lua.globals().HSW_ENABLE_FOR_TESTING)
        self.assertTrue(addon.inCombat)
        self.assertEqual(seg(addon).id, "test")
        addon.SegmentMenu(addon)                                                 # EasyMenu stub: must not error
        addon.hsw.ChatCommand(addon.hsw, "end")
        self.assertFalse(addon.inCombat)
