#!/usr/bin/env python3
"""Build the single-file c64lint binary with PyInstaller.

    python tools/build_binary.py            # Windows
    python tools/build_binary.py --strip    # Linux (inside the bullseye container)

Used by .github/workflows/release.yml on both platforms, so the exclude list
lives in one place.

Measured on Windows (2026-10-07): a plain build is 27 MB, because PyInstaller
drags in numpy (Pillow can use it, c64lint never does), Pillow's AVIF/WebP/
colour-management codecs and OpenSSL. Excluding them gives 8.2 MB with
byte-identical output on every example.

Keep PIL.ImageFont: ImageDraw imports it at module level, and a build without
it compiles cleanly and dies on startup. Only its FreeType engine
(PIL._imagingft) is safe to drop - c64lint draws its labels with Pillow's
built-in bitmap font. The workflow's smoke test is what catches the next
module like that.

--strip is for Linux only: on Windows it corrupts the bundled python DLL
(txt2dirart v0.9.0-rc2 built fine, then exited 127 "Failed to load Python DLL").
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "doctest", "pdb", "sqlite3", "asyncio", "numpy",
    "PIL.ImageQt", "PIL.ImageTk", "PIL.ImageShow",
    "PIL._avif", "PIL.AvifImagePlugin", "PIL._webp", "PIL.WebPImagePlugin",
    "PIL._imagingcms", "PIL.ImageCms", "PIL._imagingft",
    "ssl", "_ssl", "hashlib", "_hashlib",
]


def main():
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--name", "c64lint",
           "--console", "--noupx", "--noconfirm"]
    if "--strip" in sys.argv[1:]:
        cmd.append("--strip")
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ROOT / "c64lint.py"))
    print(" ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
