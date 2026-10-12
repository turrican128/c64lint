#!/usr/bin/env python3
"""c64lint - check a PNG against C64 bitmap mode rules and explain the clashes.

Tells you which 8x8 / 4x8 cells break the multicolour or hires colour limits,
which colour in each cell is the surplus one, which background ($d021) fits the
picture best, and which palette the picture was drawn in. Optionally writes the
cheapest fix, an overlay, a JSON report, a Koala file, or hands the clean
picture to png2prg (github.com/staD020/png2prg).
"""

import argparse
import io
import itertools
import json
import math
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERSION = "1.0.0"
PNG2PRG_URL = "https://github.com/staD020/png2prg"

COLOUR_NAMES = [
    "black", "white", "red", "cyan", "purple", "green", "blue", "yellow",
    "orange", "brown", "light red", "dark grey", "grey", "light green",
    "light blue", "light grey",
]

# Palette values copied from the .vpl files shipped with VICE 3.0, plus
# Colodore. Order matters: on a detection tie the earlier palette wins.
_PALETTE_HEX = {
    "pepto-pal": "000000 FFFFFF 68372B 70A4B2 6F3D86 588D43 352879 B8C76F 6F4F25 433900 9A6759 444444 6C6C6C 9AD284 6C5EB5 959595",
    "colodore": "000000 FFFFFF 813338 75CEC8 8E3C97 56AC4D 2E2C9B EDF171 8E5029 553800 C46C71 4A4A4A 7B7B7B A9FF9F 706DEB B2B2B2",
    "vice": "000000 FDFEFC BE1A24 30E6C6 B41AE2 1FD21E 211BAE DFF60A B84104 6A3304 FE4A57 424540 70746F 59FE59 5F53FE A4A7A2",
    "community-colors": "000000 FFFFFF AF2A29 62D8CC B03FB6 4AC64A 3739C4 E4ED4E B6591C 683808 EA746C 4D4D4D 848484 A6FA9E 707CE6 B6B6B5",
    "deekay": "000000 FFFFFF 882000 68D0A8 A838A0 50B818 181090 F0E858 A04800 472B1B C87870 484848 808080 98FF98 5090D0 B8B8B8",
    "pepto-palold": "000000 FFFFFF 58291D 91C6D5 915CA8 588D43 352879 B8C76F 916F43 433900 9A6759 353535 747474 9AD284 7466BE B8B8B8",
    "ptoing": "000000 FFFFFF 8C3E34 7ABFC7 8D47B3 68A941 3E31A2 D0DC71 905F25 574200 BB776D 545454 808080 ACEA88 7C70DA ABABAB",
    "c64hq": "0A0A0A FFF8FF 851F02 65CDA8 A73B9F 4DAB19 1A0C92 EBE353 A94B02 441E00 D28074 464646 8B8B8B 8EF68E 4D91D1 BABABA",
    "ccs64": "101010 FFFFFF E04040 60FFFF E060E0 40E040 4040E0 FFFF40 E0A040 9C7448 FFA0A0 545454 888888 A0FFA0 A0A0FF C0C0C0",
    "frodo": "000000 FFFFFF CC0000 00FFCC FF00FF 00CC00 0000CC FFFF00 FF8800 884400 FF8888 444444 888888 88FF88 8888FF CCCCCC",
    "godot": "000000 FFFFFF 880000 AAFFEE CC44CC 00CC55 0000AA EEEE77 DD8855 664400 FE7777 333333 777777 AAFF66 0088FF BBBBBB",
    "pc64": "212121 FFFFFF B52121 73FFFF B521B5 21B521 2121B5 FFFF21 B57321 944221 FF7373 737373 949494 73FF73 7373FF B5B5B5",
    "c64s": "000000 FCFCFC A80000 54FCFC A800A8 00A800 0000A8 FCFC00 A85400 802C00 FC5454 545454 808080 54FC54 5454FC A8A8A8",
    "pepto-ntsc": "000000 FFFFFF 67372B 70A3B1 6F3D86 588C42 342879 B7C66E 6F4E25 423800 996659 434343 6B6B6B 9AD183 6B5EB5 959595",
    "pepto-ntsc-sony": "000000 FFFFFF 7C352B 5AA6B1 694185 5D8643 212E78 CFBE6F 894A26 5B3300 AF6459 434343 6B6B6B A0CB84 5665B3 959595",
}

PALETTES = {
    name: [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in row.split()]
    for name, row in _PALETTE_HEX.items()
}

# Every built-in palette numbers its colours the same way, and no RGB value sits
# at two different numbers across them, so a colour that exactly matches ANY
# palette keeps that number even when another palette is forced.
EXACT_ANY = {}
for _pal in PALETTES.values():
    for _i, _rgb in enumerate(_pal):
        EXACT_ANY.setdefault(_rgb, _i)

FAR_DELTA_E = 20.0   # beyond this from every palette entry: probably not C64 art
MODE_HINT_PAIRS = 320  # this many split pairs: probably hires art in --mode mc
MAX_COLOURS = 256    # more distinct colours than this: a photo, not pixel art
SIZES = ((160, 200), (320, 200))


class LintError(Exception):
    """Bad input or usage: reported with '!!' and exit code 2."""
    code = 2


class Png2prgError(LintError):
    """png2prg ran but failed: exit code 3, so scripts can tell it apart."""
    code = 3


# ---------- colour maths ------------------------------------------------------

