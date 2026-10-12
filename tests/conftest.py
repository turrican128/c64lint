import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import c64lint  # noqa: E402

PEPTO = c64lint.PALETTES["pepto-pal"]


def make_png(path, w, h, fill=0, pixels=None, palette=PEPTO, mode="RGB"):
    """Write a PNG of palette index `fill`, with {(x, y): index} overrides.

    pixels values may also be raw RGB tuples (for off-palette tests)."""
    img = Image.new("RGB", (w, h), palette[fill])
    px = img.load()
    for (x, y), v in (pixels or {}).items():
        px[x, y] = v if isinstance(v, tuple) else palette[v]
    if mode != "RGB":
        img = img.convert(mode, palette=Image.ADAPTIVE, colors=256) if mode == "P" else img.convert(mode)
    img.save(path)
    return Path(path)


def mc_cell(cx, cy, colours, wide=True):
    """Pixels for one multicolour cell filled column-wise with `colours`.

    The 4x8 logical cell gets colours spread over its 32 logical pixels in
    order; wide=True returns 320-wide coordinates (doubled pixels)."""
    out = {}
    n = len(colours)
    for ly in range(8):
        for lx in range(4):
            c = colours[(ly * 4 + lx) % n]
            x, y = cx * 4 + lx, cy * 8 + ly
            if wide:
                out[(2 * x, y)] = c
                out[(2 * x + 1, y)] = c
            else:
                out[(x, y)] = c
    return out


def anchored(px=None):
    """Add cells that only fit background 6 (blue): two colour sets whose
    only shared colour is 6, three copies each, on rows 20-21."""
    out = dict(px or {})
    for i in range(3):
        out.update(mc_cell(30 + i, 20, [6, 5, 7, 8]))
        out.update(mc_cell(30 + i, 21, [6, 9, 10, 12]))
    return out


@pytest.fixture
def run(tmp_path, capsys):
    def _run(*argv):
        code = c64lint.main([str(a) for a in argv])
        out = capsys.readouterr()
        return code, out.out + out.err
    return _run
