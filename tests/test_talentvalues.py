import unittest
from harness import load, CORE_FILES
from parsers import start as start_parser, talents_lua

SHAMAN = 'STUB.class = "SHAMAN"; STUB.talents = { {name="Elemental", talents={}}, {name="Enhancement", talents={}}, {name="Restoration", talents={ {name="Tidal Mastery", rank=5, max=5}, {name="Healing Focus", rank=3, max=3} }} }'
ITEMS = 'function GetItemInfo(item) if item == 2 then return "Second", item, 3, 60, 55, "Armor", "Totem", 1, "INVTYPE_RELIC", "icon_second" end end'


def start(extra=""):
    """Core files only, a spec 264 registered with one talent formula (rough) and two relics, a segment that healed."""
    lua, addon = load(CORE_FILES, setup=SHAMAN + "\n" + extra)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.TalentValues:Register(264, {
            talents = { ["Tidal Mastery"] = { rough = true, fn = function(ctx, rank) return rank * ctx.hpm * ctx.spell("Healing Wave").healing end } },
            relics = {
                { name = "First", id = 1, fn = function(ctx) return ctx.seg.totemMana end },
                { name = "Second", id = 2, rough = true, fn = function(ctx) return 10 end },
            },
        })
        SEG = a.Segment.Create("x")
        SEG.t.heal = 2; SEG.fillerHealing = 600; SEG.fillerManaSpent = 200   -- 2 healing per point of Healing, 3 healing per mana
        SEG:Spell("Healing Wave").healing = 10
        SEG.totemMana = 8
        TALENTS = a.Util.GetTalentSnapshot()
    """)
    return lua, addon


class Pricing(unittest.TestCase):
    def test_talents_get_a_value_in_points_of_healing(self):
        lua, addon = start()
        g = lua.globals()
        self.assertTrue(addon.TalentValues.PriceTalents(addon.TalentValues, g.SEG, 264, g.TALENTS))
        mastery, focus = g.TALENTS[1], g.TALENTS[2]
        self.assertEqual((mastery.value, mastery.rough), (5 * 3 * 10 / 2, True))
        self.assertEqual((focus.value, focus.rough), (None, None))            # no formula: no healing value

    def test_a_spec_without_formulas_is_not_priced(self):
        lua, addon = start()
        g = lua.globals()
        self.assertFalse(addon.TalentValues.PriceTalents(addon.TalentValues, g.SEG, 65, g.TALENTS))
        self.assertIsNone(g.TALENTS[1].value)
        self.assertIsNone(addon.TalentValues.PriceRelics(addon.TalentValues, g.SEG, 65, None))

    def test_every_relic_is_priced_and_the_worn_one_marked(self):
        lua, addon = start(extra=ITEMS)
        g = lua.globals()
        worn = lua.eval('{ name = "First", icon = "icon_worn" }')
        rows = addon.TalentValues.PriceRelics(addon.TalentValues, g.SEG, 264, worn)
        self.assertEqual([(rows[i].name, rows[i].value, rows[i].rough, rows[i].worn, rows[i].icon) for i in (1, 2)],
                         [("First", 4, None, True, "icon_worn"), ("Second", 5, True, None, "icon_second")])
        self.assertIsNone(rows[3])

    def test_a_worn_relic_off_the_list_gets_a_row_without_a_value(self):
        lua, addon = start()
        g = lua.globals()
        rows = addon.TalentValues.PriceRelics(addon.TalentValues, g.SEG, 264, lua.eval('{ name = "Totem of Rage", icon = "icon_rage" }'))
        self.assertEqual((rows[1].worn, rows[1].icon, rows[2].worn), (None, None, None))   # nothing known about an item not worn
        self.assertEqual((rows[3].name, rows[3].value, rows[3].worn, rows[3].icon), ("Totem of Rage", None, True, "icon_rage"))

    def test_trinket_stats_are_priced_at_the_entrys_weights(self):
        lua, addon = start()
        stats = lua.eval('{ ITEM_MOD_SPELL_HEALING_DONE_SHORT = 20, ITEM_MOD_CRIT_RATING_SHORT = 14, ITEM_MOD_INTELLECT_SHORT = 5,'
                         ' ITEM_MOD_SPIRIT_SHORT = 4, ITEM_MOD_MANA_REGENERATION_SHORT = 3, ITEM_MOD_STAMINA_SHORT = 9 }')
        h = lua.eval('{ Heal = 1, Crt = 12, Hst = 7, Int = 0.5, Spi = 0.25, Mp5 = 2 }')
        self.assertAlmostEqual(addon.TalentValues.Trinket(stats, h), 20 + 12 + 2.5 + 1 + 6)   # 14 crit rating is 1%; stamina is worth nothing
        self.assertIsNone(addon.TalentValues.Trinket(lua.eval('{ ITEM_MOD_STAMINA_SHORT = 9 }'), h))
        self.assertIsNone(addon.TalentValues.Trinket(lua.eval('{}'), h))


SHAMAN_FILES = ["Parsers/RestoShaman.lua", "Parsers/RestoShamanValues.lua"]
SHAMAN_TALENTS = [("Elemental", []),
                  ("Enhancement", [("Thundering Strikes", 5), ("Ancestral Knowledge", 5), ("Mental Quickness", 2)]),
                  ("Restoration", [("Improved Healing Wave", 5), ("Tidal Focus", 5), ("Mindfulness", 3), ("Healing Focus", 3), ("Water Shield", 1),
                                   ("Tidal Mastery", 5), ("Restorative Totems", 5), ("Mana Tide Totem", 1), ("Healing Way", 3), ("Purification", 5),
                                   ("Riptide", 1), ("Totemic Focus", 5)])]
FIGHT = """
    local a = HSW_TEST_ADDON
    local s = a.SegmentManager:Get(0)
    s.t.heal = 2; s.t.crit = 30; s.t.int = 4; s.t.haste_hpct = 100
    s.totalHealing = 11000; s.fillerHealing = 12000; s.fillerCasts = 20; s.chainCasts = 10
    s.fillerManaSpent = 6120; s.manaRestore = 120
    s.timeInFSR = 60; s.totemMana = 150; s.manaTideMana = 352; s.shieldsEmptied = 2
    local hw = s:Spell("Healing Wave"); hw.healing, hw.casts, hw.castTime, hw.baseMana = 5000, 10, 30, 4000
    local lhw = s:Spell("Lesser Healing Wave"); lhw.baseMana, lhw.crit = 1000, 10
    local rt = s:Spell("Riptide"); rt.healing, rt.mana, rt.baseMana = 900, 150, 600
    local hst = s:Spell("Healing Stream Totem"); hst.healing, hst.baseMana = 300, 80
    local talents = a.Util.GetTalentSnapshot()
    a.TalentValues:PriceTalents(s, 264, talents)
    ROWS = {}
    for _, t in ipairs(talents) do ROWS[t.name] = t end
    RELICS = {}
    for _, r in ipairs(a.TalentValues:PriceRelics(s, 264, nil)) do RELICS[r.name] = r end