def rgb_to_lab(rgb):
    """sRGB (0-255) -> CIE Lab (D65)."""
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a, b):
    """CIE76 colour difference between two Lab colours."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


# ---------- input -------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _sniff(head):
    """Name a non-PNG file from its first bytes."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return "AVIF"
    for magic, name in ((b"\xff\xd8", "JPEG"), (b"GIF8", "GIF"), (b"BM", "BMP"),
                        (b"II*\x00", "TIFF"), (b"MM\x00*", "TIFF")):
        if head.startswith(magic):
            return name
    return "not a PNG file" if head else "an empty file"


def load_png(path):
    """Return (RGB image, notes), or raise LintError with a readable reason.

    notes are warnings for the report (e.g. an animated PNG)."""
    path = Path(path)
    if path.is_dir():
        raise LintError(f"{path}: is a directory, not a picture")
    if not path.is_file():
        raise LintError(f"{path}: file not found")
    notes = []
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:8] != PNG_SIGNATURE:
        raise LintError(f"{path}: is {_sniff(head)}, c64lint reads PNG only")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            img = Image.open(path)
        fmt = img.format
    except Exception as e:  # Pillow raises many types for broken files
        raise LintError(f"{path}: not a readable PNG ({e})") from None
    if fmt != "PNG":
        raise LintError(f"{path}: is {fmt or 'not an image'}, c64lint reads PNG only")
    if img.size not in SIZES:          # checked before decoding a huge file
        w, h = img.size
        raise LintError(f"{path}: picture is {w}x{h}; C64 bitmaps are 320x200 "
                        "(multicolour also 160x200)")
    if getattr(img, "n_frames", 1) > 1:
        notes.append(f"animated PNG with {img.n_frames} frames: only the first frame "
                     "is checked")
    try:
        img.load()
    except Exception as e:
        raise LintError(f"{path}: not a readable PNG ({e})") from None
    if img.mode.startswith("I"):        # 16-bit greyscale: scale, don't clip
        img = img.convert("I").point(lambda v: v * (1 / 257)).convert("L")
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        lo, _ = alpha.getextrema()
        if lo < 255:
            n = sum(1 for a in _pixels(alpha) if a < 255)
            raise LintError(f"{path}: {n} transparent pixel(s); C64 pictures have no "
                            "transparency - flatten onto the background colour first")
        img = rgba
    return img.convert("RGB"), notes


# ---------- analysis ----------------------------------------------------------

def _pixels(img):
    """Flat pixel list; getdata() is deprecated from Pillow 12."""
    get = getattr(img, "get_flattened_data", None) or img.getdata
    return get()


class Analysis:
    """Everything c64lint knows about one picture; built by analyse()."""


def detect_palette(colours, force=None):
    """Pick the palette whose entries sit closest to the picture's colours."""
    labs = {c: rgb_to_lab(c) for c in colours}
    if force:
        return force
    best = None
    for name, pal in PALETTES.items():
        plab = [rgb_to_lab(p) for p in pal]
        score = sum(min(delta_e(labs[c], p) for p in plab) for c in colours)
        if best is None or score < best[0] - 1e-9:
            best = (score, name)
    return best[1]


