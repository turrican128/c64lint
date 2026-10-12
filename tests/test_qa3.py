"""Third review (2026-10-12): an adversarial QA pass on main 7a48d70 plus an
end-to-end run against the real png2prg 1.12. Each test failed before its fix."""
import json
import os
from pathlib import Path

import pytest
from PIL import Image

import c64lint
from conftest import PEPTO, anchored, make_png, mc_cell


def broken(tmp_path, name="in.png"):
    return make_png(tmp_path / name, 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))


class FakeRun:
    """Stand-in for subprocess.run that records what png2prg would get."""

    def __init__(self, returncode=0):
        self.returncode = returncode
        self.calls = []
        self.seen = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        with Image.open(cmd[-1]) as img:      # look at the file while it exists
            self.seen.append(img.size)
        return self


# ---------- 0. png2prg only reads 320x200 ----------------------------------------

def test_160_wide_is_doubled_for_png2prg(tmp_path, run, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")
    monkeypatch.setattr(c64lint.subprocess, "run", fake)
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(2, 2, [1, 2, 3], wide=False))
    code, out = run("check", p, "--mode", "mc", "--then", "png2prg", "--", "-m", "koala")
    assert code == 0, out
    assert fake.seen == [(320, 200)]
    assert not Path(fake.calls[0][-1]).exists()        # the temporary copy is gone


def test_160_wide_fixed_picture_is_doubled_for_png2prg(tmp_path, run, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")
    monkeypatch.setattr(c64lint.subprocess, "run", fake)
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(2, 2, [1, 2, 3, 4], wide=False))
    run("check", p, "--mode", "mc", "--bg", "6", "--fix", tmp_path / "f.png", "--then", "png2prg")
    assert fake.seen == [(320, 200)]
    assert Image.open(tmp_path / "f.png").size == (160, 200)   # the user's file stays 160


# ---------- 1. a forced palette must not merge colours ---------------------------

def test_forced_palette_keeps_colour_numbers(tmp_path, run):
    # orange 8, brown 9, light grey 15, grey 12 drawn in pepto-pal; colodore
    # forced: nearest-RGB snapping merged 8->9 and 15->12
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [8, 9, 15, 12], wide=False))
    code, out = run("check", p, "--mode", "mc", "--palette", "colodore", "--bg", "6",
                    "--json", tmp_path / "r.json", "--fix", tmp_path / "f.png")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert sorted(o["nearest"] for o in rep["off_palette"]) == [6, 8, 9, 12, 15]
    assert rep["cells"] and sorted(int(k) for k in rep["cells"][0]["colours"]) == [8, 9, 12, 15]


def test_two_colours_merging_into_one_number_warns(tmp_path, run):
    r, g, b = PEPTO[12]
    px = {(0, 0): PEPTO[12], (1, 0): (r + 4, g + 4, b + 4)}   # grey and a near-grey
    p = make_png(tmp_path / "a.png", 160, 200, 0, px)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    assert "both read as 12 grey" in out
    rep = json.loads((tmp_path / "r.json").read_text())
    assert any("both read as" in n for n in rep["notes"])


# ---------- 2. no alternate data streams -----------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="NTFS streams")
def test_output_stream_on_input_refused(tmp_path, run):
    p = broken(tmp_path)
    mtime = p.stat().st_mtime_ns
    code, out = run("check", p, "--mode", "mc", "--json", str(p) + ":s")
    assert code == 2 and "stream" in out
    assert p.stat().st_mtime_ns == mtime


# ---------- 3. exit 2 means nothing was written -----------------------------------

def test_missing_png2prg_found_before_any_write(tmp_path, run, monkeypatch):
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: None)
    p = broken(tmp_path)
    code, out = run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png",
                    "--json", tmp_path / "r.json", "--then", "png2prg")
    assert code == 2 and "png2prg" in out
    assert sorted(x.name for x in tmp_path.iterdir()) == ["in.png"]


def test_failed_write_leaves_no_outputs(tmp_path, run, monkeypatch):
    p = broken(tmp_path)
    real = c64lint.encode_koala

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(c64lint, "encode_koala", boom)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json",
                    "--overlay", tmp_path / "o.png", "--fix", tmp_path / "f.png",
                    "--kla", tmp_path / "k.kla")
    monkeypatch.setattr(c64lint, "encode_koala", real)
    assert code == 2 and "disk full" in out
    assert sorted(x.name for x in tmp_path.iterdir()) == ["in.png"]


