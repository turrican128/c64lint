# c64lint — design

Date: 2026-10-07. Status: approved in conversation (sections 1–3), written up here.

## Why

Artists increasingly draw C64 pictures in Aseprite or Photoshop. When the
picture breaks the C64 mode rules, today's tools either stop (png2prg prints a
cell coordinate), silently pick an unwanted background colour (SPOT, auto
detection in general), or draw red boxes. None says *which* colour is surplus,
*why*, or *what the smallest fix is*. CSDb threads have asked for this since
2012 (forum topic 89784) and it still bites in 2025 (SPOT 1.3 comments).

c64lint is that missing step. It **complements png2prg, never replaces it**:
it does its own analysis and can hand a clean picture to png2prg.

## Scope (v1)

In: bitmap multicolour (`--mode mc`) and bitmap hires (`--mode hires`), PNG
input, report, overlay, JSON, `--fix`, Koala output, png2prg hand-off.

Out (later): FLI/AFLI, sprites, charsets, reading .kla/.art input, hires file
output (use `--then png2prg`), dithering.

## Input

- PNG only. Indexed, greyscale, RGB and RGBA without transparency are
  converted to RGB. Any pixel with alpha < 255 → error.
- `mc`: 160×200, or 320×200 where pixels are meant in horizontal pairs.
- `hires`: 320×200.
- Any other size, unreadable/truncated file, or non-PNG → error.

## Checks (in this order)

1. **Palette.** Built-in palettes taken from VICE's `.vpl` files plus
   Colodore. For each palette, score = sum over distinct image colours of the
   distance to the nearest palette entry. Lowest score wins (ties → list
   order). `--palette NAME` forces one. Every distinct colour that is not an
   exact entry of the chosen palette is a finding ("off-palette"), reported
   with its nearest entry and ΔE. Colours further than ΔE 20 from every entry
   get an extra warning that this may not be C64 art.
2. **Pixel pairs** (`mc` at 320 wide only). Each horizontal pair (x even,
   x+1) whose two pixels differ (after palette snapping) is a finding.
3. **Background ($d021)** (`mc` only). For each of the 16 colours, cost =
   sum of minimal fix costs over all cells with that background. Ranked
   by cost, then fewer bad cells, then more pixels of that colour in the
   picture, then palette index. (A lone broken cell can usually be made
   legal by picking one of its own colours as background; the pixel-count
   tie-break keeps a blue picture from reporting "background: black" when
   several backgrounds cost nothing.) Best wins unless `--bg N` is given. The
   report shows the top 5. `--bg` in hires mode → warning, ignored.
4. **Cells.** `mc`: 4×8 logical pixels, at most background + 3 colours.
   `hires`: 8×8 pixels, at most 2 colours. A cell over the limit is a finding
   listing its colours by pixel count, the surplus colour(s), and the
   cheapest fix (below).

All colour distances are CIE76 ΔE in CIE Lab of the palette's sRGB values.

## Fix algorithm (`--fix`)

Applied in order, on the working copy:

1. Snap every off-palette colour to its nearest palette entry.
2. (`mc` at 320) For each mismatched pair, both pixels take the colour with
   more pixels in that cell; tie → lower palette index.
3. Choose the background (step 3 above; same cost function, so the ranking
   and the fix always agree).
4. For each cell over the limit: try every allowed colour set (mc: every
   3-subset of the cell's non-background colours, plus background; hires:
   every pair of the cell's colours — if the cell has one colour it is never
   over the limit). Cost of a set = sum over the cell's pixels of ΔE to the
   nearest set colour. Keep the cheapest; ties → lexicographically smallest
   sorted index tuple. Repaint each pixel to its nearest set colour (ties →
   lower index).

Guarantees: clean cells are untouched; no dithering; the same input and
options give byte-identical output. The search is always exhaustive (QA
found a swap-search shortcut up to dE 85 off in noisy cells); candidates
are the cell's own colours plus, in multicolour, the background (second
review, 2026-10-07: the README had wrongly promised no new colours).
A forced --bg skips costing the other 15 backgrounds (33 s -> 1.5 s on
noise). The cell-fix memo lives for one analysis, never process-wide.

