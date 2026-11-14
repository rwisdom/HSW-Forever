import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/SessionTotals.lua"]
HW1, HW3 = 331, 547

SESSIONS = """STUB.sessions = {
    { sessionID = 1, name = "Forest Spider", durationSeconds = 7, heals = { ["Player-1"] = { [331] = 120 } } },
    { sessionID = 2, name = "Mangy Wolf", durationSeconds = 14, heals = { ["Player-1"] = { [331] = 80, [547] = 300 }, ["Player-2"] = { [331] = 999 } } },
    { sessionID = 3, name = "Mangy Wolf", durationSeconds = 7 },
}"""


def start(setup=""):
    lua, addon = load(FILES, setup=setup)
    return lua, addon, addon.SessionTotals


def totals(t):
    return {int(k): v for k, v in t.items()} if t is not None else None


class Newest(unittest.TestCase):
    def test_no_sessions_and_no_api(self):
        _, _, st = start()
        self.assertEqual(st.Newest(), 0)
        _, _, st = start("C_DamageMeter = nil")
        self.assertEqual(st.Newest(), 0)

    def test_highest_id_and_nil_while_secret(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(st.Newest(), 3)
        _, _, st = start(SESSIONS + "; STUB.secret = true")
        self.assertIsNone(st.Newest())                                     # unreadable, not "none"


class Advance(unittest.TestCase):
    def test_an_out_of_combat_reading_follows_the_meter_down_after_a_reset(self):
        # Deadmines 2026-11-10: the meter restarted its ids below the open-world watermark (10 -> 7)
        # and every fight read an empty range until the ids passed it again.
        lua, _, st = start(SESSIONS)
        st.Advance()
        self.assertEqual(st.watermark, 3)
        lua.execute('STUB.sessions = { { sessionID = 1, name = "Defias Miner" } }')
        st.Advance()
        self.assertEqual(st.watermark, 1)

    def test_a_given_id_only_raises_and_a_secret_list_changes_nothing(self):
        lua, _, st = start(SESSIONS)
        st.Advance(5)
        self.assertEqual(st.watermark, 5)
        st.Advance(2)                                                      # a fight priced late: not a reset
        self.assertEqual(st.watermark, 5)
        lua.execute("STUB.secret = true")
        st.Advance()
        self.assertEqual(st.watermark, 5)

    def test_restart_lowers_the_watermark_and_advance_raises_it_from_there(self):
        # a fight priced below its start: the meter restarted its ids since the watermark was read
        _, _, st = start(SESSIONS)
        st.Advance(10)
        st.Restart(0)
        self.assertEqual(st.watermark, 0)
        st.Advance(2)
        self.assertEqual(st.watermark, 2)


class Name(unittest.TestCase):
    def test_longest_session_in_range_names_the_fight(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(st.Name(0, 3), "Mangy Wolf")                      # 14 s beats 7 s
        self.assertEqual(st.Name(0, 1), "Forest Spider")
        self.assertEqual(st.Name(2, 3), "Mangy Wolf")
        self.assertIsNone(st.Name(3, 3))                                   # empty range
        self.assertIsNone(st.Name(3, 9))                                   # no such sessions

    def test_nil_while_secret_or_without_the_api(self):
        _, _, st = start(SESSIONS + "; STUB.secret = true")
        self.assertIsNone(st.Name(0, 3))
        _, _, st = start("C_DamageMeter = nil")
        self.assertIsNone(st.Name(0, 3))


class Recent(unittest.TestCase):
    """The meter's last sessions as text, for the discover log."""

    def test_last_sessions_with_id_name_and_duration(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(st.Recent(2), "2 Mangy Wolf 14s, 3 Mangy Wolf 7s")
        self.assertEqual(st.Recent(5), "1 Forest Spider 7s, 2 Mangy Wolf 14s, 3 Mangy Wolf 7s")

    def test_a_value_that_is_secret_or_missing_reads_as_a_question_mark(self):
        _, _, st = start(SESSIONS + "; STUB.secret = true")
        self.assertEqual(st.Recent(1), "? Mangy Wolf ?s")

    def test_none_without_sessions_or_the_api_and_unreadable_when_the_list_throws(self):
        _, _, st = start()
        self.assertEqual(st.Recent(5), "none")
        _, _, st = start("C_DamageMeter = nil")
        self.assertEqual(st.Recent(5), "none")
        _, _, st = start('C_DamageMeter.GetAvailableCombatSessions = function() error("secret") end')
        self.assertEqual(st.Recent(5), "unreadable")


class Read(unittest.TestCase):
    def test_sums_the_players_spells_over_the_range(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(totals(st.Read(0, 2)), {HW1: 200, HW3: 300})     # Player-2's 999 is not ours
        self.assertEqual(totals(st.Read(1, 2)), {HW1: 80, HW3: 300})
        self.assertEqual(totals(st.Read(2, 3)), {})                        # a session with no healing by us
        self.assertEqual(totals(st.Read(3, 3)), {})                        # empty range

    def test_nil_while_secret_or_without_the_api(self):
        _, _, st = start(SESSIONS + "; STUB.secret = true")
        self.assertIsNone(st.Read(0, 2))
        _, _, st = start("C_DamageMeter = nil")
        self.assertIsNone(st.Read(0, 1))

    def test_a_session_read_before_gives_only_what_it_gained_since(self):
        # Blackfathom Deeps 2026-11-13: the meter kept a session open across a short gap between pulls
        # (same id, longer duration). The first fight read it, the second fight's healing landed in it
        # and the second fight read an empty range: nine fights with hits priced nothing.
        lua, _, st = start(SESSIONS)
        self.assertEqual(totals(st.Read(0, 2)), {HW1: 200, HW3: 300})
        lua.execute('STUB.sessions[2].heals["Player-1"] = { [331] = 130, [547] = 300, [8004] = 60 }')   # the next pull lands in session 2
        self.assertEqual(totals(st.Read(2, 2)), {HW1: 50, 8004: 60})
        self.assertEqual(totals(st.Read(2, 2)), {})                        # taken once
        lua.execute('STUB.sessions[2].heals["Player-1"][331] = 150; STUB.sessions[3].heals = { ["Player-1"] = { [331] = 40 } }')
        self.assertEqual(totals(st.Read(2, 3)), {HW1: 60})                 # the rest of session 2 and all of session 3

    def test_a_session_this_addon_never_read_gives_nothing_as_a_start(self):
        # the start of a range is a session seen out of combat (an untracked fight): none of it is ours
        lua, _, st = start(SESSIONS)
        self.assertEqual(totals(st.Read(2, 2)), {})
        lua.execute('STUB.sessions[2].heals["Player-1"][331] = 100')
        self.assertEqual(totals(st.Read(2, 2)), {HW1: 20})                 # read once, it is followed from there

    def test_what_was_read_is_forgotten_when_untracked_combat_moves_the_meter_on(self):
        # the meter restarts its ids and untracked fights bring them back to the id last read: that
        # session is another fight's, and the old amounts say nothing about it
        lua, _, st = start(SESSIONS)
        st.Read(0, 2)
        lua.execute('STUB.sessions = { { sessionID = 1, name = "Boar" } }')
        st.Advance()
        lua.execute('STUB.sessions[2] = { sessionID = 2, name = "Boar", heals = { ["Player-1"] = { [331] = 500 } } }')
        st.Advance()
        self.assertEqual(totals(st.Read(2, 2)), {})                        # not 500 less the 80 read before the restart

    def test_secret_totals_take_nothing(self):
        lua, _, st = start(SESSIONS)
        st.Read(0, 2)
        lua.execute('STUB.sessions[2].heals["Player-1"][331] = 130; STUB.secret = true')
        self.assertIsNone(st.Read(2, 2))
        lua.execute("STUB.secret = false")
        self.assertEqual(totals(st.Read(2, 2)), {HW1: 50})

    def test_a_missing_session_in_range_contributes_nothing(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(totals(st.Read(0, 5)), {HW1: 200, HW3: 300})     # ids 4 and 5 do not exist
