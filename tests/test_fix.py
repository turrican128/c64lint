import json
import random
import time

from PIL import Image

import c64lint
from conftest import PEPTO, anchored, make_png, mc_cell


def pixels(path):
    img = Image.open(path).convert("RGB")
    return img.size, list(c64lint._pixels(img))


def test_fix_makes_picture_clean(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    code, _ = run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    assert code == 1  # exit code reflects the input
    code2, _ = run("check", tmp_path / "f.png", "--mode", "mc")
    assert code2 == 0
    assert (tmp_path / "f.diff.png").exists()


def test_fix_leaves_clean_cells_untouched(tmp_path, run):
    px = mc_cell(0, 0, [1, 2, 3])
    px.update(mc_cell(3, 2, [1, 2, 3, 4]))
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(px))
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    (w, h), before = pixels(p)
    _, after = pixels(tmp_path / "f.png")
    changed = {(i % w, i // w) for i, (a, b) in enumerate(zip(before, after)) if a != b}
    assert changed
    assert all(24 <= x < 32 and 16 <= y < 24 for x, y in changed)


def test_fix_repaints_to_perceptually_nearest(tmp_path, run):
    # cell: blue bg(6) + white(1), yellow(7), light grey(15), dark grey(11)
    # dark grey (fewest-cost to merge?) -- the cheapest removal is the colour
    # whose pixels sit closest to a kept colour; grey 11 -> blue 6 or black.
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [1, 7, 15, 11], wide=False))
    run("check", p, "--mode", "mc", "--bg", "6", "--fix", tmp_path / "f.png",
        "--json", tmp_path / "r.json")
    rep = json.loads((tmp_path / "r.json").read_text())
    cell = rep["cells"][0]
    # brute force check: the kept set is the cheapest of all candidates
    lab = [c64lint.rgb_to_lab(c) for c in PEPTO]
    counts = {int(k): v for k, v in cell["colours"].items()}
    nonbg = [c for c in counts if c != 6]
    import itertools
    best = min(
        sum(n * min(c64lint.delta_e(lab[c], lab[k]) for k in s + (6,))
            for c, n in counts.items())
        for s in itertools.combinations(sorted(nonbg), 3))
    kept = tuple(sorted(cell["fix"]["keep"]))
    got = sum(n * min(c64lint.delta_e(lab[c], lab[k]) for k in kept)
              for c, n in counts.items())
    assert abs(got - best) < 1e-6


def test_fix_snaps_off_palette(tmp_path, run):
    r, g, b = PEPTO[14]
    p = make_png(tmp_path / "a.png", 160, 200, 0, {(40, 12): (r, g, b + 3)})
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    img = Image.open(tmp_path / "f.png").convert("RGB")
    assert img.getpixel((40, 12)) == PEPTO[14]


def test_fix_resolves_pairs_by_cell_majority(tmp_path, run):
    # cell (1,0) mostly white (1); a pair (10,5)/(11,5) = blue/white
    px = {(x, y): 1 for x in range(8, 16) for y in range(8)}
    px[(10, 5)] = 6
    p = make_png(tmp_path / "a.png", 320, 200, 0, px)
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    img = Image.open(tmp_path / "f.png").convert("RGB")
    assert img.getpixel((10, 5)) == PEPTO[1] == img.getpixel((11, 5))


def test_pair_tie_takes_lower_index(tmp_path, run):
    # cell with exactly 32 white and 32 red px; mismatched pair red/white
    px = {}
    for y in range(8):
        for x in range(8, 16):
            px[(x, y)] = 1 if y < 4 else 2
    px[(8, 0)] = 2   # pair (8,0)/(9,0) = red/white, white loses one, red gains
    px[(8, 7)] = 1   # restore 32/32 balance
    p = make_png(tmp_path / "a.png", 320, 200, 0, px)
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    img = Image.open(tmp_path / "f.png").convert("RGB")
    assert img.getpixel((8, 0)) == PEPTO[1] == img.getpixel((9, 0))


def test_fix_refuses_to_overwrite_input(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(0, 0, [1, 2, 3, 4], wide=False))
    before = p.read_bytes()
    code, out = run("check", p, "--mode", "mc", "--fix", p)
    assert code == 2 and "!!" in out
    assert p.read_bytes() == before


def test_fix_is_deterministic(tmp_path, run):
    rnd = random.Random(7)
    px = {(x, y): rnd.randrange(16) for x in range(0, 64) for y in range(0, 32)}
    p = make_png(tmp_path / "a.png", 160, 200, 0, px)
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f1.png", "--json", tmp_path / "r1.json")
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f2.png", "--json", tmp_path / "r2.json")
    assert (tmp_path / "f1.png").read_bytes() == (tmp_path / "f2.png").read_bytes()
    r1 = json.loads((tmp_path / "r1.json").read_text())
    r2 = json.loads((tmp_path / "r2.json").read_text())
    r1.pop("file"); r2.pop("file")
    assert r1 == r2


