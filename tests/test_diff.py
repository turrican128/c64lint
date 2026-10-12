"""The .diff.png must make a fix visible at a glance (Alex, manual test,
2026-10-12: on the neon-sign picture 34 changed pixels were specks in a
3220x1000 image)."""
from PIL import Image

import c64lint
from conftest import PEPTO, anchored, make_png, mc_cell

S = c64lint.SCALE
MAGENTA = (255, 0, 255)


def fixed_pair(tmp_path, run):
    # one broken cell at cell (3,2) = screen x 24..31, y 16..23
    p = make_png(tmp_path / "in.png", 320, 200, 6, anchored(mc_cell(3, 2, [1, 2, 3, 4])))
    code, out = run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    before = Image.open(p).convert("RGB")
    after = Image.open(tmp_path / "f.png").convert("RGB")
    diff = Image.open(tmp_path / "f.diff.png").convert("RGB")
    return before, after, diff, out


def test_changed_cell_is_framed(tmp_path, run):
    _, _, diff, _ = fixed_pair(tmp_path, run)
    px = diff.load()
    gap = 4 * S
    for left in (0, 320 * S + gap):                     # both halves
        # frame sits just outside the cell's left edge
        assert px[left + 24 * S - 1, 20 * S] == MAGENTA
        assert px[left + 24 * S - 2, 20 * S] == MAGENTA


def test_unchanged_area_is_grey(tmp_path, run):
    _, _, diff, _ = fixed_pair(tmp_path, run)
    r, g, b = diff.getpixel((200 * S + 2, 150 * S + 2))  # far from the change
    assert r == g == b


def test_zoom_panel_shows_old_and_new_colour(tmp_path, run):
    before, after, diff, _ = fixed_pair(tmp_path, run)
    assert diff.height > 200 * S                          # zoom panel below
    changed = [(x, y) for y in range(200) for x in range(320)
               if before.getpixel((x, y)) != after.getpixel((x, y))]
    x, y = changed[0]
    z, (bx0, by0), (lx, rx), top = c64lint.diff_zoom_geometry(diff, changed, 8)
    inner = (lambda X: X * z + z // 2)
    assert diff.getpixel((lx + inner(x - bx0), top + inner(y - by0))) == before.getpixel((x, y))
    assert diff.getpixel((rx + inner(x - bx0), top + inner(y - by0))) == after.getpixel((x, y))


def test_console_says_how_much_changed(tmp_path, run):
    before, after, _, out = fixed_pair(tmp_path, run)
    n = sum(1 for y in range(200) for x in range(320)
            if before.getpixel((x, y)) != after.getpixel((x, y)))
    assert f"the fix changed {n} screen pixel(s) in 1 cell(s)" in out


def test_no_zoom_panel_when_nothing_changed(tmp_path, run):
    p = make_png(tmp_path / "in.png", 320, 200, 6, mc_cell(3, 2, [1, 2, 3]))
    run("check", p, "--mode", "mc", "--fix", tmp_path / "f.png")
    diff = Image.open(tmp_path / "f.diff.png")
    assert diff.height == 200 * S
