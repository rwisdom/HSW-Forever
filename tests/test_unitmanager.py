import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/UnitManager.lua"]


class UnitManagerTests(unittest.TestCase):
    def test_solo_cache_maps_player_by_guid_and_name(self):
        _, addon = load(FILES)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual(um.Find(um, "Player-1"), "player")
        self.assertEqual(um.FindByName(um, "Me"), "player")
        self.assertEqual(list(um.GroupNames(um).values()), ["Me"])
        self.assertIsNone(um.FindByName(um, "Nobody"))

    def test_party_cache(self):
        setup = 'STUB.group = "party"; STUB.groupSize = 2; STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"; STUB.guids.party2 = "Player-3"; STUB.names.party2 = "Cat"'
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual((um.Find(um, "Player-2"), um.FindByName(um, "Cat")), ("party1", "party2"))
        self.assertEqual(sorted(um.GroupNames(um).values()), ["Bob", "Cat", "Me"])

    def test_group_members_pets_are_cached(self):
        # Blackfathom Deeps 2026-11-13: heals on a hunter's pet were cast and landed, and none was counted
        setup = ('STUB.group = "party"; STUB.groupSize = 2; STUB.guids.party1 = "Player-2"; STUB.names.party1 = "Bob"'
                 '; STUB.guids.partypet1 = "Pet-9"; STUB.names.partypet1 = "Let"')
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual((um.Find(um, "Pet-9"), um.FindByName(um, "Let")), ("partypet1", "partypet1"))
        self.assertEqual(sorted(um.GroupNames(um).values()), ["Bob", "Let", "Me"])
        setup = ('STUB.group = "raid"; STUB.groupSize = 2; STUB.guids.raid1 = "Player-1"; STUB.names.raid1 = "Me"'
                 '; STUB.guids.raid2 = "Player-2"; STUB.names.raid2 = "Bob"; STUB.guids.raidpet2 = "Pet-9"; STUB.names.raidpet2 = "Let"')
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual(um.Find(um, "Pet-9"), "raidpet2")

    def test_secret_unit_identity_is_skipped(self):
        # A secret GUID or name (a unit reached through a hostile one in combat) cannot be a table key: the unit is left out.
        setup = ('issecretvalue = function(v) return v == "SECRET" end; STUB.group = "party"; STUB.groupSize = 1'
                 '; STUB.guids.party1 = "SECRET"; STUB.names.party1 = "SECRET"')
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual(um.Find(um, "Player-1"), "player")
        self.assertIsNone(um.Find(um, "SECRET"))
        self.assertIsNone(um.FindByName(um, "SECRET"))
        self.assertEqual(list(um.GroupNames(um).values()), ["Me"])

    def test_only_the_player_and_group_are_cached(self):
        _, addon = load(FILES, setup='STUB.guids.boss1 = "Creature-9"; STUB.names.boss1 = "Lucifron"; STUB.guids.target = "Creature-9"')
        um = addon.UnitManager
        um.Cache(um)
        self.assertIsNone(um.Find(um, "Creature-9"))

    def test_raid_does_not_list_the_player_twice(self):
        setup = 'STUB.group = "raid"; STUB.groupSize = 2; STUB.guids.raid1 = "Player-1"; STUB.names.raid1 = "Me"; STUB.guids.raid2 = "Player-2"; STUB.names.raid2 = "Bob"'
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual(sorted(um.GroupNames(um).values()), ["Bob", "Me"])
        self.assertEqual(um.Find(um, "Player-1"), "raid1")
