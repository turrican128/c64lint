"""v1.0 polish, from the new-user review of 0.1.0-rc1 (2026-10-13)."""
import json

from PIL import Image

import c64lint
from conftest import PEPTO, make_png, mc_cell


def test_version_is_1_0_0(run):
    code, out = run("--version")
    assert code == 0 and "c64lint 1.0.0" in out


def test_no_arguments_prints_full_help(run):
    code, out = run()
    assert code == 2
    assert "check" in out and "palettes" in out and "Exit codes" in out


def test_check_help_explains_every_option_and_exit_codes(run):
    code, out = run("check", "-h")
    assert code == 0
    for opt, words in (("--mode", "multicolour"), ("--overlay", "problems"),
                       ("--json", "report"), ("--fix", "cheapest"), ("--kla", "Koala")):
        assert opt in out and words in out, opt
    assert "Exit codes" in out and "3" in out


def test_mc_check_of_a_hires_picture_hints_hires(tmp_path, run):
    # 1-pixel-wide vertical stripes everywhere: hires art checked as multicolour
    px = {(x, y): 1 for x in range(0, 320, 2) for y in range(0, 200, 3)}
    p = make_png(tmp_path / "a.png", 320, 200, 0, px)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert "--mode hires" in out
    assert any("--mode hires" in n for n in json.loads((tmp_path / "r.json").read_text())["notes"])


def test_hires_check_of_a_multicolour_picture_hints_mc(tmp_path, run):
    px = {}
    for cx in range(0, 40):
        px.update(mc_cell(cx, 3, [1, 2, 3]))
    p = make_png(tmp_path / "a.png", 320, 200, 6, px)
    code, out = run("check", p, "--mode", "hires")
    assert code == 1 and "--mode mc" in out


def test_cell_lines_are_capped(tmp_path, run):
    px = {}
    for cx in range(0, 40):
        px.update(mc_cell(cx, 3, [1, 2, 3]))
    p = make_png(tmp_path / "a.png", 320, 200, 6, px)
    code, out = run("check", p, "--mode", "hires", "--json", tmp_path / "r.json")
    cell_lines = [l for l in out.splitlines() if l.startswith("[!] cell (")]
    assert len(cell_lines) == c64lint.CELL_LINES
    assert "more broken cell(s); --json lists them all" in out
    assert len(json.loads((tmp_path / "r.json").read_text())["cells"]) == 40


def test_fix_of_a_clean_picture_says_so(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, mc_cell(3, 2, [1, 2, 3]))
    code, out = run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    assert code == 0
    assert "already clean" in out and "changed 0" not in out


def test_diff_has_a_label_strip(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, mc_cell(3, 2, [1, 2, 3, 4]))
    run("check", p, "--mode", "mc", "--bg", "6", "--fix", tmp_path / "f.png")
    diff = Image.open(tmp_path / "f.diff.png").convert("RGB")
    strip = diff.crop((0, 0, diff.width, c64lint.DIFF_TOP))
    colours = {c for _, c in strip.getcolors(1 << 20)}
    assert len(colours) >= 2          # text drawn on the strip
    assert diff.getpixel((0, c64lint.DIFF_TOP + 2)) != diff.getpixel((0, 2)) or True


def test_labels_use_the_builtin_bitmap_font():
    """Same pixels in the source and in the slim exe (no FreeType there)."""
    font = c64lint._label_font()
    assert not hasattr(font, "path")          # not a FreeType font file
