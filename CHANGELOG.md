# Changelog

## 1.0.0 (2026-10-13)

First release. (0.1.0-rc1 was a release candidate on GitHub only.)

- Checks PNG pictures against C64 multicolour and hires bitmap rules.
- Detects the palette (15 built in) and reports near-miss colours.
- Finds split multicolour pixel pairs.
- Ranks all 16 background colours by fix cost.
- Explains each broken cell: its colours, the surplus one, the cheapest fix.
- `--fix`, `--overlay`, `--json`, `--kla`, `--then png2prg`.
- No output can overwrite the input picture, by any spelling of its path.
- Warns when the cheapest background is not the picture's main colour, and
  says what `--bg` with that colour would cost.
- `--then png2prg` works with 160-wide pictures (png2prg gets a
  pixel-doubled copy).
- Outputs are all-or-nothing; exit code 3 when png2prg fails.
- `.diff.png` frames every changed cell and adds a zoom of the changed area.
- Labelled `.diff.png` (BEFORE / AFTER, zoom captions); every changed pixel
  outlined or ringed.
- Hints when the mode looks wrong (`--mode hires` vs `--mode mc`).
- Help text for every option; exit codes in `-h`; no arguments prints help.
- Long lists of broken cells are capped on screen (`--json` has them all).