def test_hires_fix(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0, {(9, 1): 1, (10, 1): 2, (11, 1): 2})
    run("check", p, "--mode", "hires", "--fix", tmp_path / "f.png")
    code, _ = run("check", tmp_path / "f.png", "--mode", "hires")
    assert code == 0


def test_worst_case_noise_is_fast(tmp_path, run):
    rnd = random.Random(1)
    px = {(x, y): rnd.randrange(16) for x in range(160) for y in range(200)}
    p = make_png(tmp_path / "a.png", 160, 200, 0, px)
    t = time.perf_counter()
    code, _ = run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    elapsed = time.perf_counter() - t
    assert code == 1
    assert run("check", tmp_path / "f.png", "--mode", "mc")[0] == 0
    assert elapsed < 20, elapsed  # pure noise; real photos take < 0.5 s


# ---------- outputs ----------------------------------------------------------

def test_overlay_written(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    run("check", p, "--mode", "mc", "--overlay", tmp_path / "o.png")
    img = Image.open(tmp_path / "o.png")
    assert img.size == (960, 600)


def test_kla_round_trip(tmp_path, run):
    px = mc_cell(0, 0, [1, 2, 3])
    px.update(mc_cell(3, 2, [1, 2, 3, 4]))
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(px))
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png", "--kla", tmp_path / "o.kla")
    data = (tmp_path / "o.kla").read_bytes()
    assert len(data) == 10003 and data[:2] == b"\x00\x60"
    decoded = c64lint.decode_koala(data, PEPTO)
    assert decoded.tobytes() == Image.open(tmp_path / "f.png").convert("RGB").tobytes()


def test_kla_from_clean_160_input(tmp_path, run):
    p = make_png(tmp_path / "a.png", 160, 200, 6, mc_cell(2, 2, [1, 2, 3], wide=False))
    code, _ = run("check", p, "--mode", "mc", "--kla", tmp_path / "o.kla")
    assert code == 0
    decoded = c64lint.decode_koala((tmp_path / "o.kla").read_bytes(), PEPTO)
    src = Image.open(p).convert("RGB").resize((320, 200), Image.NEAREST)
    assert decoded.tobytes() == src.tobytes()


def test_kla_not_written_when_dirty_without_fix(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    code, out = run("check", p, "--mode", "mc", "--kla", tmp_path / "o.kla")
    assert code == 1
    assert not (tmp_path / "o.kla").exists()
    assert "[!]" in out and "--fix" in out


def test_kla_refused_in_hires(tmp_path, run):
    p = make_png(tmp_path / "a.png", 320, 200, 0)
    code, out = run("check", p, "--mode", "hires", "--kla", tmp_path / "o.kla")
    assert code == 2


def test_then_png2prg_missing(tmp_path, run, monkeypatch):
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: None)
    p = make_png(tmp_path / "a.png", 160, 200, 6)
    code, out = run("check", p, "--mode", "mc", "--then", "png2prg", "--", "-d")
    assert code == 2 and "github.com/staD020/png2prg" in out


def test_then_png2prg_runs_on_clean_result(tmp_path, run, monkeypatch):
    calls = []
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")

    class R:
        returncode = 0

    monkeypatch.setattr(c64lint.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or R())
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png",
        "--then", "png2prg", "--", "-d", "-o", "x.prg")
    assert calls == [["/bin/png2prg", "-d", "-o", "x.prg", str(tmp_path / "f.png")]]


def test_then_skipped_when_dirty_without_fix(tmp_path, run, monkeypatch):
    monkeypatch.setattr(c64lint.shutil, "which", lambda name: "/bin/png2prg")
    monkeypatch.setattr(c64lint.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    p = make_png(tmp_path / "a.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    code, out = run("check", p, "--mode", "mc", "--then", "png2prg")
    assert code == 1


def test_random_legal_koala_is_clean_and_round_trips(tmp_path, run):
    rnd = random.Random(42)
    for palette in ("pepto-pal", "colodore", "vice"):
        data = bytes([0x00, 0x60]) + bytes(rnd.randrange(256) for _ in range(10000)) \
            + bytes([rnd.randrange(16)])
        pal = c64lint.PALETTES[palette]
        img = c64lint.decode_koala(data, pal)
        img.save(tmp_path / "k.png")
        code, out = run("check", tmp_path / "k.png", "--mode", "mc",
                        "--kla", tmp_path / "k.kla", "--json", tmp_path / "r.json")
        assert code == 0, out
        assert json.loads((tmp_path / "r.json").read_text())["palette"] == palette
        again = c64lint.decode_koala((tmp_path / "k.kla").read_bytes(), pal)
        assert again.tobytes() == img.tobytes()
