import unittest
from harness import load


class HarnessSmoke(unittest.TestCase):
    def test_loads_util_with_stubs(self):
        lua, addon = load(["Classes/Util.lua"])
        copy = addon.Util.CopyTable(lua.table(a=1))
        self.assertEqual(copy.a, 1)
