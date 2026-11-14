import unittest
from harness import load, CORE_FILES

FILES = CORE_FILES + ["Events.lua"]
PALADIN = 'STUB.class = "PALADIN"; STUB.talents = { {name="Holy", talents={ {name="Illumination", rank=5, max=5} }}, {name="Protection", talents={}}, {name="Retribution", talents={}} }'
PRIEST = 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={ {name="Meditation", rank=3, max=3} }}, {name="Holy", talents={}} }'
LITANY = 'STUB.class = "PRIEST"; STUB.talents = { {name="Discipline", talents={}}, {name="Holy", talents={ {name="Litany of Light", rank=2, max=2} }} }'
SHAMAN = 'STUB.class = "SHAMAN"; STUB.talents = { {name="Elemental", talents={}}, {name="Enhancement", talents={}}, {name="Restoration", talents={ {name="Tidal Mastery", rank=1, max=5} }} }'
PARTY = 'STUB.group = "party"; STUB.groupSize = 1; STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"'
HL = 25292     # Holy Light R9, 660 mana, filler, 2.5 s cast
FH = 10917     # Flash Heal R7, 380 mana, filler
FH6 = 10916    # Flash Heal R6, 315 mana
RENEW = 25315  # Renew R10, 410 mana
PWS = 10901    # Power Word: Shield R10
HW3 = 547      # Healing Wave R3, 80 mana
CHAIN = 10623  # Chain Heal R3, 405 mana
INNER_FOCUS, WEAKENED_SOUL, WATER_SHIELD = 14751, 6788, 408510
POTION, RUNE, EARTH_SHOCK = 437, 16666, 8045   # not in the spell database: recognised by their tooltip text
DESCS = ('STUB.spellDesc[437] = "Restores 140 to 180 mana."'
         '; STUB.spellDesc[16666] = "Restores 900 to 1500 mana at the cost of 600 to 1000 life."'
         '; STUB.spellDesc[8045] = "Instantly shocks the target with concussive force, causing 17 to 19 Nature damage."')
EARTHFURY5 = ('WORN = { "Earthfury Belt", "Earthfury Boots", "Earthfury Bracers", "Earthfury Epaulets", "Earthfury Gauntlets", "Earthfury Piece 6" }'
              '; function GetInventoryItemLink(_, slot) return WORN[slot] end; function GetItemInfo(link) return link end')


