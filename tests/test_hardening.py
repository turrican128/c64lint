"""Findings from the first external QA pass (2026-10-07). Each test failed
before its fix. The output-path tests guard the one promise that matters most:
c64lint never writes over the picture you gave it."""
import itertools
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

import c64lint
from conftest import PEPTO, anchored, make_png, mc_cell

ROOT = Path(__file__).resolve().parent.parent


def broken(tmp_path, name="in.png"):
    return make_png(tmp_path / name, 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))


# ---------- 1-3, 9: no output may hit the input or another output ------------

@pytest.mark.parametrize("flag", ["--overlay", "--json", "--kla", "--fix"])
def test_no_output_may_be_the_input(tmp_path, run, flag):
    p = broken(tmp_path)
    before = p.read_bytes()
    code, out = run("check", p, "--mode", "mc", flag, p)
    assert code == 2 and "!!" in out
    assert p.read_bytes() == before


def test_diff_file_may_not_be_the_input(tmp_path, run):
    p = broken(tmp_path, "bird.diff.png")
    before = p.read_bytes()
    code, out = run("check", p, "--mode", "mc", "--fix", tmp_path / "bird.png")
    assert code == 2
    assert p.read_bytes() == before
    assert not (tmp_path / "bird.png").exists()


def test_hardlink_to_input_refused(tmp_path, run):
    p = broken(tmp_path)
    link = tmp_path / "link.png"
    os.link(p, link)
    before = p.read_bytes()
    code, _ = run("check", p, "--mode", "mc", "--fix", link)
    assert code == 2
    assert p.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Windows path spellings")
def test_long_path_spelling_of_input_refused(tmp_path, run):
    p = broken(tmp_path)
    before = p.read_bytes()
    code, _ = run("check", p, "--mode", "mc", "--fix", "\\\\?\\" + str(p.resolve()))
    assert code == 2
    assert p.read_bytes() == before


def test_two_outputs_on_one_path_refused(tmp_path, run):
    p = broken(tmp_path)
    code, out = run("check", p, "--mode", "mc", "--fix", tmp_path / "x.png",
                    "--overlay", tmp_path / "x.png")
    assert code == 2
    assert not (tmp_path / "x.png").exists()


def test_overlay_on_diff_path_refused(tmp_path, run):
    p = broken(tmp_path)
    code, _ = run("check", p, "--mode", "mc", "--fix", tmp_path / "x.png",
                  "--overlay", tmp_path / "x.diff.png")
    assert code == 2


@pytest.mark.parametrize("flag,name", [("--fix", "out.jpg"), ("--fix", "noext"),
                                       ("--overlay", "o.gif")])
def test_picture_outputs_must_be_png(tmp_path, run, flag, name):
    p = broken(tmp_path)
    code, out = run("check", p, "--mode", "mc", flag, tmp_path / name)
    assert code == 2 and ".png" in out


# ---------- 7: unwritable outputs: clean error, nothing half-written ----------

def test_missing_output_dir_is_exit_2_and_writes_nothing(tmp_path, run):
    p = broken(tmp_path)
    code, out = run("check", p, "--mode", "mc", "--overlay", tmp_path / "o.png",
                    "--json", tmp_path / "nodir" / "r.json")
    assert code == 2 and "!!" in out and "Traceback" not in out
    assert not (tmp_path / "o.png").exists()


def test_directory_as_output_is_exit_2(tmp_path, run):
    p = broken(tmp_path)
    (tmp_path / "adir.png").mkdir()
    code, out = run("check", p, "--mode", "mc", "--overlay", tmp_path / "adir.png")
    assert code == 2 and "Traceback" not in out


def test_directory_as_input_says_so(tmp_path, run):
    d = tmp_path / "pic.png"
    d.mkdir()
    code, out = run("check", d, "--mode", "mc")
    assert code == 2 and "directory" in out


# ---------- 4: 16-bit greyscale -------------------------------------------------

