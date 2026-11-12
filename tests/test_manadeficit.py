import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/ManaDeficit.lua"]
# Shadowfang Keep 2026-11-11, level 23 shaman: the figures of `/hsw stats` that day
SETUP = """
HSW_TEST_ADDON.FSR_SECONDS = 5
HSW_TEST_ADDON.ply_maxmana = 1786
HSW_TEST_ADDON.ply_regen_base = 16.75
HSW_TEST_ADDON.ply_castpct = 0.5
HSW_TEST_ADDON.ply_mp5 = 0
"""


class ManaDeficitTests(unittest.TestCase):
    def md(self, extra=""):
        lua, addon = load(FILES, setup=SETUP + extra)
        return lua, addon, addon.ManaDeficit

    def test_archmage_arugal_ends_94_down_not_at_zero(self):
        _, _, md = self.md()
        md.Advance(md, 0)                                           # pulled at a full bar
        md.Spend(md, 103, 8.04); md.Gain(md, 35.72, 8.04)           # a crit: Water Shield returned 2% of 1786
        md.Spend(md, 103, 11.42)
        self.assertEqual(md.Advance(md, 29.75), 0)                  # full again about 22 s in: regen after that restores nothing
        md.Spend(md, 103, 29.75)
        self.assertAlmostEqual(md.Advance(md, 30.77), 103 - 1.02 * 8.375, places=2)   # 94.46; one subtraction at the end gave 0

    def test_the_fight_after_it_matches_the_bar(self):
        _, _, md = self.md()
        md.Advance(md, 0)
        md.Spend(md, 103, 1.483); md.Spend(md, 103, 3.5)
        # 4.227 s inside the five-second rule at half the base rate. The bar read 1620 of 1786: 166 down.
        self.assertAlmostEqual(md.Advance(md, 5.71), 206 - 4.227 * 8.375, places=2)   # 170.6

    def test_deficit_stops_at_a_full_bar_and_at_an_empty_one(self):
        _, _, md = self.md()
        md.Spend(md, 100, 0)                                        # the first call starts from a full bar
        self.assertEqual(md.Advance(md, 60), 0)
        md.Gain(md, 500, 60)
        self.assertEqual(md.deficit, 0)
        md.Spend(md, 1500, 60); md.Spend(md, 1500, 60)
        self.assertEqual(md.deficit, 1786)                          # no emptier than empty

    def test_five_second_rule_runs_from_the_last_spend(self):
        _, _, md = self.md()
        md.Spend(md, 500, 0)
        self.assertAlmostEqual(md.Advance(md, 4), 500 - 4 * 8.375)                  # all inside
        self.assertAlmostEqual(md.Advance(md, 7), 500 - 5 * 8.375 - 2 * 16.75)      # 1 s more inside, 2 s outside
        md.Advance(md, 6)                                                           # going backwards is ignored
        self.assertAlmostEqual(md.deficit, 500 - 5 * 8.375 - 2 * 16.75)

    def test_gear_mp5_and_a_drink_restore_throughout(self):
        _, addon, md = self.md()
        addon.ply_regen_base = 0; addon.ply_mp5 = 25
        md.Spend(md, 1000, 0)
        self.assertAlmostEqual(md.Advance(md, 10), 950)             # 25 MP5 is 5 mana a second, inside the rule too
        md.SetDrinkRate(md, 40, 10)
        self.assertAlmostEqual(md.Advance(md, 20), 500)             # 45 a second while drinking
        md.SetDrinkRate(md, 0, 30)                                  # the time up to the change ran at the old rate
        self.assertAlmostEqual(md.deficit, 50)
        self.assertAlmostEqual(md.Advance(md, 40), 0)

    def test_silence_after_the_five_second_rule_means_a_full_bar(self):
        # Probe 2026-11-12: UNIT_POWER_UPDATE fires for mana while the bar is below full, in and out of combat, and stops when it fills
        _, addon, md = self.md()
        addon.ply_regen_base = 0                                    # something unseen refills the bar: the count alone would stay at 500
        md.Spend(md, 500, 0); md.OnPower(md, 0.1)                   # the cast's own mana event
        md.OnPower(md, 2); md.OnPower(md, 4); md.OnPower(md, 6)     # the bar filling
        self.assertEqual(md.Advance(md, 11.9), 500)                 # 5.9 s of silence: not yet
        self.assertEqual(md.Advance(md, 12), 0)                     # 6 s: full
        md.Spend(md, 100, 30)                                       # and the next cast starts from a full bar
        self.assertEqual(md.deficit, 100)

    def test_silence_inside_the_five_second_rule_proves_nothing(self):
        _, addon, md = self.md()
        addon.ply_regen_base = 0
        md.OnPower(md, 9.8); md.Spend(md, 500, 10)                  # the mana event may come just before the cast event
        self.assertEqual(md.Advance(md, 20.9), 500)                 # quiet for 11 s, but 5 of them some classes regenerate nothing
        self.assertEqual(md.Advance(md, 21), 0)

    def test_silence_is_not_trusted_when_the_casts_own_mana_event_never_came(self):
        _, addon, md = self.md()
        addon.ply_regen_base = 0
        md.OnPower(md, 0); md.Spend(md, 500, 10)                    # no event at the cast: the client is withholding them
        self.assertEqual(md.Advance(md, 60), 500)

    def test_share_is_the_rise_over_the_fight_between_0_and_1(self):
        _, addon, md = self.md()
        self.assertAlmostEqual(md.Share(300, 478.6), 0.1)           # pulled 300 down, ended 478.6 down: 178.6 of 1786
        self.assertEqual(md.Share(400, 250), 0)                     # the fight gained mana
        self.assertEqual(md.Share(0, 5000), 1)
        addon.ply_maxmana = 0
        self.assertEqual(md.Share(0, 500), 0)                       # max mana unknown

    def test_drink_rate_comes_from_the_buff_text(self):
        lua, _, md = self.md('STUB.spellDesc[430] = "Restores 420 mana over 21 sec.  Must remain seated while drinking."'
                             '; STUB.spellDesc[431] = "Restores 1,344 mana over 24 sec."'
                             '; STUB.spellDesc[432] = "Restores 151.2 mana over 18 sec."'
                             '; STUB.spellDesc[433] = "Restores 61 health and 135 mana over 27 sec."'
                             '; STUB.spellDesc[25290] = "Restores 12 mana every 5 seconds."'
                             '; STUB.spellDesc[434] = ""'
                             '; STUB.spellDesc[1133] = "Restores 34 mana per second."'
                             '; STUB.spellDesc[1134] = "Restores 12 health and 1,027.5 mana per second.  Must remain seated while drinking."')
        self.assertAlmostEqual(md.DrinkRateOf(1133), 34)            # Melon Juice, seen in game 2026-11-11
        self.assertAlmostEqual(md.DrinkRateOf(1134), 1027.5)
        self.assertAlmostEqual(md.DrinkRateOf(430), 20)
        self.assertAlmostEqual(md.DrinkRateOf(431), 56)
        self.assertAlmostEqual(md.DrinkRateOf(432), 8.4)
        self.assertAlmostEqual(md.DrinkRateOf(433), 5)
        self.assertEqual(md.DrinkRateOf(25290), 0)                  # Blessing of Wisdom: not a drink
        self.assertIsNone(md.DrinkRateOf(434))                      # empty text: the spell data is not loaded yet
        self.assertIsNone(md.DrinkRateOf(999))                      # no text
        lua.execute('STUB.spellDesc[999] = "Restores 300 mana over 30 sec."')
        self.assertAlmostEqual(md.DrinkRateOf(999), 10)             # asked again once it reads

    def test_a_drink_worded_as_a_percent_follows_max_mana(self):
        _, addon, md = self.md('STUB.spellDesc[1135] = "Restores 2% of your mana per second."'
                               '; STUB.spellDesc[1136] = "Restores 4.5% of your maximum mana per second.  Must remain seated while drinking."'
                               '; STUB.spellDesc[1137] = "Increases your mana regeneration by 2% per second."')
        self.assertAlmostEqual(md.DrinkRateOf(1135), 0.02 * 1786)
        self.assertAlmostEqual(md.DrinkRateOf(1136), 0.045 * 1786)
        self.assertEqual(md.DrinkRateOf(1137), 0)                   # a percent of something else
        addon.ply_maxmana = 2000                                    # a level or an Intellect buff later
        self.assertAlmostEqual(md.DrinkRateOf(1135), 40)

    def test_a_lasting_buff_rate_comes_from_its_text(self):
        _, _, md = self.md('STUB.spellDesc[19850] = "Places a Blessing on the friendly target, restoring 18 mana every 5 seconds for 1 |4hour:hrs;.  Players may only have one Blessing on them per Paladin at any one time."'
                           '; STUB.spellDesc[432] = "Restores 835 mana over 24 sec.  Must remain seated while drinking."'
                           '; STUB.spellDesc[1460] = "Increases the target\'s Intellect by 7 for 1 |4hour:hrs;."')
        self.assertAlmostEqual(md.BuffRateOf(19850), 3.6)           # Blessing of Wisdom, seen in game 2026-11-12
        self.assertEqual(md.DrinkRateOf(19850), 0)                  # not a drink: it stays through combat
        self.assertEqual(md.BuffRateOf(432), 0)
        self.assertEqual(md.BuffRateOf(1460), 0)
        self.assertIsNone(md.BuffRateOf(999))                       # no text: asked again later

    def test_a_buff_restores_mana_unless_the_clients_rates_already_carry_it(self):
        lua, addon, md = self.md()
        buffs = lambda rates: lua.execute("HSW_TEST_ADDON.ManaDeficit.buffs = { %s }" % rates)
        addon.ply_regen_base = 0
        buffs("3.6")                                                # Blessing of Wisdom: not in GetManaRegen()
        md.Spend(md, 1000, 0)
        self.assertAlmostEqual(md.Advance(md, 100), 640)
        buffs("3.6, 2.0"); addon.ply_flat_buff = 2.0                # plus Might of Stormwind, which the rates hold
        self.assertAlmostEqual(md.Advance(md, 200), 280)            # still 3.6 a second added
        buffs("3.6")                                                # its text not understood: the rates' 2.0 is not the blessing's
        self.assertAlmostEqual(md.Advance(md, 250), 100)
        buffs("2.0")                                                # alone, and the rates hold it: nothing added
        self.assertAlmostEqual(md.Advance(md, 300), 100)
        buffs("3.6, 2.0"); addon.ply_flat_buff = 5.6                # the rates hold both
        self.assertAlmostEqual(md.Advance(md, 400), 100)

    def test_scan_sums_drinks_and_buffs_and_keeps_the_rates_while_buffs_are_hidden(self):
        lua, _, md = self.md('STUB.spellDesc[430] = "Restores 420 mana over 21 sec."; STUB.spellDesc[1243] = "Increases Stamina by 3."'
                             '; STUB.spellDesc[19850] = "Places a Blessing on the friendly target, restoring 18 mana every 5 seconds."')
        lua.execute("STUB.auras = { { id = 1243 }, { id = 430 }, { id = 19850 } }; READ_AURA = C_UnitAuras.GetAuraDataByIndex")
        md.Spend(md, 500, 0)
        md.ScanBuffs(md, 0)
        self.assertAlmostEqual(md.drinkRate, 20)
        self.assertAlmostEqual(md.UnseenBuffRate(md), 3.6)
        lua.execute('C_UnitAuras.GetAuraDataByIndex = function() error("Auras cannot be accessed when secret") end')
        md.ScanBuffs(md, 5)                                         # in combat: unreadable, nothing changes
        self.assertAlmostEqual(md.drinkRate, 20)
        self.assertAlmostEqual(md.UnseenBuffRate(md), 3.6)
        lua.execute("C_UnitAuras.GetAuraDataByIndex = READ_AURA; STUB.auras = { { id = 1243 } }")
        md.ScanBuffs(md, 10)                                        # readable again, the drink and the blessing are gone
        self.assertEqual((md.drinkRate, md.UnseenBuffRate(md)), (0, 0))
        self.assertAlmostEqual(md.deficit, 500 - 5 * 8.375 - 5 * 16.75 - 10 * 20 - 10 * 3.6)   # both ran until the scan that missed them


if __name__ == "__main__":
    unittest.main()