def analyse(img, mode, palette=None, bg=None):
    w, h = img.size
    if mode == "mc" and (w, h) not in ((160, 200), (320, 200)):
        raise LintError(f"picture is {w}x{h}; multicolour needs 160x200 or 320x200")
    if mode == "hires" and (w, h) != (320, 200):
        raise LintError(f"picture is {w}x{h}; hires needs 320x200")

    a = Analysis()
    a.mode, a.size = mode, (w, h)
    a.bg_note = None
    rgb = list(_pixels(img))

    # 1. palette
    first, counts = {}, {}
    for i, c in enumerate(rgb):
        if c not in first:
            first[c] = (i % w, i // w)
        counts[c] = counts.get(c, 0) + 1
    if len(first) > MAX_COLOURS:
        raise LintError(f"picture has {len(first)} different colours; a C64 picture has "
                        "16. This looks like a photo or a scaled image - c64lint checks "
                        "pixel art. Convert it to C64 colours first (e.g. Dithertron, "
                        "Retropixels), then check the result")
    a.palette = detect_palette(list(first), palette)
    pal = PALETTES[a.palette]
    a.rgb = pal
    plab = [rgb_to_lab(p) for p in pal]
    a.de = [[delta_e(p, q) for q in plab] for p in plab]
    exact = {p: i for i, p in reversed(list(enumerate(pal)))}
    snap, a.off_palette, a.notes = {}, [], []
    for c in first:
        if c in exact:
            snap[c] = exact[c]
            continue
        lab = rgb_to_lab(c)
        dists = [delta_e(lab, p) for p in plab]
        if c in EXACT_ANY:          # another palette's exact colour: keep its number
            idx = EXACT_ANY[c]
        else:
            idx = min(range(16), key=lambda k: (dists[k], k))
        snap[c] = idx
        a.off_palette.append({
            "rgb": "#%02X%02X%02X" % c, "count": counts[c], "first": list(first[c]),
            "nearest": idx, "delta_e": round(dists[idx], 2),
            "far": dists[idx] > FAR_DELTA_E,
        })
    groups = {}
    for c, idx in snap.items():
        groups.setdefault(idx, []).append(c)
    for idx in sorted(groups):
        cs = sorted(groups[idx], key=lambda c: -counts[c])
        if len(cs) > 1:
            shown = ", ".join("#%02X%02X%02X" % c for c in cs[:3])
            more = f" and {len(cs) - 3} more" if len(cs) > 3 else ""
            a.notes.append(f"{len(cs)} different colours ({shown}{more}) both read as "
                           f"{idx} {COLOUR_NAMES[idx]}; if they were meant to be different "
                           "C64 colours, check the palette (--palette)")
    a.off_palette.sort(key=lambda o: (o["first"][1], o["first"][0]))
    grid = [snap[c] for c in rgb]          # palette index per input pixel

    # 2. pixel pairs -> logical grid (one entry per C64 pixel)
    a.pairs = []
    if mode == "mc" and w == 320:
        lw = 160
        logical = []
        cell_counts = {}           # (cx, cy) -> {colour: pixels}, built on demand
        for y in range(h):
            row = grid[y * w:(y + 1) * w]
            for lx in range(lw):
                p0, p1 = row[2 * lx], row[2 * lx + 1]
                if p0 == p1:
                    logical.append(p0)
                    continue
                a.pairs.append({"x": 2 * lx, "y": y, "colours": sorted((p0, p1))})
                key = (lx // 4, y // 8)
                counts_here = cell_counts.get(key)
                if counts_here is None:
                    counts_here = {}
                    for yy in range(key[1] * 8, key[1] * 8 + 8):
                        for v in grid[yy * w + key[0] * 8:yy * w + key[0] * 8 + 8]:
                            counts_here[v] = counts_here.get(v, 0) + 1
                    cell_counts[key] = counts_here
                n0, n1 = counts_here.get(p0, 0), counts_here.get(p1, 0)
                logical.append(p0 if (n0, -p0) > (n1, -p1) else p1)
    else:
        lw = w
        logical = grid
    a.lw = lw
    a.logical = logical

    # 3./4. cells
    cw = 4 if mode == "mc" else 8
    a.cell_w = cw
    hists = []
    for cy in range(25):
        for cx in range(40):
            hist = {}
            for y in range(cy * 8, cy * 8 + 8):
                base = y * lw + cx * cw
                for v in logical[base:base + cw]:
                    hist[v] = hist.get(v, 0) + 1
            hists.append(tuple(sorted(hist.items())))
    a.hists = hists

    de = palette_de(pal)
    memo = {}

    def cell_fix(hist, b):
        key = (hist, b)
        if key not in memo:
            memo[key] = best_set(hist, b, de)
        return memo[key]

    if mode == "mc":
        totals = [0] * 16
        for v in logical:
            totals[v] += 1
        ranking = []
        # a forced background is the user's decision: costing the other 15
        # is most of the run time on busy pictures, so it is skipped
        for b in (range(16) if bg is None else (bg,)):
            cost = bad = 0
            for hist in hists:
                c, _ = cell_fix(hist, b)
                if c is not None:
                    cost += c
                    bad += 1
            ranking.append({"bg": b, "cost": round(cost, 2), "bad_cells": bad,
                            "_key": (round(cost, 6), bad, -totals[b], b)})
        ranking.sort(key=lambda r: r["_key"])
        for r in ranking:
            del r["_key"]
        a.bg_ranking = ranking
        a.bg = ranking[0]["bg"] if bg is None else bg
        main_colour = max(range(16), key=lambda c: (totals[c], -c))
        if bg is None and a.bg != main_colour:
            alt = next(r for r in ranking if r["bg"] == main_colour)
            share = round(100 * totals[main_colour] / len(logical))
            a.bg_note = (
                f"background {a.bg} {COLOUR_NAMES[a.bg]} was picked because it is the "
                f"cheapest, but {main_colour} {COLOUR_NAMES[main_colour]} covers {share}% "
                f"of the picture. If {COLOUR_NAMES[main_colour]} is meant to be the "
                f"background, run again with --bg {main_colour}: then "
                f"{alt['bad_cells']} cell(s) need fixing")
    else:
        a.bg_ranking = []
        a.bg = None

    a.cells = []
    for i, hist in enumerate(hists):
        cost, keep = cell_fix(hist, a.bg)
        if cost is None:
            continue
        cols = dict(hist)
        changed = sum(n for c, n in hist if c not in keep)
        a.cells.append({
            "cx": i % 40, "cy": i // 40,
            "x": (i % 40) * cw * (w // lw), "y": (i // 40) * 8,
            "colours": {str(c): n for c, n in sorted(cols.items(), key=lambda t: (-t[1], t[0]))},
            "surplus": sorted(c for c in cols if c not in keep),
            "fix": {"keep": list(keep), "changed": changed, "cost": round(cost, 2)},
        })
    if mode == "mc" and len(a.pairs) >= MODE_HINT_PAIRS:
        a.notes.append(f"{len(a.pairs)} split pixel pairs: this looks like a hires picture - "
                       "if it is, check it with --mode hires")
    if mode == "hires" and a.cells and all(
            grid[i] == grid[i + 1] for i in range(0, len(grid), 2)):
        a.notes.append(f"every pixel is 2 wide and {len(a.cells)} cell(s) break the hires "
                       "rules: this looks like a multicolour picture - if it is, check it "
                       "with --mode mc")
    a.clean = not (a.off_palette or a.pairs or a.cells)
    return a


def palette_de(pal):
    """16x16 table of CIE76 distances between a palette's colours."""
    plab = [rgb_to_lab(p) for p in pal]
    return tuple(tuple(delta_e(p, q) for q in plab) for p in plab)


def best_set(hist, bg, de):
    """Cheapest legal colour set for one cell, by exhaustive search.

    hist is the cell's sorted ((colour, count), ...); bg is the background
    (None for hires). Returns (None, None) when the cell is already legal,
    else (cost, keep): keep is the sorted tuple of colours the cell may keep
    (for multicolour it includes the background). Only the cell's own colours
    are candidates. Ties go to the smallest keep tuple."""
    colours = [c for c, _ in hist]
    if bg is None:                        # hires: two colours per cell
        if len(colours) <= 2:
            return None, None
        pool, k, fixed = colours, 2, ()
    else:                                 # multicolour: background + three
        pool = [c for c in colours if c != bg]
        if len(pool) <= 3:
            return None, None
        k, fixed = 3, (bg,)
    # biggest contributions first, so the running total passes the bound early
    rows = [(c, n, de[c]) for c, n in sorted(hist, key=lambda t: -t[1])]

    def cost_of(keep, bound):
        cost = 0.0
        if len(keep) == 4:
            k0, k1, k2, k3 = keep
            for c, n, row in rows:
                if c != k0 and c != k1 and c != k2 and c != k3:
                    cost += n * min(row[k0], row[k1], row[k2], row[k3])
                    if cost > bound + 1e-9:
                        return None
        else:
            k0, k1 = keep
            for c, n, row in rows:
                if c != k0 and c != k1:
                    cost += n * min(row[k0], row[k1])
                    if cost > bound + 1e-9:
                        return None
        return cost

    # seed the bound with the most-used colours: usually close to the answer,
    # so most other sets are abandoned after a pixel or two
    count = dict(hist)
    seed = tuple(sorted(sorted(pool, key=lambda c: (-count[c], c))[:k] + list(fixed)))
    best = (cost_of(seed, math.inf), seed)
    for subset in itertools.combinations(pool, k):
        keep = tuple(sorted(subset + fixed))
        cost = cost_of(keep, best[0])
        if cost is not None and (cost < best[0] - 1e-9 or (
                abs(cost - best[0]) <= 1e-9 and keep < best[1])):
            best = (cost, keep)
    return best


# ---------- fixing ------------------------------------------------------------

def fixed_logical(a):
    """Logical index grid with every broken cell repainted."""
    out = list(a.logical)
    for cell in a.cells:
        keep = cell["fix"]["keep"]
        for y in range(cell["cy"] * 8, cell["cy"] * 8 + 8):
            base = y * a.lw + cell["cx"] * a.cell_w
            for i in range(base, base + a.cell_w):
                v = out[i]
                if v not in keep:
                    out[i] = min(keep, key=lambda q: (a.de[v][q], q))
    return out


def render(a, logical):
    """Logical index grid -> RGB image at the input resolution."""
    lw, (w, h) = a.lw, a.size
    img = Image.new("RGB", (lw, h))
    img.putdata([a.rgb[v] for v in logical])
    if lw != w:
        img = img.resize((w, h), Image.NEAREST)
    return img


def encode_koala(a, logical, bg):
    """Koala (.kla) bytes from a legal multicolour logical grid."""
    bitmap, screen, colram = bytearray(8000), bytearray(1000), bytearray(1000)
    for cy in range(25):
        for cx in range(40):
            cell = cy * 40 + cx
            used = sorted({logical[y * 160 + cx * 4 + x]
                           for y in range(cy * 8, cy * 8 + 8) for x in range(4)} - {bg})
            if len(used) > 3:
                raise LintError(f"internal: cell ({cx},{cy}) still has {len(used)} colours")
            used += [0] * (3 - len(used))
            screen[cell] = (used[0] << 4) | used[1]
            colram[cell] = used[2]
            code = {bg: 0}
            for bits, c in zip((1, 2, 3), used):
                code.setdefault(c, bits)
            for ly in range(8):
                byte = 0
                for lx in range(4):
                    byte = (byte << 2) | code[logical[(cy * 8 + ly) * 160 + cx * 4 + lx]]
                bitmap[cell * 8 + ly] = byte
    return bytes([0x00, 0x60]) + bytes(bitmap) + bytes(screen) + bytes(colram) + bytes([bg])


def decode_koala(data, palette):
    """Koala bytes -> 320x200 RGB image (used by the tests and for checks)."""
    if len(data) != 10003:
        raise LintError(f"Koala file is {len(data)} bytes, expected 10003")
    body = data[2:]
    bitmap, screen, colram, bg = body[:8000], body[8000:9000], body[9000:10000], body[10000] & 15
    img = Image.new("RGB", (160, 200))
    px = img.load()
    for cell in range(1000):
        cx, cy = cell % 40, cell // 40
        cols = (bg, screen[cell] >> 4, screen[cell] & 15, colram[cell] & 15)
        for ly in range(8):
            byte = bitmap[cell * 8 + ly]
            for lx in range(4):
                px[cx * 4 + lx, cy * 8 + ly] = palette[cols[(byte >> (6 - 2 * lx)) & 3]]
    return img.resize((320, 200), Image.NEAREST)


# ---------- pictures for humans ------------------------------------------------

SCALE = 5
MARK = 2   # size of the corner marks on a scaled pixel


def _dim(img, factor=0.35):
    return Image.eval(img, lambda v: int(v * factor))


def _mark(draw, x, y, colour, corner):
    """Small square in one corner of scaled input pixel (x, y); the rest of
    the pixel keeps its own colour, so the mark never hides what it marks."""
    px, py = x * SCALE, y * SCALE
    if corner == "br":
        px, py = px + SCALE - MARK, py + SCALE - MARK
    draw.rectangle((px, py, px + MARK - 1, py + MARK - 1), fill=colour)


def _box(draw, x0, y0, x1, y1, colour):
    """Frame drawn just OUTSIDE input pixels x0..x1-1, y0..y1-1."""
    draw.rectangle((x0 * SCALE - 1, y0 * SCALE - 1, x1 * SCALE, y1 * SCALE), outline=colour)


def overlay(a, src):
    """Input scaled x5: clean areas dimmed; broken cells at full brightness,
    framed red, surplus pixels marked magenta (top-left corner); off-palette
    pixels marked cyan (bottom-right); split pairs framed yellow."""
    w, h = a.size
    big = src.resize((w * SCALE, h * SCALE), Image.NEAREST)
    out = _dim(big)
    draw = ImageDraw.Draw(out)
    sx = w // a.lw                                      # input px per C64 px
    for cell in a.cells:
        x0, y0 = cell["cx"] * a.cell_w * sx, cell["cy"] * 8
        box = (x0 * SCALE, y0 * SCALE, (x0 + a.cell_w * sx) * SCALE, (y0 + 8) * SCALE)
        out.paste(big.crop(box), box[:2])
    for cell in a.cells:
        x0, y0 = cell["cx"] * a.cell_w * sx, cell["cy"] * 8
        keep = cell["fix"]["keep"]
        for y in range(y0, y0 + 8):
            for lx in range(a.cell_w):
                if a.logical[y * a.lw + cell["cx"] * a.cell_w + lx] not in keep:
                    for dx in range(sx):
                        _mark(draw, (cell["cx"] * a.cell_w + lx) * sx + dx, y,
                              (255, 0, 255), "tl")
        _box(draw, x0, y0, x0 + a.cell_w * sx, y0 + 8, (255, 0, 0))
    px = src.load()
    off = {o["rgb"] for o in a.off_palette}
    if off:
        for y in range(h):
            for x in range(w):
                if "#%02X%02X%02X" % px[x, y] in off:
                    _mark(draw, x, y, (0, 255, 255), "br")
    for p in a.pairs:
        _box(draw, p["x"], p["y"], p["x"] + 2, p["y"] + 1, (255, 255, 0))
    return out


DIFF_GAP = 4 * SCALE
DIFF_TOP = 40          # label strip above the before/after halves
ZOOM_LABEL = 40        # caption strip above the zoom panel
LABEL = (230, 230, 230)


def _label_font():
    """Pillow's built-in bitmap font: the same pixels with or without
    FreeType, so the slim exe draws exactly what the source draws."""
    load = getattr(ImageFont, "load_default_imagefont", None)
    return load() if load else ImageFont.load_default()


def _label(out, x, y, text, scale=3, colour=LABEL):
    """Draw text at (x, y), scaled up crisp (nearest neighbour)."""
    font = _label_font()
    x0, y0, x1, y1 = font.getbbox(text)
    tmp = Image.new("L", (x1 + 1, y1 + 1), 0)
    ImageDraw.Draw(tmp).text((0, 0), text, fill=255, font=font)
    tmp = tmp.resize((tmp.width * scale, tmp.height * scale), Image.NEAREST)
    out.paste(Image.new("RGB", tmp.size, colour), (x, y), tmp)
DIFF_FRAME = (255, 0, 255)
ZOOM_MAX, ZOOM_MAX_HEIGHT = 16, 600


def _zoom_layout(w, h, changed, cell):
    """Where the zoom panel goes: (zoom, bbox, left x, right x, top y).

    bbox is the changed area grown to whole cells plus one cell of context."""
    xs = [x for x, _ in changed]
    ys = [y for _, y in changed]
    bx0 = max(0, (min(xs) // cell - 1) * cell)
    by0 = max(0, (min(ys) // 8 - 1) * 8)
    bx1 = min(w, (max(xs) // cell + 2) * cell)
    by1 = min(h, (max(ys) // 8 + 2) * 8)
    half = w * SCALE
    z = max(1, min(ZOOM_MAX, half // (bx1 - bx0), ZOOM_MAX_HEIGHT // (by1 - by0)))
    pad = (half - (bx1 - bx0) * z) // 2
    return (z, (bx0, by0, bx1, by1), pad, half + DIFF_GAP + pad,
            DIFF_TOP + h * SCALE + ZOOM_LABEL)


def diff_zoom_geometry(diff, changed, cell):
    """Zoom-panel geometry of a diff image (for tests and tools)."""
    w = (diff.width - DIFF_GAP) // (2 * SCALE)
    h = 200
    z, box, lx, rx, top = _zoom_layout(w, h, changed, cell)
    return z, box[:2], (lx, rx), top


def diff_image(before, after, cell=8):
    """What the fix changed, readable at a glance.

    Top: before and after side by side, x5. Everything the fix left alone is
    grey and dark; changed pixels keep their colour (old on the left, new on
    the right) and every cell the fix touched is framed magenta, so the
    changes show even as a thumbnail. Below: the changed area only, magnified
    up to 16x, before and after, each changed pixel outlined."""
    w, h = after.size
    b, f = before.load(), after.load()
    changed = [(x, y) for y in range(h) for x in range(w) if b[x, y] != f[x, y]]
    zoom = _zoom_layout(w, h, changed, cell) if changed else None
    height = DIFF_TOP + h * SCALE
    if zoom:
        z, (bx0, by0, bx1, by1), lx, rx, top = zoom
        height = top + (by1 - by0) * z + DIFF_GAP
    out = Image.new("RGB", (2 * w * SCALE + DIFF_GAP, height), (40, 40, 40))
    sides = []
    for i, img in enumerate((before, after)):
        big = img.resize((w * SCALE, h * SCALE), Image.NEAREST)
        grey = big.convert("L").point(lambda v: int(v * 0.3)).convert("RGB")
        left = i * (w * SCALE + DIFF_GAP)
        out.paste(grey, (left, DIFF_TOP))
        sides.append((big, left))
    _label(out, 4, 4, "BEFORE")
    _label(out, w * SCALE + DIFF_GAP + 4, 4,
           "AFTER --fix    magenta = cells the fix changed" if changed
           else "AFTER --fix    nothing changed")
    draw = ImageDraw.Draw(out)
    for x, y in changed:
        for big, left in sides:
            box = (x * SCALE, y * SCALE, (x + 1) * SCALE, (y + 1) * SCALE)
            out.paste(big.crop(box), (left + box[0], DIFF_TOP + box[1]))
    for cx, cy in sorted({(x // cell, y // 8) for x, y in changed}):
        for _, left in sides:
            x0, y0 = left + cx * cell * SCALE, DIFF_TOP + cy * 8 * SCALE
            x1, y1 = x0 + cell * SCALE, y0 + 8 * SCALE
            for k in (1, 2):                       # 2-pixel frame outside the cell
                draw.rectangle((x0 - k, y0 - k, x1 - 1 + k, y1 - 1 + k), outline=DIFF_FRAME)
    if zoom:
        for img, px0 in ((before, lx), (after, rx)):
            crop = img.crop((bx0, by0, bx1, by1)).resize(((bx1 - bx0) * z, (by1 - by0) * z),
                                                         Image.NEAREST)
            out.paste(crop, (px0, top))
            # outline the edge of each changed area, thin enough that a one
            # pixel wide run still shows its colour inside the outline
            t = 2 if z >= 16 else 1
            if z < 8:       # too small to outline inside: ring around the pixel
                for x, y in changed:
                    qx, qy = px0 + (x - bx0) * z, top + (y - by0) * z
                    draw.rectangle((qx - 2 * z, qy - 2 * z, qx + 3 * z - 1, qy + 3 * z - 1),
                                   outline=DIFF_FRAME)
            else:
                cset = set(changed)
                for x, y in changed:
                    qx, qy = px0 + (x - bx0) * z, top + (y - by0) * z
                    if (x - 1, y) not in cset:
                        draw.rectangle((qx, qy, qx + t - 1, qy + z - 1), fill=DIFF_FRAME)
                    if (x + 1, y) not in cset:
                        draw.rectangle((qx + z - t, qy, qx + z - 1, qy + z - 1), fill=DIFF_FRAME)
                    if (x, y - 1) not in cset:
                        draw.rectangle((qx, qy, qx + z - 1, qy + t - 1), fill=DIFF_FRAME)
                    if (x, y + 1) not in cset:
                        draw.rectangle((qx, qy + z - t, qx + z - 1, qy + z - 1), fill=DIFF_FRAME)
        _label(out, 4, top - ZOOM_LABEL + 8, f"ZOOM x{z} - before", scale=2)
        _label(out, w * SCALE + DIFF_GAP + 4, top - ZOOM_LABEL + 8, f"ZOOM x{z} - after", scale=2)
    return out


def diff_stats(before, after, cell=8):
    """(changed screen pixels, cells touched) between two same-size pictures."""
    w, h = after.size
    b, f = before.load(), after.load()
    changed = [(x, y) for y in range(h) for x in range(w) if b[x, y] != f[x, y]]
    return len(changed), len({(x // cell, y // 8) for x, y in changed})


# ---------- report ------------------------------------------------------------

def _name(i):
    return f"{i} {COLOUR_NAMES[i]}"


OFF_PALETTE_LINES = 10
CELL_LINES = 20


def print_report(a, path, palette_forced, bg_forced, notes=()):
    mode = "multicolour" if a.mode == "mc" else "hires"
    w, h = a.size
    how = "forced" if palette_forced else "detected"
    print(f"[*] {path}: {w}x{h} {mode}, palette {a.palette} ({how})")
    for n in notes:
        print(f"[!] {n}")
    for o in a.off_palette[:OFF_PALETTE_LINES]:
        far = " - far from every C64 colour, is this C64 art?" if o["far"] else ""
        print(f"[!] off-palette {o['rgb']} x{o['count']} first at ({o['first'][0]},{o['first'][1]}):"
              f" nearest {_name(o['nearest'])}, dE {o['delta_e']}{far}")
    if len(a.off_palette) > OFF_PALETTE_LINES:
        print(f"[!] ... and {len(a.off_palette) - OFF_PALETTE_LINES} more off-palette "
              "colour(s); --json lists them all")
    if a.pairs:
        p = a.pairs[0]
        print(f"[!] {len(a.pairs)} pixel pair(s) with two different colours (multicolour "
              f"pixels are 2 wide), first at ({p['x']},{p['y']}): "
              f"{_name(p['colours'][0])} / {_name(p['colours'][1])}")
    if a.mode == "mc":
        if not bg_forced:
            top = ", ".join(f"{_name(r['bg'])} ({r['bad_cells']} bad, cost {r['cost']})"
                            for r in a.bg_ranking[:5])
            print(f"[*] background ranking: {top}")
        src = "forced with --bg; ranking skipped" if bg_forced else "best"
        print(f"[*] background: {_name(a.bg)} ({src})")
        if a.bg_note:
            print(f"[!] {a.bg_note}")
    for c in a.cells[:CELL_LINES]:
        cols = ", ".join(f"{_name(int(k))} x{n}" for k, n in c["colours"].items())
        sur = ", ".join(_name(s) for s in c["surplus"])
        print(f"[!] cell ({c['cx']},{c['cy']}) at x={c['x']} y={c['y']}: {cols}; "
              f"surplus: {sur}; fix repaints {c['fix']['changed']} C64 pixel(s)")
    if len(a.cells) > CELL_LINES:
        print(f"[!] ... and {len(a.cells) - CELL_LINES} more broken cell(s); "
              "--json lists them all")
    if a.clean:
        print("[*] CLEAN: fits the mode as drawn")
    else:
        bits = []
        if a.off_palette:
            bits.append(f"{len(a.off_palette)} off-palette colour(s)")
        if a.pairs:
            bits.append(f"{len(a.pairs)} split pair(s)")
        if a.cells:
            bits.append(f"{len(a.cells)} broken cell(s)")
        print(f"[!] NOT CLEAN: {', '.join(bits)}")


def report_json(a, path, notes=()):
    return {
        "version": 1, "tool": f"c64lint {VERSION}", "file": str(path),
        "notes": list(notes) + ([a.bg_note] if a.bg_note else []),
        "mode": a.mode, "palette": a.palette, "bg": a.bg,
        "bg_ranking": a.bg_ranking, "off_palette": a.off_palette,
        "pairs": a.pairs, "cells": a.cells, "clean": a.clean,
    }


# ---------- command line --------------------------------------------------------

EXIT_CODES = """Exit codes:
  0  clean: the picture fits the mode as drawn
  1  problems found (also when --fix fixed them)
  2  bad input or bad options - nothing was written
  3  png2prg (--then) failed"""


def build_parser():
    fmt = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(
        prog="c64lint", allow_abbrev=False, formatter_class=fmt,
        description="Check a PNG drawn for the C64 against bitmap mode rules, explain "
                    "every clash and write the cheapest fix.",
        epilog="Start with:  c64lint check pic.png --mode mc --overlay ov.png --fix fixed.png"
               "\n\n" + EXIT_CODES)
    ap.add_argument("--version", action="version", version=f"c64lint {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="{check,palettes}")
    c = sub.add_parser("check", help="check a picture (and optionally fix it)",
                       allow_abbrev=False, formatter_class=fmt, epilog=EXIT_CODES,
                       description="Check one PNG. Without output options it only reports.")
    c.add_argument("png", help="the picture: PNG, 320x200 (multicolour also 160x200)")
    c.add_argument("--mode", required=True, choices=["mc", "hires"],
                   help="mc = multicolour bitmap (Koala), hires = hires bitmap")
    c.add_argument("--palette", choices=list(PALETTES), metavar="NAME",
                   help="use this palette instead of detecting one "
                        "(see: c64lint palettes)")
    c.add_argument("--bg", type=int, choices=range(16), metavar="0-15",
                   help="background colour ($d021) instead of the cheapest one "
                        "(multicolour only)")
    c.add_argument("--overlay", metavar="OUT.png",
                   help="write the problems drawn over your picture, 5x size")
    c.add_argument("--json", metavar="OUT.json",
                   help="write the whole report as JSON")
    c.add_argument("--fix", metavar="OUT.png",
                   help="write the cheapest fix, plus OUT.diff.png showing what changed")
    c.add_argument("--kla", metavar="OUT.kla",
                   help="write a Koala file (multicolour), only from a clean result")
    c.add_argument("--then", choices=["png2prg"],
                   help="run png2prg on the clean result; its arguments go after --")
    sub.add_parser("palettes", help="list the built-in palettes")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:   # a Hebrew or accented path must not crash a redirected console
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        build_parser().print_help()
        return 2
    then_args = []
    wants_then = any(x == "--then" or x.startswith("--then=") for x in argv)
    if wants_then and "--" in argv:
        i = argv.index("--")
        argv, then_args = argv[:i], argv[i + 1:]
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if args.cmd == "palettes":
        for name in PALETTES:
            print(name)
        return 0
    try:
        return check(args, then_args)
    except LintError as e:
        print(f"!! {e}")
        return e.code


def _same_file(p, q):
    """True if p and q name the same file however they are spelled: case,
    relative or absolute, long-path or UNC prefixes, hardlinks."""
    try:
        if os.path.normcase(str(p.resolve())) == os.path.normcase(str(q.resolve())):
            return True
    except OSError:
        pass
    try:
        return p.exists() and q.exists() and os.path.samefile(p, q)
    except OSError:
        return False


DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}


def plan_outputs(args, src_path):
    """Every file this run will write, checked before anything is written.

    Refuses (LintError, exit 2) an output that is the input picture, two
    outputs on one file, a picture output that is not .png, a directory, or
    a folder that does not exist - so a refused run writes nothing at all."""
    outs = []
    for flag, value in (("--json", args.json), ("--overlay", args.overlay),
                        ("--fix", args.fix), ("--kla", args.kla)):
        if value:
            outs.append((flag, Path(value)))
    if args.fix:
        outs.append(("--fix (its .diff.png)", Path(args.fix).with_suffix(".diff.png")))
    for flag, path in outs:
        if ":" in path.name:
            raise LintError(f"{flag} {path}: a ':' in the file name writes an NTFS "
                            "alternate data stream; choose a plain file name")
        if path.name.split(".")[0].upper() in DEVICE_NAMES:
            raise LintError(f"{flag} {path}: {path.name.split('.')[0]} is a Windows "
                            "device name, not a file; choose another name")
        if flag in ("--fix", "--overlay") and path.suffix.lower() != ".png":
            raise LintError(f"{flag} {path}: must be a .png file")
        if path.is_dir():
            raise LintError(f"{flag} {path}: is a directory")
        if not path.resolve().parent.is_dir():
            raise LintError(f"{flag} {path}: folder {path.resolve().parent} does not exist")
        if _same_file(path, src_path):
            raise LintError(f"{flag} {path}: that is the input picture - c64lint never "
                            "writes over your picture; choose another name")
    for (f1, p1), (f2, p2) in itertools.combinations(outs, 2):
        if _same_file(p1, p2):
            raise LintError(f"{f1} and {f2} both write {p2}; give them different names")
    return dict(outs)


def _png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _commit(files):
    """Write every (path, bytes) or none of them.

    Each file goes to a temporary name next to its target first; only when
    all of them are on disk are they renamed into place. A failure removes
    the temporaries and leaves any older outputs exactly as they were."""
    temps = []
    try:
        for path, data in files:
            tmp = path.with_name(path.name + ".c64lint-tmp")
            tmp.write_bytes(data)
            temps.append((tmp, path))
        for tmp, path in temps:
            os.replace(tmp, path)
    except OSError as e:
        for tmp, _ in temps:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise LintError(f"could not write {path}: {e}") from None


def _prepare(label, make):
    try:
        return make()
    except (OSError, ValueError) as e:
        raise LintError(f"could not prepare {label}: {e}") from None


def _shell_line(cmd):
    return subprocess.list2cmdline(cmd) if os.name == "nt" else shlex.join(cmd)


def _run_png2prg(exe, then_args, png_path, width):
    """png2prg only reads 320x200: a 160-wide multicolour picture is handed
    over as a pixel-doubled temporary copy, which is removed afterwards."""
    with tempfile.TemporaryDirectory(prefix="c64lint-") as tmpdir:
        target = png_path
        if width == 160:
            target = Path(tmpdir) / (Path(png_path).stem + "-320.png")
            with Image.open(png_path) as img:
                img.convert("RGB").resize((320, 200), Image.NEAREST).save(target)
            print("[*] png2prg reads 320x200 only: passing it a pixel-doubled copy")
        cmd = [exe, *then_args, str(target)]
        print(f"[*] running {_shell_line(cmd)}")
        try:
            result = subprocess.run(cmd)
        except OSError as e:
            raise LintError(f"could not start png2prg ({exe}): {e}") from None
    if result.returncode != 0:
        raise Png2prgError(f"png2prg failed with exit code {result.returncode} "
                           "(see its output above)")


def check(args, then_args):
    if then_args and not args.then:
        raise LintError("arguments after -- are only used with --then png2prg")
    if args.kla and args.mode != "mc":
        raise LintError("--kla writes Koala, which is multicolour; hires output: "
                        "use --then png2prg")
    exe = None
    if args.then:                       # before anything is read or written
        exe = shutil.which("png2prg")
        if exe is None:
            raise LintError(f"png2prg not found on PATH - get it from {PNG2PRG_URL}")
    src_path = Path(args.png)
    outs = plan_outputs(args, src_path)
    img, notes = load_png(src_path)
    if args.bg is not None and args.mode == "hires":
        notes.append("--bg ignored: hires has no shared background colour")
        args.bg = None
    a = analyse(img, args.mode, args.palette, args.bg)
    notes = notes + a.notes
    print_report(a, src_path, args.palette is not None, args.bg is not None, notes)

    # build every output in memory first; nothing touches the disk until all
    # of them exist, so an error leaves no half-written set behind
    files, wrote = [], []
    if args.json:
        text = json.dumps(report_json(a, src_path, notes), indent=1) + "\n"
        files.append((outs["--json"], text.encode("utf-8")))
        wrote.append(args.json)
    if args.overlay:
        files.append((outs["--overlay"], _prepare("--overlay", lambda: _png_bytes(overlay(a, img)))))
        wrote.append(args.overlay)

    clean_png = src_path if a.clean else None
    clean_logical = a.logical if a.clean else None
    if args.fix:
        fl = fixed_logical(a)
        fixed = render(a, fl)
        files.append((outs["--fix"], _prepare("--fix", lambda: _png_bytes(fixed))))
        diff_path = outs["--fix (its .diff.png)"]
        cell_px = a.cell_w * (a.size[0] // a.lw)        # cell width in input pixels
        files.append((diff_path, _prepare(
            "--fix", lambda: _png_bytes(diff_image(img, fixed, cell_px)))))
        wrote.append(f"{args.fix} and {diff_path}")
        n_px, n_cells = diff_stats(img, fixed, cell_px)
        clean_png = clean_png or Path(args.fix)
        clean_logical = clean_logical or fl

    kla_skipped = False
    if args.kla:
        if clean_logical is None:
            kla_skipped = True
        else:
            data = _prepare("--kla", lambda: encode_koala(a, clean_logical, a.bg))
            files.append((outs["--kla"], data))
            wrote.append(args.kla)

    _commit(files)
    for w in wrote:
        print(f"[*] wrote {w}")
    if args.fix and n_px == 0:
        print(f"[*] nothing to fix: the picture is already clean, so {args.fix} is "
              "the same picture")
    elif args.fix:
        print(f"[*] the fix changed {n_px} screen pixel(s) in {n_cells} cell(s); "
              f"{outs['--fix (its .diff.png)']} shows them framed, with a zoom underneath")
    if kla_skipped:
        print("[!] --kla not written: the picture is not clean; add --fix to "
              "write the fixed picture as Koala")

    if args.then:
        if clean_png is None:
            print("[!] png2prg not run: the picture is not clean; add --fix to run it "
                  "on the fixed picture")
        else:
            _run_png2prg(exe, then_args, clean_png, a.size[0])
    return 0 if a.clean else 1


if __name__ == "__main__":
    sys.exit(main())
