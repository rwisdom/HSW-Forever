import unittest
from harness import load

FILES = ["Classes/Compat.lua", "Classes/Util.lua", "Parsers/Talents_Generated.lua"]


def talents(cls, tabs):
    """tabs: list of (tabName, [(talentName, rank), ...])"""
    lua_tabs = []
    for name, ts in tabs:
        items = ", ".join(f'{{name="{n}", rank={r}, max=5}}' for n, r in ts)
        lua_tabs.append(f'{{name="{name}", talents={{{items}}}}}')
    return f'STUB.class = "{cls}"; STUB.talents = {{{", ".join(lua_tabs)}}}'


class SpecDetection(unittest.TestCase):
    def spec(self, setup):
        _, addon = load(FILES, setup=setup)
        return addon.GetSpecId(addon)

    def test_priest_disc_and_holy(self):
        self.assertEqual(self.spec(talents("PRIEST", [("Discipline", [("Meditation", 3)]), ("Holy", [("Spiritual Guidance", 1)])])), 256)
        self.assertEqual(self.spec(talents("PRIEST", [("Discipline", [("Meditation", 1)]), ("Holy", [("Spiritual Guidance", 5)])])), 257)

    def test_druid_shaman_paladin(self):
        self.assertEqual(self.spec(talents("DRUID", [("Balance", []), ("Feral Combat", []), ("Restoration", [("Reflection", 3)])])), 105)
        self.assertEqual(self.spec(talents("SHAMAN", [("Elemental", []), ("Enhancement", []), ("Restoration", [("Mindfulness", 1)])])), 264)
        self.assertEqual(self.spec(talents("PALADIN", [("Holy", [("Illumination", 5)]), ("Protection", []), ("Retribution", [])])), 65)

    def test_unsupported(self):
        self.assertIsNone(self.spec(talents("WARRIOR", [("Arms", [("Deflection", 5)])])))
        self.assertIsNone(self.spec(talents("DRUID", [("Balance", [("Improved Wrath", 5)]), ("Feral Combat", []), ("Restoration", [])])))
        self.assertIsNone(self.spec(talents("PRIEST", [("Discipline", []), ("Holy", [])])))


class TalentCache(unittest.TestCase):
    def test_rank_lookup_and_snapshot(self):
        lua, addon = load(FILES, setup=talents("PALADIN", [("Holy", [("Illumination", 5), ("Holy Power", 0)]), ("Protection", [("Toughness", 2)])]))
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 5)  # first lookup builds the cache
        lua.execute("STUB.talents[1].talents[1].rank = 4")
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 5)  # cached until a talent event rebuilds it
        addon.Util.RebuildTalentCache()
        self.assertEqual(addon.GetTalentRank(addon, "Illumination"), 4)
        self.assertEqual(addon.GetTalentRank(addon, "Toughness"), 2)
        self.assertEqual(addon.GetTalentRank(addon, "Holy Power"), 0)
        self.assertEqual(addon.GetTalentRank(addon, "Nope"), 0)
        snap = addon.Util.GetTalentSnapshot()
        self.assertEqual([(snap[i].name, snap[i].rank) for i in range(1, len(snap) + 1)], [("Illumination", 4), ("Toughness", 2)])
        self.assertEqual(snap[1].icon, "icon_Illumination")
        lua.execute("STUB.talents[1].talents[1].rank = 1")
        addon.Util.RebuildTalentCache()
        self.assertEqual(snap[1].rank, 4)   # a history entry keeps the snapshot it was given