"""


class RestoShamanValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lua, _, _ = start_parser("SHAMAN", SHAMAN_TALENTS, SHAMAN_FILES)
        lua.execute(FIGHT)
        cls.rows, cls.relics = lua.globals().ROWS, lua.globals().RELICS

    def check(self, row, value, rough=None):
        self.assertAlmostEqual(row.value, value)
        self.assertEqual(row.rough, rough)

    def test_crit_talents_are_worth_the_fights_crit(self):
        self.check(self.rows["Tidal Mastery"], 5 * 30 / 2)
        self.check(self.rows["Thundering Strikes"], 5 * 30 / 2)

    def test_intellect_talents(self):
        self.check(self.rows["Mental Quickness"], 0.15 * 2 * 110)                    # the Healing it gives
        self.check(self.rows["Ancestral Knowledge"], 0.02 * 5 * (110 / 1.1) * (4 / 1.1) / 2)   # 10 sheet Int, each a gear Int's worth over 1.1

    def test_percent_healing_talents(self):
        self.check(self.rows["Purification"], 11000 * 0.10 / 1.10 / 2)
        self.check(self.rows["Healing Way"], 5000 * 0.25 / 1.25 / 2)
        self.check(self.rows["Restorative Totems"], 300 * 0.5 / 1.5 / 2)

    def test_mana_talents(self):
        self.check(self.rows["Tidal Focus"], 0.05 * (4000 + 1000 + 600) * 2 / 2)     # the totem's 80 is not a healing spell's
        self.check(self.rows["Mindfulness"], 0.5 * 10 * 60 * 2 / 2)
        self.check(self.rows["Water Shield"], 120 * 2 / 2)

    def test_rough_talents(self):
        self.check(self.rows["Improved Healing Wave"], 20 * 60 * 5000 / 12000 / 2, True)   # 3.0 s to 2.5 s is 20% haste; haste is worth 60 per 1%
        self.check(self.rows["Riptide"], (900 - 150 * 2) / 2, True)
        self.check(self.rows["Mana Tide Totem"], 352 * 2 / 2, True)
        self.check(self.rows["Totemic Focus"], 0.25 * 150 / 0.75 * 2 / 2, True)

    def test_a_talent_that_heals_nothing_has_no_value(self):
        self.assertIsNone(self.rows["Healing Focus"].value)

    def test_relics(self):
        self.check(self.relics["Tidal Totem"], 0.05 * 4000 * 2 / 2)
        self.check(self.relics["Totem of Sustaining"], 2 * 0.02 * 3000 * 2 / 2, True)
        self.check(self.relics["Totem of Urgency"], 4 * 10 / 2)
        self.check(self.relics["Totem of Tides"], 0.05 * 600 * 2 / 2)
        self.check(self.relics["Polished Driftwood Icon"], 0.08 * 10 * 60 * 2 / 2)

    def test_a_fight_without_the_spells_prices_at_zero(self):
        lua, addon, seg = start_parser("SHAMAN", SHAMAN_TALENTS, SHAMAN_FILES)
        lua.execute("""
            local a = HSW_TEST_ADDON
            local s = a.SegmentManager:Get(0)
            s.t.heal = 2; s.totalHealing = 100
            TALENTS = a.Util.GetTalentSnapshot()
            a.TalentValues:PriceTalents(s, 264, TALENTS)
        """)
        t = lua.globals().TALENTS
        for i in range(1, len(list(t.keys())) + 1):
            if t[i].name in ("Improved Healing Wave", "Riptide", "Tidal Focus", "Healing Way", "Totemic Focus"):
                self.assertEqual(t[i].value, 0, t[i].name)                           # no casts, no mana spent: nothing, and no division by zero


HISTORY_FILES = CORE_FILES + SHAMAN_FILES + ["DisplayPanel.lua", "Core.lua"]
CHARM, TIDES = "|Hitem:1|h[Lucky Charm]|h", "|Hitem:2|h[Totem of Tides]|h"   # item links: the page prints them
GEAR = ('function GetInventoryItemLink(_, slot) return ({ [13] = "' + CHARM + '", [18] = "' + TIDES + '" })[slot] end'
        '; function GetItemInfo(item)'
        ' if item == "' + CHARM + '" then return "Lucky Charm", item, 3, 45, 40, "Armor", "Trinket", 1, "INVTYPE_TRINKET", "icon_charm" end'
        ' if item == "' + TIDES + '" then return "Totem of Tides", item, 3, 60, 55, "Armor", "Totem", 1, "INVTYPE_RELIC", "icon_tides" end'
        ' if item == 249398 then return "Polished Driftwood Icon", item, 3, 60, 55, "Armor", "Totem", 1, "INVTYPE_RELIC", "icon_driftwood" end end'
        '; function GetItemStats(link) if link == "' + CHARM + '" then return { ITEM_MOD_SPELL_HEALING_DONE_SHORT = 20, ITEM_MOD_STAMINA_SHORT = 5 } end end'
        '; function GetItemSpell(link) if link == "' + CHARM + '" then return "Lucky Strike" end end')


def shaman_entry(extra=GEAR):
    """A logged boss fight of a Resto Shaman: one Healing Wave R10 heal of 1000 after 620 mana of filler casts, 100 s long."""
    lua, addon = load(HISTORY_FILES, setup=talents_lua("SHAMAN", SHAMAN_TALENTS) + "\n" + extra)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.hsw:OnInitialize()
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.UnitManager.units["Player-1"] = "player"
        a.SegmentManager:Enqueue("Boss", true)
        local s = a.SegmentManager:Get(0)
        s:IncFillerCasts(620)
        a.StatParser:DecompHealingForCurrentSpec("SPELL_HEAL", "Player-1", 25357, false)
        STUB.time = 100
        a.StatParser:ApplyTotals(s, { [25357] = 1000 })
        s:End()
        a:AddHistoricalSegment(s)
    """)
    return lua, addon, addon.History.Get(addon.History, 0)


