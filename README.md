# c64lint

**Find out why your C64 picture won't convert - and the smallest fix.**

You drew a picture in Aseprite, Photoshop or GIMP for the C64. The converter
says *too many colours*, or picks a background colour you never meant, or
draws a red box and leaves you to guess. c64lint tells you:

- **which cells** break the multicolour or hires colour limit,
- **which colour** in each cell is the one too many,
- **the cheapest fix** - the fewest, least visible pixel changes - as a
  picture you can look at before you accept it,
- **which background colour ($d021)** suits the picture, ranked, with the
  cost of each choice,
- **which palette** you drew in, and every colour that is *nearly* right
  (the classic "same palette but wrong colours!" problem).

It is a checker, not a converter. When the picture is clean it hands it to
[png2prg](https://github.com/staD020/png2prg), or writes a Koala file itself.

![overlay](docs/overlay-example.png)

*Overlay of `examples/02-bird-clash.png`: the broken cell framed red, the
surplus pixel marked magenta, everything that is fine dimmed.*

## Quick start

```
c64lint check examples/02-bird-clash.png --mode mc
```

```
[*] examples/02-bird-clash.png: 320x200 multicolour, palette pepto-pal (detected)
[*] background ranking: 6 blue (1 bad, cost 39.43), 7 yellow (1 bad, cost 39.43), 1 white (1 bad, cost 39.43), 2 red (1 bad, cost 39.43), 0 black (1 bad, cost 51.33)
[*] background: 6 blue (best)
[!] cell (28,3) at x=224 y=24: 6 blue x18, 7 yellow x8, 2 red x4, 0 black x1, 1 white x1; surplus: 0 black; fix repaints 1 C64 pixel(s)
[!] NOT CLEAN: 1 broken cell(s)
```

See what is wrong, and what the fix would change:

```
c64lint check pic.png --mode mc --overlay problems.png --fix fixed.png
```

`fixed.png` is your picture with the cheapest fix applied; `fixed.diff.png`
shows before and after side by side, with only the changed pixels lit.

**Your picture is never written to.** Every output path is checked before
anything is written: one that names your input - by any spelling, a
different case, a UNC or `\\?\` path, a hardlink - is refused, as are two
outputs on the same file or a folder that does not exist. A refused run
writes nothing.

Then build it:

```
c64lint check pic.png --mode mc --fix fixed.png --kla pic.kla
c64lint check pic.png --mode mc --fix fixed.png --then png2prg -- -d -o pic.prg
```

## What it checks, in order

1. **Palette.** Matches every colour against 15 known C64 palettes (the ones
   VICE ships, plus Colodore) and picks the closest. Colours that are not an
   exact palette entry are reported with their nearest C64 colour and how far
   off they are (CIE dE). Force one with `--palette`; list them with
   `c64lint palettes`.
2. **Pixel pairs** (multicolour at 320 wide). Multicolour pixels are two
   screen pixels wide. A pair with two different colours is a hires pixel
   that slipped in.
3. **Background.** All 16 colours are tried; each costs whatever fixing the
   whole picture with it would cost. The ranking is printed; the cheapest is
   used unless you give `--bg N`. A single broken cell can often be "fixed" by
   choosing one of its own colours as background - if the ranking surprises
   you, that is usually why, and `--bg` puts you in charge.
4. **Cells.** Multicolour: each 4x8 cell may hold the background + 3 colours.
   Hires: each 8x8 cell may hold 2 colours.

## How the fix decides

For a broken cell, every allowed set of colours is tried and the one with the
smallest total *visible* change wins. Visible means the colour difference as
the eye sees it (CIE Lab), not raw RGB, so a stray dark blue turns dark grey,
not yellow. Each removed pixel goes to its nearest kept colour.

- Cells that were already fine are never touched.
- No dithering is added.
- Same input, same options: byte-identical output.
- A fix only uses colours already in the cell, plus the background colour,
  which every multicolour cell can show anyway (bit pair 00). Repainting a
  stray pixel to the background is often the cheapest fix.

Pixel counts in the report are C64 pixels (one multicolour pixel = two screen
pixels).

## Options

| Option | |
|---|---|
| `--mode mc` / `--mode hires` | Required. Multicolour takes 160x200 or 320x200, hires 320x200 |
| `--palette NAME` | Use this palette instead of detecting one |
| `--bg N` | Background colour 0-15 (multicolour only). Skips costing the other 15, which is much faster on busy pictures |
| `--overlay OUT.png` | Problems drawn over your picture, 5x size |
| `--json OUT.json` | Everything in the report, machine-readable |
| `--fix OUT.png` | Cheapest fix, plus `OUT.diff.png`: before and after side by side |
| `--kla OUT.kla` | Koala file (multicolour). Written only from a clean result |
| `--then png2prg -- ARGS` | Run png2prg with ARGS on the clean result |

"Clean result" means: your picture if it passed, otherwise the `--fix`
picture. Without `--fix` a picture that fails gets no Koala file and no png2prg
run - c64lint never builds from something it just told you is broken.

Exit codes: `0` clean, `1` problems found (even if `--fix` fixed them), `2`
bad input or bad options. Use it in a makefile in front of png2prg.

## Input

PNG only: RGB, RGBA, greyscale (8 or 16 bit) or indexed. Transparent pixels
are refused - the C64 has no transparency, so flatten onto your background
first. A picture with more than 256 different colours is refused too: that
is a photo or a scaled image, so convert it to C64 colours first (Dithertron,
Retropixels) and check the result. An animated PNG is checked on its first
frame, with a warning.

## Examples

`examples/` has five small pictures, each broken in one typical way. Try:

```
c64lint check examples/02-bird-clash.png --mode mc --overlay ov.png --fix fixed.png
```

## Not (yet) covered

FLI/AFLI, sprites, charsets, reading .kla/.art files, writing hires files
(use `--then png2prg`).

## Install

Download the zip from the releases page: one file for Windows, one for Linux,
nothing to install. Or run the source with Python 3.10+ and Pillow:

```
pip install pillow
python c64lint.py check pic.png --mode mc
```

## Credits

Code: DR.J/Delysid. Palette values from the palette files shipped with
[VICE](https://vice-emu.sourceforge.io/), and Colodore by Pepto. png2prg by
Burglar - the tool to build your picture with once c64lint is happy.

MIT licence.
