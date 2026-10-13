# CSDb submission — c64lint 1.0.0

Everything needed to fill in the "Add release" form at
<https://csdb.dk/additem.php?type=release>. Modelled on the png2prg 1.12
entry (<https://csdb.dk/release/?id=252826>), the closest comparable tool
release, and on txt2dirart's own entry.

**Submit this yourself — under your own CSDb account.**

---

## Form fields

| field | value |
|---|---|
| **Name** | `c64lint 1.0.0` |
| **Type** | `Other Platform C64 Tool` |
| **Released by** | DR.J / Delysid |
| **Release date** | the day you submit |
| **Website** | `https://github.com/turrican128/c64lint` |

### Credits

```
Code  -  DR.J of Delysid
```

Add a `Test` line for anyone who runs it on their own art before you submit.
A tool release with named testers reads as vetted rather than thrown over the
wall, and for a checker of pixel art the best tester is a pixel artist.

### Downloads

Upload both, in this order:

1. **`c64lint-1.0.0.zip`** — from the GitHub `v1.0.0` release (not one of the
   release candidates). Contains `c64lint.exe`, the Linux binary `c64lint`,
   the Python source, README, CHANGELOG, LICENSE and `examples/`.
2. **`c64lint-examples.zip`** — the five example pictures on their own, each
   broken in one typical way, so people can see what the tool reports before
   they point it at their own art.

### Screenshots

Upload both, in this order - the first one becomes the thumbnail:

1. `docs/csdb-screenshot.png` (384x272). The neon-sign test picture before
   (broken cells framed red) and after `--fix` (changed cells framed magenta),
   with the matching report lines, all text in the real C64 character set. It
   is a composed picture, not a capture of a running C64 - c64lint runs on the
   PC.
2. `docs/csdb-terminal.png` (744x442). A console window with the real output
   of `c64lint.exe check examples-bird-clash.png --mode mc --overlay ov.png
   --fix fixed.png` run in `C:\Temp\c64lint-1.0.0`, followed by a re-check of
   `fixed.png` that comes out CLEAN. Text is the 1.0.0 binary's actual output,
   wrapped at 90 columns.

---

## Summary text

CSDb entries for tools are thin. Keep it short and let the README do the
work.

```
c64lint tells you why your C64 picture won't convert - and the smallest fix.

Drew it in Aseprite or Photoshop and the converter says "too many colours",
or picks a background you never meant? c64lint checks a PNG against the
multicolour or hires bitmap rules and shows which cells break them, which
colour in each is the one too many, which background colour suits the
picture (ranked, with the cost of each), hires pixels hiding in multicolour
art, and near-miss RGB values from your editor. --fix writes the cheapest
repair with a before/after picture, so you decide before you accept it.

A checker, not a converter: when the picture is clean it hands it to png2prg,
or writes a Koala file itself. It never writes over your picture.

Command line. Single-file binaries for Windows and Linux; the Python source
is one file.
```

---

## Before you press Submit

- [ ] The `v1.0.0` release on GitHub is marked Latest (not pre-release)
- [ ] You downloaded `c64lint-1.0.0.zip` from it and ran
      `c64lint.exe check examples\02-bird-clash.png --mode mc` from the
      unpacked folder
- [ ] You ran it on one picture of your own
- [ ] Screenshots: `docs/csdb-screenshot.png` (384x272) first, then
      `docs/csdb-terminal.png` (744x442)
- [ ] Optional: a note to Burglar first - c64lint hands its clean pictures to
      png2prg (`--then png2prg`), it is meant to sit next to his tool