def start(setup=PALADIN, spec=65, extra=""):
    """In combat, parser registered for `spec`, unit events wired to a stub frame, one unnamed live segment."""
    lua, addon = load(FILES, setup=setup + "\n" + extra)
    lua.execute(f"""
        local a = HSW_TEST_ADDON
        a.StatParser:Create({spec}, {{}})
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.frame = CreateFrame(); a:SetupUnitEvents()
        a.SegmentManager:Enqueue(); a.UnitManager:Cache()
        local ttl = a.SegmentManager:Get("Total")                 -- as StartFight does: Total is live for the fight
        ttl.startTime = a.SegmentManager:Get(0).startTime; ttl.fsrLastAccum = ttl.startTime
        a.inCombat = true
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def fire(addon, event, *args):
    """Delivers a unit event the way the client would: through the frame's OnEvent script."""
    addon.frame.OnEvent(addon.frame, event, *args)


def cast(addon, spell, target=""):
    fire(addon, "UNIT_SPELLCAST_SENT", "player", target, "cast-guid", spell)
    fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast-guid", spell)


class UnitEvents(unittest.TestCase):
    def test_secret_hostile_target_name_leaves_the_fight_unnamed(self):
        # In combat the hostile target's name is a secret string: comparing it throws, so the segment stays "Trash".
        lua, addon, seg = start(extra='issecretvalue = function(v) return v == "SECRET" end; STUB.names.target = "SECRET"'
                                      '; function UnitExists() return true end; function UnitCanAttack() return true end')
        lua.execute("function HSW_TEST_ADDON:StartFight() end")   # DisplayPanel.lua is not loaded here; the segment already exists
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)
        self.assertEqual(seg.id, "Trash")
        lua.execute('STUB.names.target = "Mr. Smite"')
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)
        self.assertEqual(seg.id, "Mr. Smite")

    def test_fight_ends_when_nobody_is_in_combat(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("function HSW_TEST_ADDON:EndFight() self.inCombat = false end")   # DisplayPanel.lua is not loaded here
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertFalse(addon.inCombat)

    def test_fight_outlives_the_players_combat_while_the_group_fights(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("function HSW_TEST_ADDON:EndFight() self.inCombat = false end; STUB.combat.party1 = true")
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertTrue(addon.inCombat)                                    # Bob still fights: the healer only flickered out
        lua.execute("STUB.tick()")
        self.assertTrue(addon.inCombat)
        lua.execute("STUB.combat.party1 = false; STUB.tick()")
        self.assertFalse(addon.inCombat)
        self.assertEqual(len(list(lua.globals().STUB.tickers.keys())), 0)   # the poll stopped with the fight

    def test_boss_pulled_mid_fight_gets_its_own_segment(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("""
            FIGHTS = {}
            function HSW_TEST_ADDON:EndFight() if self.inCombat then table.insert(FIGHTS, "end"); self.inCombat = false end end
            function HSW_TEST_ADDON:StartFight(id) table.insert(FIGHTS, "start:" .. tostring(id)); self.inCombat = true end
            STUB.combat.party1 = true
        """)
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)                            # trash: healer out, Bob fighting -> poll
        addon.hsw.ENCOUNTER_START(addon.hsw, "ENCOUNTER_START", 1, "Lucifron")
        self.assertEqual(list(lua.globals().FIGHTS.values()), ["end", "start:Lucifron"])
        self.assertTrue(addon.inBossFight)
        self.assertEqual(len(list(lua.globals().STUB.tickers.keys())), 0)    # the trash poll cannot end the boss fight
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)                            # mid-boss flicker: ignored
        self.assertTrue(addon.inCombat)
        addon.hsw.ENCOUNTER_END(addon.hsw)
        self.assertEqual(list(lua.globals().FIGHTS.values()), ["end", "start:Lucifron", "end"])
        self.assertFalse(addon.inBossFight)

    def test_discover_mode_saves_the_combat_boundaries(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("function HSW_TEST_ADDON:EndFight() end; STUB.combat.party1 = true; HSW_TEST_ADDON.discoverSpells = true")
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        addon.hsw.ENCOUNTER_END(addon.hsw)
        saved = list(addon.hsw.db["global"].discoverLog.values())
        self.assertEqual([s.split(" AM ")[1] for s in saved], ["player left combat, group still fighting.", "encounter ended."])

    def test_encounter_start_with_no_open_fight(self):
        lua, addon, seg = start()
        lua.execute("""
            FIGHTS = {}
            function HSW_TEST_ADDON:EndFight() if self.inCombat then table.insert(FIGHTS, "end"); self.inCombat = false end end
            function HSW_TEST_ADDON:StartFight(id) table.insert(FIGHTS, "start:" .. tostring(id)); self.inCombat = true end
        """)
        addon.inCombat = False
        addon.hsw.ENCOUNTER_START(addon.hsw, "ENCOUNTER_START", 1, "Lucifron")
        self.assertEqual(list(lua.globals().FIGHTS.values()), ["start:Lucifron"])

    def test_untracked_combat_and_entering_world_advance_the_session_watermark(self):
        lua, addon, seg = start()
        lua.execute('STUB.sessions = { { sessionID = 5, name = "Boar" } }')
        addon.inCombat = False                                                # no fight open: the content gate refused it
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertEqual(addon.SessionTotals.watermark, 5)
        lua.execute('STUB.sessions[2] = { sessionID = 6, name = "Wolf" }')
        addon.hsw.PLAYER_ENTERING_WORLD(addon.hsw)
        self.assertEqual(addon.SessionTotals.watermark, 6)
        lua.execute('STUB.sessions[3] = { sessionID = 7, name = "Rabbit" }; function HSW_TEST_ADDON:EndFight() self.inCombat = false end')
        addon.inCombat = True                                                 # a tracked fight: its sessions are the finaliser's to claim
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertEqual(addon.SessionTotals.watermark, 6)

    def test_secret_combat_flag_counts_as_out_of_combat(self):
        lua, addon, seg = start(extra=PARTY + '; issecretvalue = function(v) return v == "SECRET" end')
        lua.execute('function HSW_TEST_ADDON:EndFight() self.inCombat = false end; STUB.combat.party1 = "SECRET"')
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertFalse(addon.inCombat)

    def test_heal_and_crit_heal_are_counted(self):
        lua, addon, seg = start()
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", "secret", 2)        # release client: the amount is a secret value
        self.assertEqual((seg.hits[HL].direct.n, seg.hits[HL].direct.crit), (1, 0))
        self.assertEqual(seg.totalHealing, 0)                                 # priced at fight end, not here
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "CRITICAL", "secret", 2)
        self.assertEqual((seg.hits[HL].direct.n, seg.hits[HL].direct.crit), (2, 1))
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.hits[HL].direct.n, 2)

    def test_heals_on_others_need_a_cast_on_them(self):
        lua, addon, seg = start(extra=PARTY)
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)           # not ours
        self.assertEqual(len(list(seg.hits.keys())), 0)
        cast(addon, HL, "Bob")
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)
        self.assertEqual(seg.hits[HL].targets.Bob, 1)

    def test_quiet_failure_of_a_duplicate_sent_leaves_one_expectation(self):
        # Forever sends a queued cast twice and fails one copy quietly
        lua, addon, seg = start(extra=PARTY)
        fire(addon, "UNIT_SPELLCAST_SENT", "player", "Bob", "cast-A", HL)
        fire(addon, "UNIT_SPELLCAST_SENT", "player", "Bob", "cast-B", HL)
        fire(addon, "UNIT_SPELLCAST_FAILED_QUIET", "player", "cast-B", HL)
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "CRITICAL", 900, 2)     # someone else's heal on Bob, same frame
        self.assertEqual(seg.hits[HL].direct.n, 1)

    def test_filler_cast_records_mana(self):
        lua, addon, seg = start()
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HL)          # no cost API in stub -> table cost 660
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (1, 660))
        lua.execute(f"STUB.spellCost[{HL}] = 500")                           # cost API wins (talent reductions, downranks)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HL)
        self.assertEqual((seg.fillerCasts, seg.fillerManaSpent), (2, 1160))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 633)         # Lay on Hands: not a filler
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 424242)      # unknown spell
        self.assertEqual(seg.fillerCasts, 2)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.fillerManaSpent, 1160)

    def test_every_cast_with_a_cost_drains_the_pool(self):
        lua, addon, seg = start(PRIEST, 256)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # filler heal, table cost 380
        self.assertEqual((seg.manaSpent, seg.fillerManaSpent), (380, 380))
        lua.execute("STUB.spellCost[424242] = 120")                          # a shock or totem: not in the database
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 424242)
        self.assertEqual((seg.manaSpent, seg.fillerManaSpent), (500, 380))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", INNER_FOCUS)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # free cast: nothing spent
        self.assertEqual((seg.manaSpent, seg.fillerManaSpent), (500, 380))
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.manaSpent, 500)
        addon.inCombat = False
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # out of combat: ignored
        self.assertEqual(seg.manaSpent, 500)
        lua, addon, seg = start(LITANY, 257)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", RENEW)        # Litany 2/2: 10% of Renew's 410 comes back
        self.assertAlmostEqual(seg.manaSpent, 380 + 410 - 41)

    def test_mana_potion_adds_its_tooltip_average_to_mana_gained(self):
        # Seen in game 2026-11-11: a Minor Mana Potion is the player's cast 437, "Restores 140 to 180 mana."
        lua, addon, seg = start(SHAMAN, 264, extra=DESCS)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)
        self.assertEqual((seg.manaGained, seg.manaSpent), (160, 0))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", RUNE)         # same wording, 900 to 1500
        self.assertEqual(seg.manaGained, 1360)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", EARTH_SHOCK)  # a cast that restores nothing
        self.assertEqual(seg.manaGained, 1360)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(ttl.manaGained, 1360)
        addon.inCombat = False
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)       # out of combat: ignored
        self.assertEqual(seg.manaGained, 1360)

    def test_unreadable_potion_text_counts_nothing_and_is_reported_once(self):
        lua, addon, seg = start(SHAMAN, 264, extra='issecretvalue = function(v) return v == "SECRET" end; STUB.spellDesc[437] = "SECRET"')
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)
        self.assertEqual(seg.manaGained, 0)
        self.assertEqual(len([m for m in lua.globals().MSGS.values() if "437" in m]), 1)
        self.assertIn("spell 437 has no readable description", addon.hsw.db["global"].discoverLog[1])
        lua.execute('STUB.spellDesc[437] = "Restores 140 to 180 mana."')
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)       # readable now: counted
        self.assertEqual(seg.manaGained, 160)

    def test_casts_potions_and_crit_returns_move_the_mana_deficit(self):
        lua, addon, seg = start(PRIEST, 256, extra=DESCS)
        md = addon.ManaDeficit
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # 380
        lua.execute("STUB.spellCost[424242] = 120")
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 424242)       # a shock or totem
        self.assertEqual(md.deficit, 500)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)       # 160 back
        addon.StatParser.IncManaRestore(addon.StatParser, 40)                # a crit return
        self.assertEqual(md.deficit, 300)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", INNER_FOCUS)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # free cast: nothing spent
        self.assertEqual(md.deficit, 300)

    def test_between_pulls_casts_and_potions_move_the_deficit_but_not_the_segments(self):
        lua, addon, seg = start(PRIEST, 256, extra=DESCS)
        addon.inCombat = False
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # a heal between pulls
        self.assertEqual((addon.ManaDeficit.deficit, seg.manaSpent), (380, 0))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", POTION)
        self.assertEqual((addon.ManaDeficit.deficit, seg.manaGained), (220, 0))
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", EARTH_SHOCK)  # no cost known, restores nothing
        self.assertEqual(addon.ManaDeficit.deficit, 220)

    def test_a_drink_buff_sets_the_rate_and_combat_ends_it(self):
        lua, addon, seg = start(SHAMAN, 264, extra='STUB.spellDesc[430] = "Restores 420 mana over 21 sec."')
        addon.inCombat = False
        lua.execute("STUB.auras = { { id = 430 } }")
        fire(addon, "UNIT_AURA", "player")
        self.assertAlmostEqual(addon.ManaDeficit.drinkRate, 20)
        lua.execute("function HSW_TEST_ADDON:StartFight() end")              # DisplayPanel.lua is not loaded here
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)
        self.assertEqual(addon.ManaDeficit.drinkRate, 0)

    def test_a_mana_buff_is_seen_out_of_combat_and_kept_through_the_fight(self):
        # Blessing of Wisdom, seen in game 2026-11-12: 18 mana every 5 seconds, not in GetManaRegen()
        lua, addon, seg = start(SHAMAN, 264, extra='STUB.spellDesc[19850] = "Places a Blessing on the friendly target, restoring 18 mana every 5 seconds for 1 |4hour:hrs;."')
        addon.inCombat = False
        lua.execute("STUB.auras = { { id = 19850 } }")
        addon.hsw.PLAYER_ENTERING_WORLD(addon.hsw)                           # a /reload with the buff up
        self.assertAlmostEqual(addon.ManaDeficit.UnseenBuffRate(addon.ManaDeficit), 3.6)
        lua.execute("STUB.auras = {}")
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual(addon.ManaDeficit.UnseenBuffRate(addon.ManaDeficit), 0)
        lua.execute("STUB.auras = { { id = 19850 } }")
        fire(addon, "UNIT_AURA", "player")
        lua.execute("function HSW_TEST_ADDON:StartFight() end")              # DisplayPanel.lua is not loaded here
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)
        self.assertAlmostEqual(addon.ManaDeficit.UnseenBuffRate(addon.ManaDeficit), 3.6)   # a blessing does not end with the pull

    def test_mana_events_are_timed_and_other_powers_ignored(self):
        lua, addon, seg = start()
        lua.execute("STUB.time = 7")
        fire(addon, "UNIT_POWER_UPDATE", "player", "RAGE")
        self.assertIsNone(addon.ManaDeficit.lastPower)
        fire(addon, "UNIT_POWER_UPDATE", "player", "MANA")
        self.assertEqual(addon.ManaDeficit.lastPower, 7)

    def test_a_drink_in_the_clients_rates_is_counted_once_whenever_they_pick_it_up_or_let_it_go(self):
        # Seen in game: while seated GetManaRegen() carries the drink in both rates (2026-11-11: 13.63 / 6.81 read
        # 48.43 / 41.61), but not in step with the buff: a pull while seated left 64.93 / 57.36 behind (2026-11-13).
        drink = 835 / 24
        lua, addon, seg = start(SHAMAN, 264, extra='STUB.spellDesc[432] = "Restores 835 mana over 24 sec.  Must remain seated while drinking."'
                                                   '; STUB.regen = { base = 13.75, cast = 6.875 }')       # 60 Spirit: 6.25 + 60 / 8
        md = addon.ManaDeficit
        addon.inCombat = False
        md.Spend(md, 1000, 0)
        lua.execute("STUB.time = 10; STUB.auras = { { id = 432 } }")         # seated: the buff is up, the rates do not hold it yet
        fire(addon, "UNIT_AURA", "player")
        self.assertAlmostEqual(md.drinkRate, drink)
        self.assertAlmostEqual(addon.ply_regen_base, 13.75)
        seated = 1000 - 5 * 6.875 - 5 * 13.75
        lua.execute("STUB.time = 12; STUB.regen = { base = 13.75 + 835 / 24, cast = 6.875 + 835 / 24 }")
        fire(addon, "UNIT_POWER_UPDATE", "player", "MANA")                   # every mana tick re-reads the rates: now they hold it
        self.assertAlmostEqual(addon.ply_regen_base, 13.75)                  # Spirit regen alone, as before the drink
        self.assertAlmostEqual(addon.ply_castpct, 0.5)
        lua.execute("STUB.time = 20")
        fire(addon, "UNIT_POWER_UPDATE", "player", "MANA")
        at_pull = seated - 10 * (13.75 + drink)
        self.assertAlmostEqual(md.deficit, at_pull)                          # the drink once, not twice
        lua.execute("function HSW_TEST_ADDON:StartFight() self:UpdatePlayerStats() end")   # DisplayPanel.lua is not loaded here
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)                           # pulled while seated: the rates still carry the drink
        self.assertEqual(md.drinkRate, 0)
        self.assertAlmostEqual(addon.ply_regen_base, 13.75)
        self.assertAlmostEqual(addon.ply_castpct, 0.5)
        lua.execute("STUB.time = 30")
        fire(addon, "UNIT_POWER_UPDATE", "player", "MANA")
        self.assertAlmostEqual(md.deficit, at_pull - 10 * 13.75)             # and for the count the drink is over
        lua.execute("STUB.regen = { base = 13.75, cast = 6.875 }")
        fire(addon, "UNIT_POWER_UPDATE", "player", "MANA")                   # the rates let go of it
        self.assertEqual(md.endedDrink, 0)

    def test_regen_rates_change_after_the_deficit_is_brought_up_to_date(self):
        lua, addon, seg = start()                                            # stub regen: base 10, cast 3
        addon.inCombat = False
        addon.ManaDeficit.Spend(addon.ManaDeficit, 1000, 0)
        lua.execute("STUB.time = 10; STUB.regen = { base = 50, cast = 50 }")
        fire(addon, "UNIT_STATS", "player")
        self.assertAlmostEqual(addon.ManaDeficit.deficit, 1000 - 5 * 3 - 5 * 10)   # the 10 s ran at the old rates

    def test_earthfury_mana_return_comes_off_the_filler_cost(self):
        lua, addon, seg = start(SHAMAN, 264)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HW3)          # table cost 80, no set
        self.assertEqual(seg.fillerManaSpent, 80)
        lua.execute(EARTHFURY5 + "; HSW_TEST_ADDON.inCombat = false")
        addon.hsw.PLAYER_EQUIPMENT_CHANGED(addon.hsw)
        self.assertEqual(addon.ply_earthfury, 5)
        addon.inCombat = True
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HW3)          # 5 pieces: 25% chance of 35% of 80 back
        self.assertAlmostEqual(seg.fillerManaSpent, 80 + 80 - 7)
        lua.execute(f"STUB.spellCost[{HW3}] = 76")                            # Tidal Focus: the return is still 35% of the base cost
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", HW3)
        self.assertAlmostEqual(seg.fillerManaSpent, 153 + 76 - 7)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", CHAIN)        # Chain Heal: no return
        self.assertAlmostEqual(seg.fillerManaSpent, 222 + 405)

    def test_litany_of_light_returns_mana_when_the_previous_heal_was_another_spell(self):
        lua, addon, seg = start(LITANY, 257)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # first heal: nothing before it
        self.assertEqual(seg.fillerManaSpent, 380)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # same spell: no return
        self.assertEqual(seg.fillerManaSpent, 760)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", RENEW)        # 2/2: 10% of the 410 base cost back
        self.assertAlmostEqual(seg.fillerManaSpent, 760 + 410 - 41)
        lua.execute(f"STUB.spellCost[{FH6}] = 300")                          # Improved Healing: still 10% of the base cost
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH6)
        self.assertAlmostEqual(seg.fillerManaSpent, 1129 + 300 - 31.5)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # another rank of the same spell: no return
        self.assertAlmostEqual(seg.fillerManaSpent, 1397.5 + 380)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.fillerManaSpent, 1777.5)

    def test_litany_tracks_heals_cast_out_of_combat_and_needs_the_talent(self):
        lua, addon, seg = start(LITANY, 257)
        lua.execute("HSW_TEST_ADDON.inCombat = false")
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", RENEW)        # before the pull
        lua.execute("HSW_TEST_ADDON.inCombat = true")
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)           # previous heal was Renew
        self.assertAlmostEqual(seg.fillerManaSpent, 380 - 38)
        lua, addon, seg = start(PRIEST, 256)                                 # no Litany
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", RENEW)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)
        self.assertEqual(seg.fillerManaSpent, 790)

    def test_shield_cast_is_credited_at_cast_with_weakened_soul(self):
        lua, addon, seg = start(PRIEST, 256)
        cast(addon, PWS)
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)
        self.assertGreater(seg.t.heal, 0)
        self.assertTrue(addon.BuffTracker.TargetHas(addon.BuffTracker, "player", WEAKENED_SOUL))
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 500, 1)             # no expectation was opened for the shield
        self.assertEqual(seg.totalHealing, 928 + 0.10 * 200)
        self.assertEqual(len(list(seg.hits.keys())), 0)

    def test_self_cast_buffs_are_marked_and_inner_focus_consumed(self):
        lua, addon, seg = start(PRIEST, 256)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", INNER_FOCUS)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, INNER_FOCUS), 1)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)          # free cast: spends Inner Focus, no FSR
        self.assertIsNone(addon.lastManaSpend)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, INNER_FOCUS), 0)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)
        self.assertEqual(addon.lastManaSpend, 0)
        lua, addon, seg = start(SHAMAN, 264)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", WATER_SHIELD)
        self.assertEqual(addon.BuffTracker.Get(addon.BuffTracker, WATER_SHIELD), 3)   # three globes

    def test_water_shield_globes_spent_unseen_are_credited_when_the_buffs_read(self):
        # Seen in game 2026-11-13: "When a spell, melee, or ranged attack hits the caster or when one of the caster's
        # spells gets a critical result, 2% of maximum mana is restored to the caster, expending one water globe."
        lua, addon, seg = start(SHAMAN, 264)                                 # max mana 3000: a globe is 60
        bt, md = addon.BuffTracker, addon.ManaDeficit
        md.Spend(md, 1000, 0)
        lua.execute("STUB.auras = { { id = 408510, count = 3 } }")
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual((bt.Get(bt, WATER_SHIELD), md.deficit, seg.manaRestore), (3, 1000, 0))
        lua.execute("STUB.auras = { { id = 408510, count = 2 } }")          # a hit, or a shock's crit: one globe gone
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual((md.deficit, seg.manaRestore), (940, 60))           # in a fight it comes off the filler mana too
        addon.inCombat = False
        lua.execute("STUB.auras = { { id = 408510, count = 1 } }")          # one more between pulls, to a heal's crit
        fire(addon, "UNIT_AURA", "player")
        lua.execute("STUB.auras = {}")                                       # and the last one
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual((md.deficit, seg.manaRestore), (820, 60))
        lua.execute("STUB.auras = { { id = 408510, count = 3 } }")          # recast: nothing to credit
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual((bt.Get(bt, WATER_SHIELD), md.deficit), (3, 820))

    def test_a_water_shield_lost_with_globes_left_gives_no_mana(self):
        # Stockade 2026-11-12: `water shield -103` out of combat, three globes at once. A globe goes one at a time, each with
        # its own UNIT_AURA, so several gone at one look were spent unseen only if a fight came since the look before.
        lua, addon, seg = start(SHAMAN, 264)                                 # max mana 3000: a globe is 60
        lua.execute("function HSW_TEST_ADDON:StartFight() end")              # DisplayPanel.lua is not loaded here
        bt, md = addon.BuffTracker, addon.ManaDeficit
        addon.inCombat = False
        md.Spend(md, 1000, 0)
        lua.execute("STUB.auras = { { id = 408510, count = 3 } }")
        fire(addon, "UNIT_AURA", "player")
        lua.execute("STUB.auras = {}")                                       # taken off, run out, or a loading screen
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual((bt.Get(bt, WATER_SHIELD), md.deficit), (0, 1000))
        lua.execute("STUB.auras = { { id = 408510, count = 3 } }")
        fire(addon, "UNIT_AURA", "player")
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)                           # a fight: hits spend globes unseen
        lua.execute('READ_AURA = C_UnitAuras.GetAuraDataByIndex; C_UnitAuras.GetAuraDataByIndex = function() error("Auras cannot be accessed when secret") end')
        fire(addon, "UNIT_AURA", "player")                                   # unreadable in combat: still owed
        self.assertEqual(md.deficit, 1000)
        lua.execute("C_UnitAuras.GetAuraDataByIndex = READ_AURA; STUB.auras = { { id = 408510, count = 1 } }")
        fire(addon, "UNIT_AURA", "player")                                   # first look after it: two went
        self.assertEqual((bt.Get(bt, WATER_SHIELD), md.deficit), (1, 880))
        lua.execute("STUB.auras = { { id = 408510, count = 3 } }")
        fire(addon, "UNIT_AURA", "player")
        lua.execute("STUB.auras = {}")                                       # no fight since that look
        fire(addon, "UNIT_AURA", "player")
        self.assertEqual(md.deficit, 880)

    def test_recasting_water_shield_in_combat_credits_no_mana(self):
        # Stockade 2026-11-12: the shield is refreshed with globes left (3 charges and a fresh 10 m on the screenshot after
        # each recast), and the bar gained nothing: counting the old globes as spent put the count 73 and 109 under the bar.
        lua, addon, seg = start(SHAMAN, 264)
        bt, md = addon.BuffTracker, addon.ManaDeficit
        md.Spend(md, 1000, 0)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", WATER_SHIELD)
        self.assertEqual((bt.Get(bt, WATER_SHIELD), seg.manaRestore), (3, 0))
        bt.UseCharge(bt, WATER_SHIELD)                                       # a heal crit took one and was credited then
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", WATER_SHIELD)   # the other two are replaced, not spent
        self.assertEqual((bt.Get(bt, WATER_SHIELD), seg.manaRestore, md.deficit), (3, 0, 1000))

    def test_casts_and_heals_are_logged_on_the_live_segment(self):
        lua, addon, seg = start(extra=PARTY)
        cast(addon, HL, "Bob")                                               # table cost 660, t = 0
        lua.execute("STUB.time = 2.5")
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "CRITICAL", 1500, 2.5)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 633)          # Lay on Hands: no cost, still a cast
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", 424242)      # unknown spell: not logged
        rows = list(seg.events.values())
        self.assertEqual(rows, ["0.00,cast,25292,Holy Light,Bob,,,660",
                                "2.50,heal,25292,Holy Light,Bob,,1,",
                                "2.50,cast,633,Lay on Hands,Me,,,0"])
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertEqual(len(list(ttl.events.values())), 0)                 # the Total segment keeps no log

    def test_free_cast_is_logged_at_zero_mana(self):
        lua, addon, seg = start(PRIEST, 256)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", INNER_FOCUS)
        fire(addon, "UNIT_SPELLCAST_SUCCEEDED", "player", "g", FH)
        rows = list(seg.events.values())                                     # Inner Focus is not a healing spell: one row
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].endswith(",Flash Heal,Me,,,0"), rows)

    def test_failed_cast_opens_no_heal(self):
        lua, addon, seg = start()
        fire(addon, "UNIT_SPELLCAST_SENT", "player", "", "g", HL)
        fire(addon, "UNIT_SPELLCAST_FAILED", "player", "g", HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 1000, 2)
        self.assertEqual(len(list(seg.hits.keys())), 0)

    def test_ignored_out_of_combat(self):
        lua, addon, seg = start()
        addon.inCombat = False
        cast(addon, HL)
        fire(addon, "UNIT_COMBAT", "player", "HEAL", "", 1000, 2)
        self.assertEqual(len(list(seg.hits.keys())), 0)


