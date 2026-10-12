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

    # a bird flying past the top of the sun: its cell already holds the sky
    # (blue, the background) and the sun (yellow); red, black and white make
    # four colours besides the background - one too many
    img = scene()
    d = ImageDraw.Draw(img)
    d.rectangle((224, 27, 231, 27), fill=PAL[2])
    d.rectangle((226, 26, 227, 26), fill=PAL[0])
    d.rectangle((228, 25, 229, 25), fill=PAL[1])
    img.save(EX / "02-bird-clash.png")
    made.append("02-bird-clash.png       a bird on the sun's edge: one colour too many")

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

    # hires: stray specks on the edges of white block letters. The letters
    # sit 3 px off the 8x8 grid, so edge cells already hold black AND white;
    # a speck there is a third colour, and the obvious fix is to paint it
    # back to whatever surrounds it.
    img = Image.new("RGB", (320, 200), PAL[0])
    d = ImageDraw.Draw(img)
    o = 3
    for x0 in (64, 136, 208):
        d.rectangle((x0 + o, 64 + o, x0 + 47 + o, 135 + o), fill=PAL[1])
    for x0, y0, x1, y1 in ((80, 80, 111, 119), (96, 88, 111, 111),            # C
                           (152, 80, 167, 95), (152, 104, 167, 119), (168, 80, 183, 95),  # 6
                           (224, 64, 239, 95), (224, 112, 239, 135), (240, 80, 255, 95)):  # 4
        d.rectangle((x0 + o, y0 + o, x1 + o, y1 + o), fill=PAL[0])
    # yellow specks inside the white letters, blue specks just outside them;
    # each lands in a cell that already holds black and white
    for x, y in ((69, 100), (141, 110), (213, 75)):
        img.putpixel((x, y), PAL[7])
    for x, y in ((65, 120), (209, 130)):
        img.putpixel((x, y), PAL[6])
    img.save(EX / "05-hires-clash.png")
    made.append("05-hires-clash.png      hires: stray yellow and blue pixels on the letter edges")

    # the overlay for the README
    src = Image.open(EX / "02-bird-clash.png").convert("RGB")
    a = c64lint.analyse(src, "mc")
    ov = c64lint.overlay(a, src)
    ov.crop((1040, 80, 1240, 200)).resize((600, 360), Image.NEAREST).save(DOCS / "overlay-example.png")

    (EX / "README.txt").write_text(
        "c64lint examples - try:\n\n"
        "  c64lint check examples/02-bird-clash.png --mode mc --overlay ov.png --fix fixed.png\n\n"
        + "\n".join(made) + "\n", encoding="utf-8")
    print("\n".join(made))


if __name__ == "__main__":
    main()
