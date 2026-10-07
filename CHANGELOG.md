# Changelog

## 0.1.0

First version.

- Checks PNG pictures against C64 multicolour and hires bitmap rules.
- Detects the palette (15 built in) and reports near-miss colours.
- Finds split multicolour pixel pairs.
- Ranks all 16 background colours by fix cost.
- Explains each broken cell: its colours, the surplus one, the cheapest fix.
- `--fix`, `--overlay`, `--json`, `--kla`, `--then png2prg`.
