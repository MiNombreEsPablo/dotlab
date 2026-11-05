"""The browser's engine (Pyodide) must draw the same dots as the native one.

It needs Node and Pyodide's npm package, and the network (Pyodide fetches its wheels), so it only runs when
DOTLAB_PARITY_PYODIDE names a folder where `npm install pyodide@<the version the site uses>` was done (CI's web-parity job
does this). The cases are the ones checked bit for bit by hand: text in DejaVu Sans, every effect, border and
background, alignments, a QR code, a doodle. Not here, on purpose: the four fonts whose glyphs sit a dot apart (FreeType
2.13 in Pyodide, a newer one natively) and pictures that need a non-square resize (a newer Pillow resamples differently).
Both are documented in AGENTS.md.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from dotlab import api, doodle, spec

ROOT = Path(__file__).resolve().parent.parent
PYODIDE = os.environ.get("DOTLAB_PARITY_PYODIDE")

pytestmark = pytest.mark.skipif(not PYODIDE, reason="set DOTLAB_PARITY_PYODIDE to a folder with `npm install pyodide`")


def _cases() -> dict:
    cases = {"default": {"text": "Hello"}, "qr": {"qr": "https://example.com/x"}, "qr+text+bars": {"qr": "hi", "text": "scan me", "bars": True}}
    cases["multi italic"] = {"text": "line one\nline two\nthree", "italic": True, "bold": False, "size": 40, "align": "left", "valign": "top"}
    for effect in spec.EFFECTS:
        cases[f"effect {effect}"] = {"text": "Glitch 99", "effect": effect}
    for style in spec.BORDER_STYLES:
        cases[f"border {style}"] = {"text": "Box", "border": True, "border_style": style}
    for background in spec.BACKGROUNDS:
        cases[f"background {background}"] = {"text": "BG", "background": background}
    for align in spec.ALIGNMENTS:
        for valign in spec.VALIGNMENTS:
            cases[f"align {align} {valign}"] = {"text": "a\nbb", "align": align, "valign": valign}
    ink = Image.new("L", (spec.W, spec.SH), 0)
    ink.paste(255, (30, 30, 200, 60))
    ink.paste(255, (250, 100, 270, 200))
    cases["doodle"] = {"text": "Hi", "doodle": doodle.encode(ink)}
    return cases


def test_the_web_engine_draws_the_same_dots_as_the_native_one(tmp_path):
    cases = _cases()
    (tmp_path / "cases.json").write_text(json.dumps(cases))
    node = subprocess.run(
        ["node", str(ROOT / "src" / "dotlab" / "web" / "test" / "parity.mjs"), str(tmp_path / "cases.json"), str(tmp_path / "out.json"),
         str(ROOT / "src" / "dotlab"), PYODIDE],
        capture_output=True, text=True, timeout=600)
    assert node.returncode == 0, node.stdout[-2000:] + node.stderr[-2000:]
    web = json.loads((tmp_path / "out.json").read_text())
    native = {name: hashlib.sha256(api.preview_pixels(raw)).hexdigest()[:16] for name, raw in cases.items()}
    assert set(web) == set(native)
    differing = sorted(name for name in native if native[name] != web[name])
    assert not differing, f"{len(differing)} of {len(native)} labels differ between Pyodide and the native engine: {differing}"
