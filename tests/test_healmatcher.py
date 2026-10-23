import unittest
from harness import load, CORE_FILES

HL = 25292       # Holy Light R9: direct, 2.5 s cast
HS = 20930       # Holy Shock R4: instant direct
REJUV = 25299    # Rejuvenation R11: HoT, 3 s ticks over 12 s
REGROWTH = 9858  # Regrowth R9: direct + HoT (2 s cast, 3 s ticks over 21 s)
CHAIN = 10623    # Chain Heal R3: 3 targets
HST = 5394       # Healing Stream Totem R1
WG = 408120      # Wild Growth R1: party HoT, 1 s ticks over 7 s
PWS = 10901      # Power Word: Shield R10: absorb, never a UNIT_COMBAT heal
HW = 547         # Healing Wave R3: base 138, 2.5 s cast; Earthfury jumps to two more units at 20% each
LHW = 8008       # Lesser Healing Wave R2: no jumps

PARTY = 'STUB.group = "party"; STUB.groupSize = 2; STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"; STUB.guids.party2 = "Player-3"; STUB.names.party2 = "Cat"'
SELF_TWICE = 'STUB.guids.targettarget = "Player-1"; STUB.names.targettarget = "Me"'   # the player seen through a second token


def start(setup=""):
    """In combat with the group cached; DecompHealingForCurrentSpec is replaced by a recorder."""
    lua, addon = load(CORE_FILES, setup=setup)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.UnitManager:Cache(); a.inCombat = true
        HEALS = {}
        function a.StatParser:DecompHealingForCurrentSpec(ev, guid, spellID, crit, amount, over)
            table.insert(HEALS, { ev = ev, guid = guid, spellID = spellID, crit = crit, amount = amount })
        end
    """)
    return lua, addon, addon.HealMatcher


def heals(lua):
    H = lua.globals().HEALS
    return [(H[i].ev, H[i].guid, H[i].spellID, H[i].crit, H[i].amount) for i in range(1, len(H) + 1)]


class DirectHeals(unittest.TestCase):
    def test_cast_on_self_matches_next_heal_and_dedupes_tokens(self):
        lua, addon, hm = start(SELF_TWICE)
        hm.OnCastSent(hm, HL, "", 0)                                   # "" target = self
        hm.OnCastSucceeded(hm, HL, 2.5)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 2.5)
        hm.OnUnitCombat(hm, "targettarget", "HEAL", "", 1000, 2.5)     # same heal, second token
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-1", HL, False, 1000)])

    def test_crit_flag_and_named_target(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, HS, "Bob", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0)              # someone else's heal on us
        hm.OnUnitCombat(hm, "party1", "HEAL", "CRITICAL", 900, 0.1)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-2", HS, True, 900)])

    def test_sent_target_with_suffix_matches_bare_unit_name(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, HL, "Me Bam", 0)                             # Forever: "Hop Bam" for the player "Hop"
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 2.5)
        hm.OnCastSent(hm, HS, "Bob-Realm", 3)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 500, 3.1)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-1", HL, False, 1000), ("SPELL_HEAL", "Player-2", HS, False, 500)])
        self.assertEqual(hm.SentTarget(hm, HS), "Bob")

    def test_repeated_interrupt_drops_only_that_cast(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, HS, "Bob", 0, "cast-A")
        hm.OnCastSent(hm, HS, "Cat", 0, "cast-B")
        for _ in range(4):                                             # Forever fires INTERRUPTED several times per cast
            hm.OnCastFailed(hm, HS, "cast-B")
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 500, 0.1)            # Cat: the interrupted cast, not ours
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 500, 0.1)            # Bob: still expected
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-2", HS, False, 500)])

    def test_expectation_expires_after_cast_time_plus_window(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HL, "", 0)                                   # 2.5 s cast: landing window closes at 3.5
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 3.6)
        self.assertEqual(heals(lua), [])

    def test_queued_cast_does_not_steal_the_landing_heal(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HL, "", 0)
        hm.OnCastSent(hm, HL, "", 2.4)                                 # queued before the first lands
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 2.5)
        hm.OnCastSent(hm, HL, "", 4.9)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 5.0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 7.5)           # last of the chain
        self.assertEqual(len(heals(lua)), 3)

    def test_instant_sent_during_a_cast_lands_first(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HL, "", 0)
        hm.OnCastSent(hm, HS, "", 1)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 1)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 2.5)
        self.assertEqual([h[2] for h in heals(lua)], [HS, HL])

    def test_a_small_tick_on_the_target_does_not_take_the_expectation(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, HL, "Bob", 0)                                # Holy Light R9: base 2000ish
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 12, 1.3)             # someone's HoT tick on Bob
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 2500, 2.5)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-2", HL, False, 2500)])

    def test_a_weak_heal_above_a_third_of_base_still_matches(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, HL, "Bob", 0)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 900, 2.5)            # halved by a healing debuff
        self.assertEqual([h[4] for h in heals(lua)], [900])

    def test_chain_heal_bounces_skip_the_band(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, CHAIN, "Bob", 0)
        for token, amount in (("party1", 500), ("party2", 250), ("player", 125)):
            hm.OnUnitCombat(hm, token, "HEAL", "", amount, 2.5)
        self.assertEqual([h[4] for h in heals(lua)], [500, 250, 125])

    def test_failed_cast_drops_expectation(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HS, "", 0)
        hm.OnCastFailed(hm, HS)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [])

    def test_multi_target_spell_lands_on_any_unit(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, CHAIN, "Bob", 0)
        hm.OnCastSucceeded(hm, CHAIN, 2.5)
        for token, amount in (("party1", 800), ("party2", 400), ("player", 200), ("party1", 100)):
            hm.OnUnitCombat(hm, token, "HEAL", "", amount, 2.5)
        self.assertEqual([h[2] for h in heals(lua)], [CHAIN, CHAIN, CHAIN])   # three bounces; the fourth heal is not ours

    def test_absorb_casts_and_unknown_spells_open_nothing(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, PWS, "", 0)
        hm.OnCastSent(hm, 424242, "", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [])
        self.assertEqual(hm.SentTarget(hm, PWS), "Me")                 # the shield's target is still remembered

    def test_unattributed_heal_does_not_block_a_later_identical_one(self):
        lua, addon, hm = start(PARTY)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 1000, 0)             # not ours: nothing cast on Bob yet
        hm.OnCastSent(hm, HS, "Bob", 0)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 1000, 0)             # same unit, amount and frame, but now ours
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-2", HS, False, 1000)])


def start8(setup=""):
    """start() with eight Earthfury pieces worn: Healing Wave jumps to two more units."""
    lua, addon, hm = start(setup)
    addon.ply_earthfury = 8
    return lua, addon, hm


class EarthfuryJumps(unittest.TestCase):
    """Earthfury Healing Wave jumps land on other units in the frame of the main heal, before or after it in event order."""

    def test_jumps_after_the_main_heal_are_ours(self):
        lua, addon, hm = start8(PARTY)
        hm.OnCastSent(hm, HW, "Bob", 0)
        for token, amount in (("party1", 230), ("party2", 46), ("player", 9)):
            hm.OnUnitCombat(hm, token, "HEAL", "", amount, 2)
        self.assertEqual([(h[1], h[2], h[4]) for h in heals(lua)], [("Player-2", HW, 230), ("Player-3", HW, 46), ("Player-1", HW, 9)])

    def test_jumps_before_the_main_heal_are_held_until_it_lands(self):
        lua, addon, hm = start8(PARTY)
        hm.OnCastSent(hm, HW, "Bob", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 9, 2)
        hm.OnUnitCombat(hm, "party2", "HEAL", "CRITICAL", 54, 2)
        self.assertEqual(heals(lua), [])
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 230, 2)
        self.assertEqual(sorted((h[4], h[3]) for h in heals(lua)), [(9, False), (54, True), (230, False)])

    def test_only_two_jumps_and_only_in_the_landing_frame(self):
        lua, addon, hm = start8(PARTY)
        hm.OnCastSent(hm, HW, "Bob", 0)
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 20, 1)        # a frame earlier: someone's tick
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 230, 2)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 9, 2)
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 46, 2)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 5, 2)         # a third heal in the frame
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 40, 2.1)      # the frame after
        self.assertEqual([h[4] for h in heals(lua)], [230, 9, 46])

    def test_a_held_heal_arrives_once_per_token(self):
        lua, addon, hm = start8(PARTY + "; " + SELF_TWICE)
        hm.OnCastSent(hm, HW, "Bob", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 9, 2)
        hm.OnUnitCombat(hm, "targettarget", "HEAL", "", 9, 2)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 230, 2)
        self.assertEqual([h[4] for h in heals(lua)], [230, 9])

    def test_held_heals_from_another_frame_are_reported_as_unattributed(self):
        lua, addon, hm = start8(PARTY)
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        hm.OnCastSent(hm, HW, "Bob", 0)
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 20, 1)
        self.assertEqual(len(list(lua.globals().MSGS.keys())), 0)   # held: the landing frame is not known yet
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 230, 2)
        self.assertEqual([h[4] for h in heals(lua)], [230])
        self.assertIn("20", lua.globals().MSGS[1])

    def test_lesser_healing_wave_does_not_jump(self):
        lua, addon, hm = start8(PARTY)
        hm.OnCastSent(hm, LHW, "Bob", 0)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 250, 1.5)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 9, 1.5)
        self.assertEqual([h[4] for h in heals(lua)], [250])

    def test_no_jumps_below_eight_pieces(self):
        lua, addon, hm = start(PARTY)
        addon.ply_earthfury = 7
        hm.OnCastSent(hm, HW, "Bob", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 9, 2)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 230, 2)
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 46, 2)
        self.assertEqual([h[4] for h in heals(lua)], [230])


SECRET = 'issecretvalue = function(v) return v == "SECRET" end'   # the stub's stand-in for a secret string


class SecretValues(unittest.TestCase):
    """In a dungeon the client hands secret strings for the cast target and for units reached through a hostile one."""

    def test_secret_cast_target_falls_back_to_the_selected_group_member(self):
        lua, addon, hm = start(PARTY + "; " + SECRET + '; STUB.guids.target = "Player-2"; STUB.names.target = "Bob"')
        hm.OnCastSent(hm, HS, "SECRET", 0)
        hm.OnUnitCombat(hm, "party1", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-2", HS, False, 500)])
        self.assertEqual(hm.SentTarget(hm, HS), "Bob")

    def test_secret_cast_target_without_a_friendly_target_means_self(self):
        lua, addon, hm = start(PARTY + "; " + SECRET + '; STUB.guids.target = "SECRET"; STUB.names.target = "SECRET"')   # hostile target
        hm.OnCastSent(hm, HS, "SECRET", 0)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-1", HS, False, 500)])

    def test_heal_on_a_secret_unit_is_dropped(self):
        # the player seen through the hostile target's target: secret GUID and name; the "player" token delivers the same heal
        lua, addon, hm = start(SECRET + '; STUB.guids.targettarget = "SECRET"; STUB.names.targettarget = "SECRET"')
        hm.OnCastSent(hm, HS, "", 0)
        hm.OnUnitCombat(hm, "targettarget", "HEAL", "", 500, 0.1)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [("SPELL_HEAL", "Player-1", HS, False, 500)])


class PeriodicHeals(unittest.TestCase):
    def test_hot_ticks_until_duration_ends(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, REJUV, "", 0)
        hm.OnCastSucceeded(hm, REJUV, 0)
        for t in (3, 6, 9, 12):
            hm.OnUnitCombat(hm, "player", "HEAL", "", 194, t)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 194, 16)             # past 12 s + one tick of grace: not ours
        self.assertEqual([(h[0], h[2]) for h in heals(lua)], [("SPELL_PERIODIC_HEAL", REJUV)] * 4)

    def test_direct_part_then_ticks(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, REGROWTH, "", 0)
        hm.OnCastSucceeded(hm, REGROWTH, 2)
        hm.OnUnitCombat(hm, "player", "HEAL", "CRITICAL", 1500, 2)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 142, 5)
        self.assertEqual([(h[0], h[2], h[3]) for h in heals(lua)],
                         [("SPELL_HEAL", REGROWTH, True), ("SPELL_PERIODIC_HEAL", REGROWTH, False)])

    def test_party_hot_registers_on_every_member(self):
        lua, addon, hm = start(PARTY)
        hm.OnCastSent(hm, WG, "Bob", 0)
        hm.OnCastSucceeded(hm, WG, 0)
        hm.OnUnitCombat(hm, "party2", "HEAL", "", 48, 1)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 48, 1)
        self.assertEqual([h[1] for h in heals(lua)], ["Player-3", "Player-1"])

    def test_totem_explains_leftover_heals_while_down(self):
        lua, addon, hm = start()
        hm.OnUnitCombat(hm, "player", "HEAL", "", 5, 1)                # no totem yet
        hm.OnCastSent(hm, HST, "", 2)
        hm.OnCastSucceeded(hm, HST, 2)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 5, 4)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 5, 400)              # totem long gone
        self.assertEqual(heals(lua), [("SPELL_PERIODIC_HEAL", "Player-1", HST, False, 5)])


class Housekeeping(unittest.TestCase):
    def test_reset_and_out_of_combat(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HS, "", 0)
        hm.Reset(hm)
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 0.1)
        self.assertEqual(heals(lua), [])
        hm.OnCastSent(hm, HS, "", 1)
        addon.inCombat = False
        hm.OnUnitCombat(hm, "player", "HEAL", "", 500, 1.1)
        self.assertEqual(heals(lua), [])

    def test_unattributed_heal_reported_in_discovery_mode(self):
        lua, addon, hm = start()
        lua.execute('MSGS = {}; function HSW_TEST_ADDON:Msg(s) table.insert(MSGS, tostring(s)) end; HSW_TEST_ADDON.discoverSpells = true')
        hm.OnUnitCombat(hm, "player", "HEAL", "", 777, 1)
        self.assertEqual(len(list(lua.globals().MSGS.keys())), 1)
        self.assertIn("777", lua.globals().MSGS[1])