class FiveSecondRule(unittest.TestCase):
    def test_mana_cast_starts_fsr_and_accumulates(self):
        lua, addon, seg = start()
        self.assertIsNone(addon.lastManaSpend)
        addon.OnPlayerSpellcast(addon, HL)                       # t=0, table cost 660
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.time = 8")
        addon.OnPlayerSpellcast(addon, HL)
        self.assertEqual(addon.lastManaSpend, 8)
        self.assertAlmostEqual(seg.timeInFSR, 5)
        self.assertAlmostEqual(seg.timeOutsideFSR, 3)
        ttl = addon.SegmentManager.Get(addon.SegmentManager, "Total")
        self.assertAlmostEqual(ttl.timeInFSR, 5)

    def test_free_casts_and_unknown_costs_do_not(self):
        lua, addon, seg = start()
        addon.OnPlayerSpellcast(addon, 633)                      # Lay on Hands: no mana cost
        addon.OnPlayerSpellcast(addon, 424242)                   # unknown spell, no cost API
        self.assertIsNone(addon.lastManaSpend)
        lua.execute("STUB.spellCost[424242] = 10")
        addon.OnPlayerSpellcast(addon, 424242)                   # unknown spell but the client says it costs mana
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.time = 3; STUB.auras = { {id=14751} }; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs()")
        addon.OnPlayerSpellcast(addon, HL)                       # Inner Focus up: free cast
        self.assertEqual(addon.lastManaSpend, 0)
        lua.execute("STUB.auras = {}; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs(); STUB.spellCost[%d] = 0" % HL)
        addon.OnPlayerSpellcast(addon, HL)                       # client reports 0 cost (e.g. Clearcasting consumed)
        self.assertEqual(addon.lastManaSpend, 0)
        addon.inCombat = False
        lua.execute("STUB.spellCost[%d] = nil" % HL)
        addon.OnPlayerSpellcast(addon, HL)                       # out of combat: ignored
        self.assertEqual(addon.lastManaSpend, 0)


