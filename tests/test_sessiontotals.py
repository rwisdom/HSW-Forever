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

    def test_a_missing_session_in_range_contributes_nothing(self):
        _, _, st = start(SESSIONS)
        self.assertEqual(totals(st.Read(0, 5)), {HW1: 200, HW3: 300})     # ids 4 and 5 do not exist