def test_16bit_greyscale_scaled_not_clipped(tmp_path, run):
    img = Image.new("I;16", (320, 200), 108 * 257)
    for y in range(200):
        for x in range(160):
            img.putpixel((x, y), 68 * 257)
    img.save(tmp_path / "g16.png")
    code, out = run("check", tmp_path / "g16.png", "--mode", "hires",
                    "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert "#FFFFFF" not in out
    # grey 108 and dark grey 68 are pepto entries 12 and 11
    assert code == 0 and rep["palette"] == "pepto-pal"


# ---------- 5: coordinates are input pixels in every geometry ------------------

def test_cell_x_at_160_wide(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6,
                 anchored_160(mc_cell(10, 5, [1, 2, 3, 4], wide=False)))
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    cell = json.loads((tmp_path / "r.json").read_text())["cells"][0]
    assert (cell["cx"], cell["x"], cell["y"]) == (10, 40, 40)
    assert "at x=40 y=40" in out


def anchored_160(px):
    out = dict(px)
    for i in range(3):
        out.update(mc_cell(30 + i, 20, [6, 5, 7, 8], wide=False))
        out.update(mc_cell(30 + i, 21, [6, 9, 10, 12], wide=False))
    return out


# ---------- 6: the fix is the cheapest, also in noisy cells ---------------------

def test_fix_is_cheapest_even_with_many_colours():
    rnd = random.Random(3)
    de = c64lint.palette_de(PEPTO)
    for _ in range(300):
        n = rnd.randrange(11, 17)
        colours = rnd.sample(range(16), n)
        counts = [1] * n
        for _ in range(32 - n):
            counts[rnd.randrange(n)] += 1
        hist = tuple(sorted(zip(colours, counts)))
        bg = rnd.randrange(16)
        cost, keep = c64lint.best_set(hist, bg, de)
        pool = [c for c in colours if c != bg]
        brute = min(
            sum(cnt * min(de[c][k] for k in s + (bg,)) for c, cnt in hist)
            for s in itertools.combinations(sorted(pool), 3))
        assert abs(cost - brute) < 1e-6


# ---------- 8: non-ASCII paths with redirected output ---------------------------

def test_unicode_path_with_redirected_stdout(tmp_path):
    d = tmp_path / "dir ש"
    d.mkdir()
    p = make_png(d / "pic ü.png", 160, 200, 6)
    env = dict(os.environ, PYTHONIOENCODING="cp1255")
    r = subprocess.run([sys.executable, str(ROOT / "c64lint.py"), "check", str(p),
                        "--mode", "mc"], capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode(errors="replace")


# ---------- 10: photos are refused, not listed colour by colour -----------------

def test_photo_like_input_refused_quickly(tmp_path, run):
    rnd = random.Random(5)
    img = Image.new("RGB", (160, 200))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(160 * 200)])
    img.save(tmp_path / "photo.png")
    code, out = run("check", tmp_path / "photo.png", "--mode", "mc")
    assert code == 2
    assert "colours" in out and len(out.splitlines()) < 10


def test_off_palette_console_list_is_capped(tmp_path, run):
    px = {(x, 0): (100 + x, 3, 7) for x in range(40)}   # in no palette
    p = make_png(tmp_path / "a.png", 160, 200, 0, px)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert code == 1
    assert len([l for l in out.splitlines() if "off-palette #" in l]) <= 10
    assert len(json.loads((tmp_path / "r.json").read_text())["off_palette"]) == 40


# ---------- 13: nits -------------------------------------------------------------

def test_header_comes_first(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0)
    _, out = run("check", p, "--mode", "hires", "--bg", "3")
    assert out.splitlines()[0].startswith("[*] ")


def test_animated_png_warns(tmp_path, run):
    a = Image.new("RGB", (160, 200), PEPTO[6])
    b = Image.new("RGB", (160, 200), PEPTO[1])
    a.save(tmp_path / "anim.png", save_all=True, append_images=[b])
    code, out = run("check", tmp_path / "anim.png", "--mode", "mc")
    assert "[!]" in out and "frame" in out


def test_huge_png_refused_before_decoding(tmp_path, run):
    Image.new("1", (12000, 8000)).save(tmp_path / "big.png")
    code, out = run("check", tmp_path / "big.png", "--mode", "mc")
    assert code == 2 and "12000x8000" in out


def test_double_dash_without_then_is_a_filename_separator(tmp_path, run, monkeypatch):
    p = make_png(tmp_path / "-pic.png", 160, 200, 6)
    monkeypatch.chdir(tmp_path)
    code, _ = run("check", "--mode", "mc", "--", "-pic.png")
    assert code == 0
