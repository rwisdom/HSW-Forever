import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import gen_talents as g  # noqa: E402


class RealData(unittest.TestCase):
    def test_tab_map_from_json(self):
        tabs = g.collect()
        self.assertEqual([n for _, n, _ in tabs["PRIEST"]], ["Discipline", "Holy", "Shadow"])
        self.assertEqual([n for _, n, _ in tabs["SHAMAN"]], ["Elemental", "Enhancement", "Restoration"])
        text = g.render(tabs)
        for line in ['\t\t["Mindfulness"] = 3,', '\t\t["Meditation"] = 1,', '\t\t["Spiritual Guidance"] = 2,',
                     '\t\t["Illumination"] = 1,', '\t\t["Reflection"] = 3,', '\t\t["Improved Wrath"] = 1,']:
            self.assertIn(line, text)
        self.assertNotIn("Nature's Grasp", text)   # listed under `removed`: not in Forever
        self.assertTrue(text.startswith("-- GENERATED"))
        self.assertGreaterEqual(text.count("] = "), 190)   # 205 talents at export 2026-10-06
