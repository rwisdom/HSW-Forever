import unittest
from harness import load


class CompatTests(unittest.TestCase):
    def test_legacy_fallbacks(self):
        lua, addon = load(["Classes/Compat.lua"])
        self.assertEqual(addon.Compat.GetSpellInfo(635), ("spell635", None, "icon635"))
        self.assertEqual(addon.Compat.GetSpellCooldown(635), (0, 0))
        self.assertEqual(addon.Compat.GetSpellHaste(), 0)
        self.assertIsNone(addon.Compat.GetSpellManaCost(635))   # STUB.spellCost empty → API returns nil

    def test_mana_cost_from_power_cost_table(self):
        lua, addon = load(["Classes/Compat.lua"], setup="STUB.spellCost[635] = 35")
        self.assertEqual(addon.Compat.GetSpellManaCost(635), 35)

    def test_prefers_namespaced_apis(self):
        setup = """
        C_Spell = { GetSpellInfo = function(id) return { name = "ns" .. id, iconID = 7 } end,
                    GetSpellCooldown = function(id) return { startTime = 5, duration = 2 } end }
        C_UnitAuras = { GetAuraDataByIndex = function(unit, i)
            if i == 1 then return { applications = 3, expirationTime = 9, sourceUnit = "player", spellId = 14751 } end
            return nil end }
        """
        lua, addon = load(["Classes/Compat.lua"], setup=setup)
        self.assertEqual(addon.Compat.GetSpellInfo(1), ("ns1", None, 7))
        self.assertEqual(addon.Compat.GetSpellCooldown(1), (5, 2))
        self.assertEqual(addon.Compat.UnitAura("player", 1), (3, 9, "player", 14751))
        self.assertIsNone(addon.Compat.UnitAura("player", 2))

    def test_legacy_unit_aura(self):
        lua, addon = load(["Classes/Compat.lua"], setup="STUB.auras[1] = { id = 16870, count = 2, expiration = 4 }")
        self.assertEqual(addon.Compat.UnitAura("player", 1), (2, 4, "player", 16870))
