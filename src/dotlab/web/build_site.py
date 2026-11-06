"""Build the static site (what GitHub Pages serves): `python src/dotlab/web/build_site.py OUT [--no-wheels]`.

The site is exactly the layout the dev server fakes: the files of web/, plus
  engine/<module>.py        the engine's Python sources (the modules `dev_server.ENGINE_MODULES` lists)
  engine/manifest.json      what the browser has to load, written out as a file
  engine/wheels/            the one dependency Pyodide doesn't have (qrcode), pinned and checked against its SHA-256,
                            so a visit never depends on PyPI
  fonts/*.ttf               the bundled fonts, fetched on demand
  assets/                   the banner's mark, the favicon and the install icons
  licenses.txt              the project's licence and the licence of every bundled font
Pyodide itself comes from the jsDelivr CDN at the version the manifest names.

`--no-wheels` skips the download (for tests, which have no network).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dev_server  # noqa: E402  (the one list of what the browser engine ships)

WEB = dev_server.WEB
# The engine is tested against this qrcode; a different one would change labels. Update the three together.
QRCODE_REQUIREMENT = "qrcode==8.2"
QRCODE_WHEEL = "qrcode-8.2-py3-none-any.whl"
QRCODE_SHA256 = "16e64e0716c14960108e85d853062c9e8bba5ca8252c0b4d0231b9df4060ff4f"
NOT_SITE = {"dev_server.py", "build_site.py", "test", "__pycache__", "node_modules", ".pytest_cache"}


def verify_wheel(path: Path, sha256: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != sha256:
        raise SystemExit(f"{path.name} is not the wheel this build was written against\n  expected {sha256}\n  got      {actual}")


def fetch_wheel(into: Path) -> str:
    """Download the pinned wheel with pip (no dependencies: it needs none here), check it, put it in `into`."""
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run([sys.executable, "-m", "pip", "download", QRCODE_REQUIREMENT, "--no-deps", "--only-binary=:all:",
                        "-d", scratch, "-q"], check=True)
        wheel = Path(scratch) / QRCODE_WHEEL
        verify_wheel(wheel, QRCODE_SHA256)
        shutil.copy(wheel, into / QRCODE_WHEEL)
    return QRCODE_WHEEL


def build(out: Path, wheels: bool = True) -> dict:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: refusing to build over it")
    out.mkdir(parents=True, exist_ok=True)

    for item in WEB.iterdir():  # the page itself: html, css, js (and their folders)
        if item.name in NOT_SITE or item.suffix == ".py":
            continue
        if item.is_dir():
            shutil.copytree(item, out / item.name, ignore=shutil.ignore_patterns(*NOT_SITE, "*.py"))
        else:
            shutil.copy(item, out / item.name)

    engine = out / "engine"
    engine.mkdir(exist_ok=True)
    for name in dev_server.ENGINE_MODULES:
        shutil.copy(dev_server.PACKAGE / name, engine / name)

    (out / "fonts").mkdir()
    for font in dev_server.FONTS.glob("*.ttf"):
        shutil.copy(font, out / "fonts" / font.name)
    (out / "assets").mkdir()
    for name in dev_server.SITE_ASSETS:
        shutil.copy(dev_server.ASSETS / name, out / "assets" / name)

    (out / "licenses.txt").write_text(dev_server.licenses_text(), encoding="utf-8")  # the fonts' licences travel with them
    manifest = dev_server.manifest()
    if wheels:
        manifest["wheels"] = [fetch_wheel(engine / "wheels")]
        manifest["pypi"] = []  # nothing comes from PyPI at run time
    (engine / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # Pages must not run its own processing over the files
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path, help="an empty (or new) folder to build the site into")
    parser.add_argument("--no-wheels", action="store_true", help="don't download the pinned wheel")
    args = parser.parse_args()
    manifest = build(args.out, wheels=not args.no_wheels)
    files = [p for p in args.out.rglob("*") if p.is_file()]
    print(f"built {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB, into {args.out}"
          f" (Pyodide {manifest['pyodide']} from the CDN)")