Third review (2026-10-12, QA agent + real png2prg 1.12 + Alex's manual test):
- 160-wide pictures go to png2prg as a pixel-doubled temporary copy (it
  reads 320x200 only).
- A colour exact in any built-in palette keeps its number under a forced
  --palette; colours that collapse to one number are reported in notes.
- Background hint: when the auto background is not the most-used colour,
  say so and give the cost of --bg <that colour>.
- Outputs are built in memory and committed via temp files + os.replace:
  exit 2 writes nothing and keeps older outputs. png2prg presence is checked
  first. png2prg failing = exit 3.
- Refused outputs also include NTFS streams and Windows device names. Input
  is identified by its signature before Pillow opens it. allow_abbrev off;
  --then=png2prg accepted. JSON gains `notes`.
- .diff.png redesigned after Alex's manual test (34 changed pixels were
  specks in a 3220x1000 image): untouched areas grey, touched cells framed
  magenta, zoom panel of the changed area (up to 16x) with outlines on the
  edges of changed areas only; console reports pixels/cells changed.

Output safety (added after QA): every output path, including the derived
`.diff.png`, is checked before anything is written. Same file as the input
(compared by resolved path and by `os.path.samefile`, which covers case,
UNC, long-path and hardlinks), two outputs on one file, a non-.png picture
output, a directory or a missing folder: exit 2, nothing written.

Input limits (added after QA): size checked before decoding; >256 distinct
colours refused as a photo; 16-bit greyscale scaled, not clipped; animated
PNG checked on frame 1 with a warning.

## Command line

```
c64lint check PIC.png --mode {mc,hires} [--palette NAME] [--bg N]
                      [--overlay OUT.png] [--json OUT.json] [--fix OUT.png]
                      [--kla OUT.kla] [--then png2prg -- ARGS...]
c64lint palettes        # list built-in palettes
```

- Console: `[*]` progress/info, `[!]` warnings, `!!` errors; final summary
  line.
- `--overlay`: input scaled x5 (nearest), broken cells framed red outside
  the cell, surplus pixels marked with a magenta corner square, everything
  else dimmed. `--fix` always also writes `<fix>.diff.png`: before and after
  side by side, changed pixels lit.
- `--json`: schema `{"version":1, "file", "mode", "palette", "bg",
  "bg_ranking":[{"bg","cost","bad_cells"}], "off_palette":[...],
  "pairs":[...], "cells":[{"cx","cy","colours":{idx:count},
  "surplus":[...], "fix":{"keep":[...],"changed":n}}], "clean": bool}`.
- `--fix OUT.png`: never the input path (refused with an error). Written at
  the input resolution.
- `--kla OUT.kla` (`mc` only): written from the clean result — the input if
  clean, else the fixed picture if `--fix` was given; otherwise not written
  and a warning says why. Bit-pair assignment per cell: kept colours sorted
  by palette index → %01, %10, %11. Load address $6000.
- `--then png2prg -- ARGS`: same clean-result rule; runs png2prg with ARGS
  and the clean PNG path. If png2prg is not on PATH, error with the download
  URL (github.com/staD020/png2prg).
- Exit codes: 0 input clean, 1 findings (even if fixed), 2 bad input/usage.

## Code and dependencies

Single file `c64lint.py`, Python ≥ 3.10, Pillow only. Palettes embedded.
README credits VICE for the palette files and points to png2prg.

## Testing

pytest, fixtures generated in code: clean mc/hires, one broken cell, pair
mismatch, off-palette colour, tie cases, 16-colour worst case, every refused
input (wrong size, alpha, truncated, not a PNG, `--fix` = input). Golden JSON
for a few fixtures. Round trip: `--fix` + `--kla`, decode the .kla, pixels
equal the fixed PNG. Determinism: two runs byte-identical. If png2prg is on
PATH, it must accept every fixed picture (skipped otherwise). No README
guarantee without a test behind it.

## Release

As txt2dirart: own public repo (Alex creates it), GitHub Actions PyInstaller
one-file binaries for Windows and Linux on `v*` tags, RC tags first and the
artifacts read before v1.0, examples zip of deliberately broken pictures.
Alex submits to CSDb himself.
