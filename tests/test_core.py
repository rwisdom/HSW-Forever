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
        a.SegmentManager:Enqueue("Boss")
        local s = a.SegmentManager:Get(0)
        s:IncFillerCasts(660)
        a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false, 1000, 0)
        STUB.time = {seconds}
        s:End()
    """)
    return addon.SegmentManager.Get(addon.SegmentManager, 0)


class Database(unittest.TestCase):
    def test_defaults(self):
        _, addon = start()
        g = addon.hsw.db["global"]
        self.assertEqual((g.schema, g.enabledInDungeons, g.enabledInRaids, g.enabledInBattlegrounds), (2, True, True, False))
        self.assertEqual((g.hasteRatingPerPct, g.intPerCritOverride.PALADIN, g.maxSegments, g.neverShow), (1, 0, 10, False))
        for gone in ("useHPMoverHPCT", "useVersDR", "useCritResurg", "enabledInMythicPlusDungeons", "enabledInLfrRaids"):
            self.assertIsNone(g[gone])

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
        seg = fought_segment(lua, addon)           # HPM 1000/660, 100 s all outside the FSR, no Int talent (mult 1.0), Human Spirit mult 1.05
        heal, crt, hst, int_, spi, mp5 = addon.GetStatsForSegment(addon, seg)
        self.assertEqual(heal, 1)
        self.assertAlmostEqual(crt, seg.t.crit / seg.t.heal)
        self.assertEqual(hst, 0)                    # no chain casts
        self.assertAlmostEqual(int_, (seg.t.int + 15 * 1.0 * 1000 / 660) / seg.t.heal)
        self.assertAlmostEqual(spi, 0.1 * 1.05 * 100 * (1000 / 660) / seg.t.heal)
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
        self.assertEqual((h.Name, h.Realm, h.Region), ("Me", "Realm", "US"))
        names = addon.GetHistoricalSegmentsList(addon)
        self.assertIn("Boss 1:40", names[0])
        self.assertIn("Spell_Holy_HolyBolt", names[0])

    def test_raid_trash_skipped_bosses_kept(self):
        lua, addon = start(extra='STUB.instance = { name = "MC", type = "raid", difficultyId = 14 }')
        lua.execute("""
            local a = HSW_TEST_ADDON
            a.SegmentManager:Enqueue(); a.SegmentManager:SetCurrentId("Trash")
            a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25292, false, 1000, 0)
            a.SegmentManager:Get(0):End()
        """)
        addon.AddHistoricalSegment(addon, addon.SegmentManager.Get(addon.SegmentManager, 0))
        self.assertEqual(addon.History.Size(addon.History), 0)
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        self.assertEqual(addon.History.Size(addon.History), 1)

    def test_example_segment_when_history_empty(self):
        _, addon = start()
        names = addon.GetHistoricalSegmentsList(addon)
        self.assertEqual(addon.History.Size(addon.History), 1)
        self.assertIn("Example Segment!", names[0])

    def test_history_options_table_uses_new_labels(self):
        lua, addon = start()
        addon.AddHistoricalSegment(addon, fought_segment(lua, addon))
        t = addon.BuildOptionsTableForHistorySegment(addon, 0)
        names = [v.name for _, v in t.items() if v.name]
        for label in ("+Healing", "Crit Rating", "Haste (HPCT)", "Intellect", "Spirit", "MP5", "Pawn >>", "icon_Illumination"):
            self.assertTrue(any(label in n for n in names), label)
        self.assertFalse(any("QE" in n or "Versatility" in n for n in names))


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
        self.assertIn("Spirit 60 -> 10.00", m[2])
        self.assertIn("0.1000", m[3])

    def test_spec_and_stats(self):
        self.chat("spec")
        self.chat("STATS")
        m = self.msgs()
        self.assertIn("65", m[0])
        self.assertTrue(any("castpct=0.30" in s for s in m), m)
        self.assertTrue(any("IntPerCrit=31.9" in s for s in m), m)
