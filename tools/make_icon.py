#!/usr/bin/env python3
"""Draw the addon icon: four horizontal bars in the class colours of the healing classes.

    python tools/make_icon.py

Writes icon.png (64x64, shipped; "## IconTexture" in the .toc shows it in the AddOns list) and
images/HealerStatWeights-512.png (the CurseForge project image, not shipped). Bar lengths are
random but seeded, so the files only change when this script does.
"""
import pathlib
import random

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKGROUND = (26, 26, 26)
CLASS_COLOURS = [            # Blizzard class colours, top to bottom
    ("PRIEST", (255, 255, 255)),
    ("PALADIN", (244, 140, 186)),
    ("SHAMAN", (0, 112, 221)),
    ("DRUID", (255, 124, 10)),
]
SEED = 20261029


def draw(size, lengths):
    """A size x size image: four bars whose widths are `lengths` (fractions of the drawable width)."""
    img = Image.new("RGB", (size, size), BACKGROUND)
    d = ImageDraw.Draw(img)
    margin = round(size * 0.11)
    inner = size - 2 * margin
    gap = round(inner * 0.08)
    bar_h = (inner - 3 * gap) / 4
    radius = max(1, round(bar_h * 0.25))
    for i, ((_, colour), length) in enumerate(zip(CLASS_COLOURS, lengths)):
        top = margin + i * (bar_h + gap)
        width = max(bar_h, inner * length)
        d.rounded_rectangle((margin, round(top), round(margin + width), round(top + bar_h)), radius=radius, fill=colour)
    return img


def bar_lengths(seed=SEED):
    rng = random.Random(seed)
    return [rng.uniform(0.35, 1.0) for _ in CLASS_COLOURS]


def main():
    lengths = bar_lengths()
    out = [(ROOT / "icon.png", 64), (ROOT / "images" / "HealerStatWeights-512.png", 512)]
    for path, size in out:
        path.parent.mkdir(exist_ok=True)
        draw(size, lengths).save(path, optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({size}x{size})")


if __name__ == "__main__":
    main()
