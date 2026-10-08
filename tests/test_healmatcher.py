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

    def test_expectation_expires_after_cast_time_plus_window(self):
        lua, addon, hm = start()
        hm.OnCastSent(hm, HL, "", 0)                                   # 2.5 s cast: landing window closes at 3.5
        hm.OnUnitCombat(hm, "player", "HEAL", "", 1000, 3.6)
        self.assertEqual(heals(lua), [])

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
