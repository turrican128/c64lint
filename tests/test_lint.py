import json

from PIL import Image

import c64lint
from conftest import PEPTO, anchored, make_png, mc_cell


# ---------- palette ----------------------------------------------------------

def test_palette_detected(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [1, 2]))
    code, out = run("check", p, "--mode", "mc")
    assert code == 0
    assert "pepto-pal" in out


def test_palette_detects_colodore(tmp_path, run):
    pal = c64lint.PALETTES["colodore"]
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [2, 3, 4]), palette=pal)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert code == 0
    assert json.loads((tmp_path / "r.json").read_text())["palette"] == "colodore"


def test_off_palette_colour_is_a_finding(tmp_path, run):
    r, g, b = PEPTO[14]
    p = make_png(tmp_path / "a.png", 160, 200, 0, {(40, 12): (r, g, b + 1)})
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert code == 1
    rep = json.loads((tmp_path / "r.json").read_text())
    assert len(rep["off_palette"]) == 1
    op = rep["off_palette"][0]
    assert op["nearest"] == 14 and op["count"] == 1 and op["first"] == [40, 12]
    assert "off-palette" in out


def test_forced_palette(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6)
    code, out = run("check", p, "--mode", "mc", "--palette", "deekay",
                    "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["palette"] == "deekay"
    assert code == 1  # pepto blue is not an exact deekay entry


def test_unknown_palette_is_usage_error(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200)
    code, out = run("check", p, "--mode", "mc", "--palette", "nope")
    assert code == 2


def test_palettes_command(run):
    code, out = run("palettes")
    assert code == 0
    for name in ("pepto-pal", "colodore", "vice", "deekay"):
        assert name in out


# ---------- pixel pairs ------------------------------------------------------

def test_pair_mismatch_found_at_320(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0, {(11, 5): 1})
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert code == 1
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["pairs"] == [{"x": 10, "y": 5, "colours": [0, 1]}]


def test_no_pair_check_at_160(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 0, {(11, 5): 1})
    code, _ = run("check", p, "--mode", "mc")
    assert code == 0


# ---------- cells and background --------------------------------------------

def test_clean_mc_picture(tmp_path, run):
    px = {}
    px.update(mc_cell(0, 0, [1, 2, 3]))
    px.update(mc_cell(5, 7, [4, 5, 7]))
    p = make_png(tmp_path / "a.png", 320, 200, 6, px)
    code, out = run("check", p, "--mode", "mc")
    assert code == 0
    assert "CLEAN" in out


def test_broken_mc_cell(tmp_path, run):
    # background 6 everywhere, one cell with 4 non-background colours
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert code == 1
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["bg"] == 6
    assert len(rep["cells"]) == 1
    cell = rep["cells"][0]
    assert (cell["cx"], cell["cy"]) == (3, 2)
    assert sorted(int(k) for k in cell["colours"]) == [1, 2, 3, 4]
    assert len(cell["surplus"]) == 1
    assert cell["fix"]["changed"] == 8  # one colour of 8 logical pixels
    assert "cell (3,2)" in out


def test_background_ranking_prefers_cheapest(tmp_path, run):
    # cells all contain black + 3 colours; black must be the background
    px = {}
    for cx in range(0, 40, 3):
        px.update(mc_cell(cx, 0, [0, 1, 2, 3]))
        px.update(mc_cell(cx, 1, [0, 4, 5, 7]))
    p = make_png(tmp_path / "a.png", 320, 200, 0, px)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert code == 0
    assert rep["bg"] == 0
    assert rep["bg_ranking"][0] == {"bg": 0, "cost": 0.0, "bad_cells": 0}
    assert rep["bg_ranking"][1]["bad_cells"] > 0


def test_forced_bg(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, mc_cell(0, 0, [6, 1, 2, 3]))
    code, out = run("check", p, "--mode", "mc", "--bg", "0",
                    "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["bg"] == 0
    assert code == 1  # with bg 0 the cell holds 6,1,2,3 = 4 non-bg colours


def test_single_broken_cell_is_ambiguous(tmp_path, run):
    # one cell of 1,2,3,4 on blue: any of 1..4 as background makes it legal,
    # so the cheapest background is not blue -- and the report must say so
    p = make_png(tmp_path / "a.png", 320, 200, 6, mc_cell(3, 2, [1, 2, 3, 4]))
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert code == 0
    assert rep["bg"] in (1, 2, 3, 4)


def test_zero_cost_tie_prefers_most_used_colour(tmp_path, run):
    # blue picture with one clean cell: black, white, red, cyan and blue all
    # cost nothing; blue covers most pixels so it wins
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(2, 2, [1, 2, 3], wide=False))
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert code == 0 and rep["bg"] == 6


def test_bg_ignored_in_hires(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0)
    code, out = run("check", p, "--mode", "hires", "--bg", "3")
    assert code == 0
    assert "[!]" in out and "--bg" in out


def test_hires_broken_cell(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0, {(9, 1): 1, (10, 1): 2})
    code, out = run("check", p, "--mode", "hires", "--json", tmp_path / "r.json")
    assert code == 1
    rep = json.loads((tmp_path / "r.json").read_text())
    assert [(c["cx"], c["cy"]) for c in rep["cells"]] == [(1, 0)]
    assert rep["cells"][0]["fix"]["changed"] == 1


def test_hires_two_colours_clean(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0, {(9, 1): 1, (100, 100): 2})
    code, _ = run("check", p, "--mode", "hires")
    assert code == 0


# ---------- refused input ----------------------------------------------------

def test_wrong_size(tmp_path, run):
    p = make_png(tmp_path / "a.png", 100, 100)
    code, out = run("check", p, "--mode", "mc")
    assert code == 2 and "!!" in out


def test_hires_rejects_160(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200)
    code, _ = run("check", p, "--mode", "hires")
    assert code == 2


def test_alpha_rejected(tmp_path, run):
    img = Image.new("RGBA", (160, 200), (0, 0, 0, 255))
    img.putpixel((3, 3), (0, 0, 0, 0))
    img.save(tmp_path / "a.png")
    code, out = run("check", tmp_path / "a.png", "--mode", "mc")
    assert code == 2 and "transparent" in out


def test_opaque_rgba_accepted(tmp_path, run):
    Image.new("RGBA", (160, 200), PEPTO[6] + (255,)).save(tmp_path / "a.png")
    code, _ = run("check", tmp_path / "a.png", "--mode", "mc")
    assert code == 0


def test_indexed_png_accepted(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [1, 2]), mode="P")
    code, _ = run("check", p, "--mode", "mc")
    assert code == 0


def test_truncated_png(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [1, 2, 3]))
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    code, out = run("check", p, "--mode", "mc")
    assert code == 2 and "!!" in out


def test_not_a_png(tmp_path, run):
    p = tmp_path / "a.png"
    p.write_bytes(b"hello")
    code, out = run("check", p, "--mode", "mc")
    assert code == 2


def test_jpeg_refused(tmp_path, run):
    p = tmp_path / "a.png"
    Image.new("RGB", (160, 200)).save(p, format="JPEG")
    code, out = run("check", p, "--mode", "mc")
    assert code == 2 and "PNG" in out


def test_missing_file(tmp_path, run):
    code, out = run("check", tmp_path / "nope.png", "--mode", "mc")
    assert code == 2


def test_missing_mode_is_usage_error(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200)
    code, _ = run("check", p)
    assert code == 2
