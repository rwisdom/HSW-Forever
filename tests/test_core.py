import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Parsers/HolyPaladin.lua", "DisplayPanel.lua", "Core.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5}, {name="Holy Power", rank=0, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'


def start(extra=""):
    lua, addon = load(FILES, setup=PALADIN + "\n" + extra)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.hsw:OnInitialize()
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.UnitManager.units["Player-1"] = "player"
    """)
    return lua, addon


def fought_segment(lua, addon, seconds=100):
    """A finished boss segment: one Holy Light R9 heal of 1000 after 660 mana of filler casts, `seconds` long."""
    lua.execute(f"""
        local a = HSW_TEST_ADDON
        a.SegmentManager:Enqueue("Boss", true)
        local s = a.SegmentManager:Get(0)
        s:IncFillerCasts(660)
        a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false)
        STUB.time = {seconds}
        a.StatParser:ApplyTotals(s, {{ [25292] = 1000 }})
        s:End()
    """)
    return addon.SegmentManager.Get(addon.SegmentManager, 0)


class Database(unittest.TestCase):
    def test_defaults(self):
        _, addon = start()
        g = addon.hsw.db["global"]
        self.assertEqual((g.schema, g.enabledInDungeons, g.enabledInRaids, g.enabledInBattlegrounds), (2, True, True, False))
        self.assertEqual((g.hasteRatingPerPct, g.intPerCritOverride.PALADIN, g.maxSegments, g.neverShow, g.logEvents), (1, 0, 10, False, False))
        self.assertEqual(addon.hsw.optionsFrame.settingsCategoryID, "HSW_TEST_CATEGORY")   # Configure button → Settings.OpenToCategory(id)

    def test_old_history_is_wiped_once(self):
        _, addon = start(extra='HSW_TEST_SAVED = { history = { [1] = { Int = 1, Vrs = 0.5 } }, front = 1, back = 0 }')
        g = addon.hsw.db["global"]
        self.assertEqual((g.front, g.back, g.schema, len(list(g.history.keys()))), (0, 0, 2, 0))
        _, addon = start(extra='HSW_TEST_SAVED = { schema = 2, history = { [1] = { Heal = 1 } }, front = 1, back = 0 }')
        g = addon.hsw.db["global"]
        self.assertEqual((g.front, g.history[1].Heal), (1, 1))


class StatsForSegment(unittest.TestCase):
    def test_divides_by_healing_and_adds_live_terms(self):
        lua, addon = start()
        seg = fought_segment(lua, addon)           # HPM 1000/660, 100 s all outside the FSR, no Int talent (mult 1.0), Human Spirit mult 1.10
        seg.poolShare = 0.5                        # half the mana pool went into the fight
        heal, crt, hst, int_, spi, mp5 = addon.GetStatsForSegment(addon, seg)
        self.assertEqual(heal, 1)
        self.assertAlmostEqual(crt, seg.t.crit / seg.t.heal)
        self.assertEqual(hst, 0)                    # no chain casts
        self.assertAlmostEqual(int_, (seg.t.int + 15 * 1.0 * 1000 / 660 * 0.5) / seg.t.heal)
        self.assertAlmostEqual(spi, 0.125 * 1.10 * 100 * (1000 / 660) / seg.t.heal)   # default regen per Spirit
        self.assertAlmostEqual(mp5, 100 / 5 * (1000 / 660) / seg.t.heal)

    def test_empty_segment(self):
        _, addon = start()
        self.assertEqual(tuple(addon.GetStatsForSegment(addon, addon.Segment.Create("x"))), (1, 0, 0, 0, 0, 0))


class History(unittest.TestCase):
    def test_add_and_list(self):
        lua, addon = start()
        addon.AddHistoricalSegment(addon, addon.Segment.Create("empty"))   # nothing healed: skipped
        self.assertEqual(addon.History.Size(addon.History), 0)
        seg = fought_segment(lua, addon)
        addon.AddHistoricalSegment(addon, seg)
        self.assertEqual(addon.History.Size(addon.History), 1)
        h = addon.History.Get(addon.History, 0)
        self.assertEqual((h.Segment, h.Duration, h.Class, h.SpecID, h.ClassName, h.Heal), ("Boss", "1:40", "Holy Paladin", 65, "PALADIN", 1))
        stats = addon.GetStatsForSegment(addon, seg)
        self.assertAlmostEqual(h.Crt, stats[1])
        self.assertAlmostEqual(h.Mp5, stats[5])
        self.assertAlmostEqual(h.HealPct, 1000 / 100 / seg.t.heal)
        self.assertAlmostEqual(h.Mp5Pct, 1000 / 100 / seg.GetMP5(seg))
        self.assertEqual((h.Talents[1].name, h.Talents[1].rank), ("Illumination", 5))
        self.assertIsNone(h.Name)                                                 # no player/realm/region in the log
        names = addon.GetHistoricalSegmentsList(addon)
        self.assertIn("Boss 1:40", names[0])
        self.assertIn("Spell_Holy_HolyBolt", names[0])

    def test_raid_trash_skipped_bosses_kept(self):
        lua, addon = start(extra='STUB.instance = { name = "MC", type = "raid", difficultyId = 14 }')
        lua.execute("""
            local a = HSW_TEST_ADDON
            a.SegmentManager:Enqueue(); a.SegmentManager:SetCurrentId("Trash")
            a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false)
            a.StatParser:ApplyTotals(a.SegmentManager:Get(0), { [25292] = 1000 })
            a.SegmentManager:Get(0):End()
        """)
        addon.AddHistoricalSegment(addon, addon.SegmentManager.Get(addon.SegmentManager, 0))
        self.assertEqual(addon.History.Size(addon.History), 0)
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        self.assertEqual(addon.History.Size(addon.History), 1)

    def test_empty_history_shows_a_note_and_stores_nothing(self):
        lua, addon = start()
        self.assertEqual(len(list(addon.GetHistoricalSegmentsList(addon).keys())), 0)
        tab = lua.globals().HSW_TEST_OPTIONS.HealerStatWeights().args.historyTab.args
        self.assertEqual(tab.HistorySelection.args.empty.name, "No logged segments yet.")
        self.assertEqual(addon.History.Size(addon.History), 0)

    def test_history_tab_clear_button_wipes_the_log(self):
        lua, addon = start()
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        build = lua.globals().HSW_TEST_OPTIONS.HealerStatWeights          # the options builder AceConfig calls
        tab = build().args.historyTab.args
        self.assertIn("ctrl0", tab.HistorySelection.args.keys())
        self.assertEqual((tab.clearHistory.type, tab.clearHistory.confirm), ("execute", True))
        tab.clearHistory.func()
        self.assertEqual(addon.History.Size(addon.History), 0)
        tab = build().args.historyTab.args                                 # AceConfig refetches after an execute
        self.assertNotIn("ctrl0", tab.HistorySelection.args.keys())
        self.assertIn("empty", tab.HistorySelection.args.keys())

    def test_history_options_table_labels(self):
        lua, addon = start()
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        t = addon.BuildOptionsTableForHistorySegment(addon, 0)
        names = [v.name for _, v in t.items() if v.name]
        for label in ("+Healing", "Crit Rating", "Haste (HPCT)", "Intellect", "Spirit", "MP5", "Pawn >>", "icon_Illumination"):
            self.assertTrue(any(label in n for n in names), label)

    def test_history_entry_carries_the_trinket_snapshot(self):
        trinket = ('function GetInventoryItemLink(_, slot) return slot == 13 and "|Hitem:1|h[Lucky Charm]|h" or nil end'
                   '; function GetItemInfo(link) return "Lucky Charm", link, 3, 45, 40, "Armor", "Trinket", 1, "INVTYPE_TRINKET", "icon_charm" end')
        lua, addon = start(extra=trinket)
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        h = addon.History.Get(addon.History, 0)
        self.assertEqual((h.Slot13.name, h.Slot13.ilvl, h.Slot13.icon), ("Lucky Charm", 45, "icon_charm"))
        self.assertIsNone(h.Slot14)
        names = [v.name for _, v in addon.BuildOptionsTableForHistorySegment(addon, 0).items() if v.name]
        self.assertTrue(any("icon_charm" in n and "45" in n and "Lucky Charm" in n for n in names), names)

    def test_secret_item_data_in_combat_is_not_snapshotted(self):
        trinket = ('issecretvalue = function(v) return v == "SECRET" end'
                   '; function GetInventoryItemLink(_, slot) return slot == 13 and "|Hitem:1|h[Lucky Charm]|h" or nil end'
                   '; function GetItemInfo(link) return "SECRET", link, 3, 45, 40, "Armor", "Trinket", 1, "INVTYPE_TRINKET", "icon_charm" end')
        lua, addon = start(extra=trinket)
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        self.assertIsNone(addon.History.Get(addon.History, 0).Slot13)

    def test_history_entry_exports_its_casts_and_heals_as_csv(self):
        lua, addon = start(extra="HSW_TEST_SAVED = { logEvents = true }")   # off by default
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))       # one Holy Light heal, no cast events
        h = addon.History.Get(addon.History, 0)
        csv = addon.EventsCSV(addon, h)
        self.assertEqual(csv.split("\n"), ["time,event,spell_id,spell,target,amount,crit,mana",
                                           "0.00,heal,25292,Holy Light,Me,,0,",
                                           "100.00,total,25292,Holy Light,,1000,,"])
        t = addon.BuildOptionsTableForHistorySegment(addon, 0)
        boxes = [v for _, v in t.items() if v.type == "input" and v.multiline]
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].get(None), csv)
        self.assertEqual(addon.EventsCSV(addon, lua.table()), "No casts or heals were recorded for this segment.")   # pre-feature entry

    def test_event_logging_is_off_by_default_and_switchable(self):
        lua, addon = start()
        opts = lua.globals().HSW_TEST_OPTIONS.HealerStatWeights().args.optionsTab.args
        self.assertIn("memory intensive", opts.logEvents.desc.lower())
        self.assertFalse(opts.logEvents.get(None))
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        h = addon.History.Get(addon.History, 0)
        self.assertEqual(len(list(h.Events.values())), 0)                   # nothing recorded while off
        t = addon.BuildOptionsTableForHistorySegment(addon, 0)
        self.assertFalse(any(v.type == "input" and v.multiline for _, v in t.items()))   # section hidden
        opts.logEvents.set(None, True)
        t = addon.BuildOptionsTableForHistorySegment(addon, 0)
        self.assertTrue(any(v.type == "input" and v.multiline for _, v in t.items()))
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        self.assertEqual(len(list(addon.History.Get(addon.History, 0).Events.values())), 2)   # recording now: the heal and its total

    def test_calibration_inputs_are_validated(self):
        lua, addon = start()
        opts = lua.globals().HSW_TEST_OPTIONS.HealerStatWeights().args.optionsTab.args
        g = addon.hsw.db["global"]
        opts.hasteRatingPerPct.set(None, "abc")
        opts.hasteRatingPerPct.set(None, "0")
        self.assertEqual((g.hasteRatingPerPct, addon.HasteConv), (1, 100))      # rejected: unchanged
        opts.hasteRatingPerPct.set(None, "10")
        self.assertEqual((g.hasteRatingPerPct, addon.HasteConv, opts.hasteRatingPerPct.get(None)), (10, 1000, "10"))
        opts.intPerCrit.set(None, "40")
        self.assertEqual((g.intPerCritOverride.PALADIN, addon.IntPerCrit, opts.intPerCrit.get(None)), (40, 40, "40"))
        opts.intPerCrit.set(None, "x")                                           # not a number: back to the table
        self.assertEqual((g.intPerCritOverride.PALADIN, addon.IntPerCrit), (0, 31.9))


class Chat(unittest.TestCase):
    def setUp(self):
        self.lua, self.addon = start()
        self.lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end')

    def msgs(self):
        m = self.lua.globals().MSGS
        return [m[i] for i in range(1, len(list(m.keys())) + 1)]

    def chat(self, s):
        self.addon.hsw.ChatCommand(self.addon.hsw, s)

    def test_discover_and_regen(self):
        self.chat("discover on")
        self.assertTrue(self.addon.discoverSpells)
        self.chat("discover off")
        self.assertFalse(self.addon.discoverSpells)
        self.chat("regen")
        m = self.msgs()
        self.assertIn("Spirit 60: 0.125 mana/s per Spirit", m[2])
        self.assertIn("Casting share now: 30%", m[2])

    def test_spec_and_stats(self):
        self.chat("spec")
        self.chat("STATS")
        m = self.msgs()
        self.assertIn("65", m[0])
        self.assertTrue(any("castpct=0.30" in s for s in m), m)
        self.assertTrue(any("IntPerCrit=31.9" in s for s in m), m)

    def test_mana_prints_the_last_changes_to_the_deficit(self):
        self.lua.execute('HSW_TEST_ADDON.ManaDeficit:Spend(250, 0, "cast 913"); HSW_TEST_ADDON.ManaDeficit:Gain(60, 0, "mana return")')
        self.lua.execute('HSW_TEST_ADDON.ManaDeficit:OnPower(0)')
        self.chat("stats")                                                    # leaves a line of its own in the log
        self.chat("mana")
        m = self.msgs()[-3:]
        self.assertTrue(m[0].endswith("cast 913 +250: 0 -> 250 [0 ev]"), m)
        self.assertTrue(m[1].endswith("mana return -60: 250 -> 190 [0 ev]"), m)
        self.assertTrue(m[2].endswith("stats: 190 -> 190 [1 ev]"), m)

    def test_stats_prints_the_mana_deficit(self):
        self.lua.execute("HSW_TEST_ADDON.ManaDeficit:Spend(250); HSW_TEST_ADDON.ManaDeficit:SetDrinkRate(20); HSW_TEST_ADDON.ManaDeficit.buffs = { 3.6 }")
        self.chat("stats")
        self.assertTrue(any("mana deficit=250 drink=20.0/s buffs=3.6/s" in m for m in self.msgs()), self.msgs())

    def test_spec_on_a_class_without_a_healing_spec(self):
        self.lua.execute('STUB.class = "WARRIOR"; STUB.talents = {}; HSW_TEST_ADDON.Util.RebuildTalentCache()')
        self.chat("spec")
        self.assertEqual(self.msgs(), ["Spec: none (this class has no healing spec), supported: false"])

    def test_spec_on_a_healer_with_no_points_yet(self):
        # In game 2026-11-04: a level-3 shaman could not start a segment ("Current spec is not supported")
        self.lua.execute('STUB.talents[1].talents[1].rank = 0; HSW_TEST_ADDON.Util.RebuildTalentCache()')
        self.chat("spec")
        self.assertEqual(self.msgs(), ["Spec: id 65 (Holy Paladin), supported: true"])

    def test_spec_before_talent_data_loads(self):
        self.lua.execute('C_ClassTalents.GetActiveConfigID = function() return nil end; HSW_TEST_ADDON.Util.RebuildTalentCache()')
        self.chat("spec")
        self.assertEqual(self.msgs(), ["Spec: none (talent data not loaded yet), supported: false"])
