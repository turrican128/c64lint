#!/usr/bin/env python3
"""Build examples/ - small pictures, each broken in one typical way - and the
README's overlay screenshot in docs/. Run from the repo root:

    python tools/make_examples.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import c64lint  # noqa: E402

PAL = c64lint.PALETTES["pepto-pal"]
EX = ROOT / "examples"
DOCS = ROOT / "docs"


def scene(wide=True):
    """A legal multicolour picture on blue: ground, sun, and a few hills.

    Drawn at 160x200 so every pixel is a C64 pixel, then doubled."""
    img = Image.new("RGB", (160, 200), PAL[6])
    d = ImageDraw.Draw(img)
    d.rectangle((0, 160, 159, 199), fill=PAL[9])            # brown ground
    d.rectangle((0, 152, 159, 159), fill=PAL[5])            # green strip
    d.ellipse((100, 30, 131, 61), fill=PAL[7])              # yellow sun
    d.polygon([(0, 152), (40, 104), (80, 152)], fill=PAL[11])
    d.polygon([(60, 152), (104, 96), (148, 152)], fill=PAL[12])
    for x in range(8, 160, 24):                             # white fence posts
        d.rectangle((x, 168, x + 1, 191), fill=PAL[1])
    return img.resize((320, 200), Image.NEAREST) if wide else img


def check_clean(img, mode="mc"):
    a = c64lint.analyse(img, mode)
    assert a.clean, f"base scene is not clean: {len(a.cells)} cells"


def main():
    EX.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    made = []

    base = scene()
    check_clean(base)
    base.save(EX / "01-clean.png")
    made.append("01-clean.png            clean multicolour, exits 0")

    # a red bird drawn into the sun: sun cell now holds blue, yellow, white,
    # red and black -- one colour too many
    img = scene()
    d = ImageDraw.Draw(img)
    d.rectangle((224, 40, 233, 41), fill=PAL[2])
    d.rectangle((228, 42, 229, 43), fill=PAL[0])
    d.rectangle((226, 38, 227, 39), fill=PAL[1])
    img.save(EX / "02-bird-clash.png")
    made.append("02-bird-clash.png       too many colours in the sun's cells")

    # single-pixel highlights: hires pixels slipped into a multicolour picture
    img = scene()
    px = img.load()
    for x, y in ((205, 34), (211, 36), (241, 48)):
        px[x, y] = PAL[1]
    img.save(EX / "03-split-pairs.png")
    made.append("03-split-pairs.png      1-pixel-wide detail in multicolour")

    # colours nudged by an editor's colour picker / colour management
    img = scene()
    px = img.load()
    r, g, b = PAL[12]
    for y in range(150, 152):
        for x in range(160, 200):
            if px[x, y] == PAL[12]:
                px[x, y] = (r + 2, g + 1, b)
    img.save(EX / "04-off-palette.png")
    made.append("04-off-palette.png      near-miss RGB values from the editor")

    # hires: a third colour inside 8x8 cells
    img = Image.new("RGB", (320, 200), PAL[0])
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 279, 159), outline=PAL[1])
    d.line((40, 100, 279, 100), fill=PAL[14])
    img.save(EX / "05-hires-clash.png")
    made.append("05-hires-clash.png      hires: light blue line crosses white frame")

    # the overlay for the README
    src = Image.open(EX / "02-bird-clash.png").convert("RGB")
    a = c64lint.analyse(src, "mc")
    ov = c64lint.overlay(a, src)
    ov.crop((540, 60, 840, 240)).resize((600, 360), Image.NEAREST).save(DOCS / "overlay-example.png")

    (EX / "README.txt").write_text(
        "c64lint examples - try:\n\n"
        "  c64lint check examples/02-bird-clash.png --mode mc --overlay ov.png --fix fixed.png\n\n"
        + "\n".join(made) + "\n", encoding="utf-8")
    print("\n".join(made))


if __name__ == "__main__":
    main()
