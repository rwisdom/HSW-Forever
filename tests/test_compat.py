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

    def test_secret_values_become_nil(self):
        # Forever hides spell timing behind "secret" numbers; the stub marks -777 as secret.
        setup = """
        issecretvalue = function(v) return v == -777 end
        STUB.cooldowns[635] = { start = -777, duration = -777 }
        STUB.spellCost[635] = -777
        STUB.auras[1] = { id = 16870, count = -777, expiration = -777 }
        """
        lua, addon = load(["Classes/Compat.lua"], setup=setup)
        self.assertEqual(addon.Compat.PlainNumber(5), 5)
        self.assertIsNone(addon.Compat.PlainNumber(-777))
        self.assertIsNone(addon.Compat.PlainNumber("5"))
        self.assertEqual(addon.Compat.GetSpellCooldown(635), (None, None))
        self.assertIsNone(addon.Compat.GetSpellManaCost(635))             # caller falls back to the table cost
        self.assertEqual(addon.Compat.UnitAura("player", 1), (None, None, "player", 16870))

    def test_aura_read_refused_in_combat(self):
        # Forever throws from the aura API in combat; the 5th return flags "unreadable", not "empty".
        setup = 'C_UnitAuras = { GetAuraDataByIndex = function() error("Auras cannot be accessed when secret") end }'
        lua, addon = load(["Classes/Compat.lua"], setup=setup)
        self.assertEqual(addon.Compat.UnitAura("player", 1), (None, None, None, None, True))
        lua, addon = load(["Classes/Compat.lua"], setup='function UnitAura() error("secret") end')
        self.assertEqual(addon.Compat.UnitAura("player", 1), (None, None, None, None, True))

    def test_legacy_unit_aura(self):
        lua, addon = load(["Classes/Compat.lua"], setup="STUB.auras[1] = { id = 16870, count = 2, expiration = 4 }")
        self.assertEqual(addon.Compat.UnitAura("player", 1), (2, 4, "player", 16870))
