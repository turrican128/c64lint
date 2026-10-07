"""The shipped examples must behave the way README.md and examples/README.txt
say they do; a docs claim with no test behind it rots silently."""
from pathlib import Path

import pytest

EX = Path(__file__).resolve().parent.parent / "examples"

CASES = [
    ("01-clean.png", "mc", 0),
    ("02-bird-clash.png", "mc", 1),
    ("03-split-pairs.png", "mc", 1),
    ("04-off-palette.png", "mc", 1),
    ("05-hires-clash.png", "hires", 1),
]


@pytest.mark.parametrize("name,mode,expected", CASES)
def test_example_exit_code(run, tmp_path, name, mode, expected):
    code, out = run("check", EX / name, "--mode", mode, "--fix", tmp_path / "f.png")
    assert code == expected, out
    assert run("check", tmp_path / "f.png", "--mode", mode)[0] == 0


def test_each_example_shows_its_own_problem(run):
    out = {n: run("check", EX / n, "--mode", m)[1] for n, m, _ in CASES}
    assert "broken cell" in out["02-bird-clash.png"]
    assert "pixel pair" in out["03-split-pairs.png"]
    assert "off-palette" in out["04-off-palette.png"]
    assert "broken cell" in out["05-hires-clash.png"]


def test_every_example_is_listed():
    listed = (EX / "README.txt").read_text()
    for p in EX.glob("*.png"):
        assert p.name in listed
