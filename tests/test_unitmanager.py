import unittest
from harness import load

FILES = ["Classes/UnitManager.lua"]


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

    def test_raid_does_not_list_the_player_twice(self):
        setup = 'STUB.group = "raid"; STUB.groupSize = 2; STUB.guids.raid1 = "Player-1"; STUB.names.raid1 = "Me"; STUB.guids.raid2 = "Player-2"; STUB.names.raid2 = "Bob"'
        _, addon = load(FILES, setup=setup)
        um = addon.UnitManager
        um.Cache(um)
        self.assertEqual(sorted(um.GroupNames(um).values()), ["Bob", "Me"])
        self.assertEqual(um.Find(um, "Player-1"), "raid1")
