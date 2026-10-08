import unittest
from harness import load, CORE_FILES


class BuffTrackerTests(unittest.TestCase):
    def setUp(self):
        self.lua, self.addon = load(CORE_FILES)
        self.bt = self.addon.BuffTracker

    def auras(self, lua_list):
        self.lua.execute(f"STUB.auras = {{ {lua_list} }}; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs()")

    def test_stacks_apply_and_expire_with_callbacks(self):
        self.lua.execute("""
            CALLS = {}
            HSW_TEST_ADDON.BuffTracker:Track(408510,
                function(c, old) table.insert(CALLS, "apply:" .. c .. ":" .. old) end,
                function(c, old) table.insert(CALLS, "expire:" .. c .. ":" .. old) end)
        """)
        self.assertEqual(self.bt.Get(self.bt, 408510), 0)
        self.auras("{id=408510, count=3}")
        self.assertEqual(self.bt.Get(self.bt, 408510), 3)
        self.auras("{id=408510, count=2}")
        self.assertEqual(self.bt.Get(self.bt, 408510), 2)
        self.auras("{id=99}")
        self.assertEqual(self.bt.Get(self.bt, 408510), 0)
        calls = self.lua.globals().CALLS
        self.assertEqual([calls[i] for i in range(1, 4)], ["apply:3:0", "expire:2:3", "expire:0:2"])

    def test_count_zero_is_one_stack_and_expiry_is_honoured(self):
        self.auras("{id=14751, count=0, expiration=5}")      # Inner Focus is tracked by Spells_Manual
        self.assertEqual(self.bt.Get(self.bt, 14751), 1)
        self.lua.execute("STUB.time = 6")
        self.assertEqual(self.bt.Get(self.bt, 14751), 0)      # expired by time even without a UNIT_AURA

    def test_untracked_auras_ignored(self):
        self.auras("{id=12345, count=4}")
        self.assertEqual(self.bt.Get(self.bt, 12345), 0)

    def test_marks_from_own_casts_and_target_marks(self):
        self.bt.MarkCast(self.bt, 14751, 60)                            # Inner Focus cast: up until spent
        self.assertEqual(self.bt.Get(self.bt, 14751), 1)
        self.bt.Consume(self.bt, 14751)
        self.assertEqual(self.bt.Get(self.bt, 14751), 0)
        self.bt.MarkCast(self.bt, 408510, 600)                          # Water Shield cast
        self.assertEqual(self.bt.Get(self.bt, 408510), 1)
        self.lua.execute("STUB.time = 601")
        self.assertEqual(self.bt.Get(self.bt, 408510), 0)               # expired by time
        self.bt.MarkTarget(self.bt, "Me", 6788, 15)                     # Weakened Soul on the unit named Me
        self.assertTrue(self.bt.TargetHas(self.bt, "player", 6788))     # UnitName("player") == "Me" in the stub
        self.assertFalse(self.bt.TargetHas(self.bt, "target", 6788))    # no such unit
        self.lua.execute("STUB.time = 617")
        self.assertFalse(self.bt.TargetHas(self.bt, "player", 6788))
        self.bt.MarkCast(self.bt, 12345, 10)                            # untracked buff: ignored
        self.assertEqual(self.bt.Get(self.bt, 12345), 0)


class CastTrackerTests(unittest.TestCase):
    def setUp(self):
        self.lua, self.addon = load(CORE_FILES)
        self.lua.execute('HSW_TEST_ADDON.inCombat = true; HSW_TEST_ADDON.ply_hst = 0.1; HSW_TEST_ADDON.SegmentManager:Enqueue("fight")')
        self.seg = self.addon.SegmentManager.Get(self.addon.SegmentManager, 0)
        self.ct = self.addon.CastTracker

    def cast(self, spell, start, end):
        """UNIT_SPELLCAST_START at `start`, UNIT_SPELLCAST_SUCCEEDED at `end` (seconds)."""
        self.lua.execute(f"STUB.casting = {{ startMS = {start * 1000}, endMS = {end * 1000}, spellID = {spell} }}")
        self.ct.StartCast(self.ct, "player")
        self.lua.execute(f"STUB.time = {end}")
        self.ct.FinishCast(self.ct, "player", "cast-guid", spell)

    def test_back_to_back_casts_count_as_chain(self):
        self.cast(25292, 0, 2.5)                  # first cast: nothing to chain from
        self.assertEqual(self.seg.chainCasts, 0)
        self.cast(25292, 2.6, 5.1)                # started within 1/3 s of the previous end
        self.assertEqual((self.seg.chainCasts, self.seg.chainHaste), (1, 0.1))
        ttl = self.addon.SegmentManager.Get(self.addon.SegmentManager, "Total")
        self.assertEqual(ttl.chainCasts, 1)
        self.cast(25292, 7.0, 9.5)                # gap: not a chain
        self.assertEqual(self.seg.chainCasts, 1)

    def test_instant_on_cooldown_right_after_a_cast(self):
        self.cast(25292, 0, 2.5)
        self.lua.execute("STUB.cooldowns[20930] = { start = 2.5, duration = 10 }")
        self.ct.FinishCast(self.ct, "player", "g", 20930)   # Holy Shock the moment Holy Light lands
        self.assertEqual(self.seg.chainCasts, 1)

    def test_unknown_spells_and_out_of_combat_ignored(self):
        self.ct.FinishCast(self.ct, "player", "g", 424242)
        self.addon.inCombat = False
        self.cast(25292, 0, 2.5)
        self.cast(25292, 2.6, 5.1)
        self.assertEqual(self.seg.chainCasts, 0)


class HistoryQueueTests(unittest.TestCase):
    def test_spell_queue_removed_history_queue_bounded(self):
        lua, addon = load(CORE_FILES)
        self.assertIsNone(addon.Queue.CreateSpellQueue)
        lua.execute("""
            HSW_TEST_ADDON.hsw.db.global.historySize = 2
            H = HSW_TEST_ADDON.Queue.CreateHistoryQueue()
            H:Enqueue({n=1}); H:Enqueue({n=2}); H:Enqueue({n=3})
        """)
        H = lua.globals().H
        self.assertEqual(H.Size(H), 2)
        self.assertEqual((H.Get(H, 0).n, H.Get(H, 1).n), (3, 2))
        self.assertIsNone(H.Get(H, 2))
        self.assertTrue(H.GetDirty(H))
