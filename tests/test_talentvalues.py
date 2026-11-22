import unittest
from harness import load, CORE_FILES

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


if __name__ == "__main__":
    unittest.main()