class Handlers(unittest.TestCase):
    def test_entering_world_and_talent_change_rebuild_state(self):
        lua, addon, _ = start()
        lua.execute("STUB.talents[1].talents[1].rank = 3")
        addon.inBossFight = True
        addon.hsw.PLAYER_ENTERING_WORLD(addon.hsw)
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 3)
        self.assertFalse(addon.inBossFight)                                  # zoned out mid-encounter: no ENCOUNTER_END came
        lua.execute("STUB.talents[1].talents[1].rank = 1; HSW_TEST_ADDON.hsw.db.global.intPerCritOverride.PALADIN = 50")
        addon.hsw.CHARACTER_POINTS_CHANGED(addon.hsw)
        self.assertEqual((addon.GetTalentRank(addon, "Illumination"), addon.IntPerCrit), (1, 50))
        addon.hsw.PLAYER_TALENT_UPDATE(addon.hsw)
        lua.execute("STUB.talents[1].talents[1].rank = 2")
        addon.hsw.TRAIT_TREE_CURRENCY_INFO_UPDATED(addon.hsw, "TRAIT_TREE_CURRENCY_INFO_UPDATED", 1082)   # the event Forever fires on a point spend
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 2)
        addon.hsw.PLAYER_EQUIPMENT_CHANGED(addon.hsw)
        addon.hsw.COMBAT_RATING_UPDATE(addon.hsw)
        self.assertEqual(addon.ply_sp, 200)

    def test_combat_log_handler_is_gone(self):
        _, addon, _ = start()
        self.assertIsNone(addon.hsw.COMBAT_LOG_EVENT_UNFILTERED)     # registering it is a blocked action on Forever

    def test_unit_aura_credits_fsr_time_at_the_old_casting_share(self):
        lua, addon, seg = start()                                    # casting share 3/10
        lua.execute("STUB.time = 4; STUB.regen = { base = 10, cast = 10 }")     # Innervate lands
        fire(addon, "UNIT_AURA", "player")
        self.assertAlmostEqual(seg.castPctWeighted, 0.3 * 4)         # 0..4 at the share in force then
        self.assertAlmostEqual(addon.ply_castpct, 1.0)
        lua.execute("STUB.time = 6")
        fire(addon, "UNIT_STATS", "player")
        self.assertAlmostEqual(seg.castPctWeighted, 0.3 * 4 + 1.0 * 2)

    def test_roster_change_in_combat_recaches_the_group(self):
        lua, addon, seg = start()
        lua.execute(PARTY)                                           # Bob joins mid-fight
        cast(addon, HL, "Bob")
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 2)
        self.assertEqual(len(list(seg.hits.keys())), 0)              # Bob's GUID is not cached yet
        addon.hsw.GROUP_ROSTER_UPDATE(addon.hsw)
        lua.execute("STUB.time = 10")
        cast(addon, HL, "Bob")
        fire(addon, "UNIT_COMBAT", "party1", "HEAL", "", 1000, 12)
        self.assertEqual(seg.hits[HL].targets.Bob, 1)

    def test_re_entering_combat_cancels_the_poll(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("function HSW_TEST_ADDON:EndFight() self.inCombat = false end; function HSW_TEST_ADDON:StartFight() end; STUB.combat.party1 = true")
        addon.hsw.PLAYER_REGEN_ENABLED(addon.hsw)
        self.assertEqual(len(list(lua.globals().STUB.tickers.keys())), 1)
        addon.hsw.PLAYER_REGEN_DISABLED(addon.hsw)
        self.assertEqual(len(list(lua.globals().STUB.tickers.keys())), 0)
        self.assertTrue(addon.inCombat)


class OathOfLight(unittest.TestCase):
    OATH = 1328548

    def test_oath_marks_its_target_in_or_out_of_combat_one_at_a_time(self):
        lua, addon, seg = start(extra=PARTY)
        lua.execute("HSW_TEST_ADDON.inCombat = false")                # sworn before the pull, as a 5 min buff is
        cast(addon, self.OATH, "Bob Builder")
        self.assertTrue(addon.BuffTracker.TargetHas(addon.BuffTracker, "party1", self.OATH))
        self.assertEqual(seg.fillerManaSpent, 0)                       # no expectation, no filler: out of combat
        lua.execute("HSW_TEST_ADDON.inCombat = true")
        cast(addon, self.OATH)                                         # sworn on the player: Bob loses it
        self.assertFalse(addon.BuffTracker.TargetHas(addon.BuffTracker, "party1", self.OATH))
        self.assertTrue(addon.BuffTracker.TargetHas(addon.BuffTracker, "player", self.OATH))
        lua.execute("STUB.time = 301")
        self.assertFalse(addon.BuffTracker.TargetHas(addon.BuffTracker, "player", self.OATH))