def test_failed_write_keeps_an_existing_output_intact(tmp_path, run, monkeypatch):
    p = broken(tmp_path)
    (tmp_path / "r.json").write_text("old")
    monkeypatch.setattr(c64lint, "encode_koala",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    run("check", p, "--mode", "mc", "--json", tmp_path / "r.json", "--fix", tmp_path / "f.png",
        "--kla", tmp_path / "k.kla")
    assert (tmp_path / "r.json").read_text() == "old"


# ---------- 4. --then spellings --------------------------------------------------

def test_then_with_equals(tmp_path, run, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")
    monkeypatch.setattr(c64lint.subprocess, "run", fake)
    p = make_png(tmp_path / "a.png", 320, 200, 6)
    code, out = run("check", p, "--mode", "mc", "--then=png2prg", "--", "-d")
    assert code == 0, out
    assert fake.calls[0][1:-1] == ["-d"]


def test_abbreviated_options_are_refused(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6)
    code, out = run("check", p, "--mo", "mc")
    assert code == 2


# ---------- 5. png2prg failing has its own exit code --------------------------------

def test_png2prg_failure_is_exit_3(tmp_path, run, monkeypatch):
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")
    monkeypatch.setattr(c64lint.subprocess, "run", FakeRun(returncode=1))
    p = make_png(tmp_path / "a.png", 320, 200, 6)
    code, out = run("check", p, "--mode", "mc", "--then", "png2prg", "--", "-o", "my pic.prg")
    assert code == 3 and "png2prg failed" in out
    assert '"my pic.prg"' in out or "'my pic.prg'" in out


# ---------- 6. Windows device names ------------------------------------------------

@pytest.mark.parametrize("name", ["CON", "nul.json", "COM1.kla", "aux.png", "Lpt3.png"])
def test_device_names_refused(tmp_path, run, name):
    p = broken(tmp_path)
    flag = "--kla" if name.endswith(".kla") else "--json" if not name.endswith(".png") else "--fix"
    code, out = run("check", p, "--mode", "mc", flag, tmp_path / name)
    assert code == 2 and "device" in out


# ---------- 7. the format message does not depend on the build ---------------------

def test_non_png_named_from_its_signature(tmp_path, run, monkeypatch):
    p = tmp_path / "a.png"
    p.write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 32)
    monkeypatch.setattr(c64lint.Image, "open",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    code, out = run("check", p, "--mode", "mc")
    assert code == 2 and "WEBP" in out


# ---------- 8. notes reach the JSON -------------------------------------------------

def test_notes_in_json(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0)
    run("check", p, "--mode", "hires", "--bg", "3", "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert any("--bg ignored" in n for n in rep["notes"])


# ---------- the background hint (Alex, manual test of 12-fix-neon-sign) ---------------

def neon_like(tmp_path):
    """Blue picture with a row of cells that hold red, cyan, dark grey and grey
    but no blue: red is cheapest as $d021, blue covers nearly everything."""
    px = {}
    for cx in range(10, 20):
        px.update(mc_cell(cx, 12, [2, 3, 11, 12]))
    return make_png(tmp_path / "neon.png", 320, 200, 6, px)


def test_background_hint_when_cheapest_is_not_the_main_colour(tmp_path, run):
    p = neon_like(tmp_path)
    code, out = run("check", p, "--mode", "mc", "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    assert rep["bg"] != 6
    lines = out.splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("[*] background:"))
    assert lines[i + 1].startswith("[!] background ") and "--bg 6" in lines[i + 1]
    assert "10 cell(s) need fixing" in lines[i + 1]
    assert any("--bg 6" in n for n in rep["notes"])


def test_no_background_hint_when_forced(tmp_path, run):
    p = neon_like(tmp_path)
    _, out = run("check", p, "--mode", "mc", "--bg", "2")
    assert "was picked because" not in out


def test_no_background_hint_when_main_colour_wins(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    _, out = run("check", p, "--mode", "mc")
    assert "was picked because" not in out
