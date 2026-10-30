import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import make_icon as m  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class IconTests(unittest.TestCase):
    def test_four_class_coloured_bars_on_a_dark_background(self):
        img = m.draw(64, m.bar_lengths())
        self.assertEqual(img.size, (64, 64))
        colours = {c for _, c in img.getcolors(64 * 64)}
        for _, colour in m.CLASS_COLOURS:
            self.assertIn(colour, colours)
        self.assertIn(m.BACKGROUND, colours)

    def test_lengths_are_seeded_and_varied(self):
        a, b = m.bar_lengths(), m.bar_lengths()
        self.assertEqual(a, b)
        self.assertGreater(max(a) - min(a), 0.1)

    def test_committed_images_match_the_script(self):
        from PIL import Image
        for name, size in (("icon.png", 64), ("images/HealerStatWeights-512.png", 512)):
            on_disk = Image.open(ROOT / name).convert("RGB")
            self.assertEqual(on_disk.size, (size, size))
            self.assertEqual(list(on_disk.getdata()), list(m.draw(size, m.bar_lengths()).getdata()), name)