def by_name(rows):
    return {rows[i].name: rows[i] for i in range(1, len(list(rows.keys())) + 1)}


class HistoryEntry(unittest.TestCase):
    def test_talents_are_priced_on_the_entry(self):
        _, _, h = shaman_entry()
        self.assertTrue(h.TalentsPriced)
        t = by_name(h.Talents)
        self.assertAlmostEqual(t["Tidal Mastery"].value, 5 * h.Crt)            # a point is 1% crit: the entry's Crit weight
        self.assertAlmostEqual(t["Mental Quickness"].value, 0.15 * 2 * 110)
        self.assertEqual((t["Tidal Mastery"].max, t["Riptide"].rough, t["Healing Focus"].value), (5, True, None))

    def test_relics_are_priced_and_the_worn_one_marked(self):
        _, _, h = shaman_entry()
        self.assertEqual([h.Relics[i].name for i in range(1, 6)],
                         ["Tidal Totem", "Totem of Sustaining", "Totem of Urgency", "Totem of Tides", "Polished Driftwood Icon"])
        r = by_name(h.Relics)
        self.assertEqual((h.Slot18.name, r["Totem of Tides"].worn, r["Totem of Tides"].icon), ("Totem of Tides", True, "icon_tides"))
        self.assertEqual((r["Tidal Totem"].worn, r["Tidal Totem"].icon, r["Polished Driftwood Icon"].icon), (None, None, "icon_driftwood"))
        self.assertEqual((r["Tidal Totem"].value, r["Totem of Sustaining"].rough), (0, True))   # no Healing Wave cast was seen

    def test_a_trinkets_stats_are_priced(self):
        _, _, h = shaman_entry()
        self.assertEqual((h.Slot13.value, h.Slot13.rough), (20, True))        # 20 Healing at weight 1; it has a use effect
        self.assertIsNone(h.Slot14)


if __name__ == "__main__":
    unittest.main()
