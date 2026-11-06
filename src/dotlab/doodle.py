"""Freehand doodles: a 1-bit ink mask the size of the sticker, stored in `LabelSpec.doodle` as base64 PNG text.

A string rather than a file, so a doodle travels with presets and label files and needs no extra plumbing. White
pixels in the mask are ink (printed black), black ones are untouched label.
"""
from __future__ import annotations

import base64
import binascii
import io
import math
import random
from functools import lru_cache

from PIL import Image, UnidentifiedImageError

from . import stickers
from .spec import SH, W

SIZE = (W, SH)


def encode(mask: Image.Image) -> str:
    """Base64 PNG of `mask` (any mode, size W x SH; non-zero is ink), or "" when nothing is drawn."""
    if mask.size != SIZE:
        raise ValueError(f"a doodle is {W}x{SH} dots, not {mask.width}x{mask.height}")
    bits = mask.convert("L").point([0] * 128 + [255] * 128).convert("1")
    if not bits.getbbox():
        return ""
    out = io.BytesIO()
    bits.save(out, "PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


@lru_cache(maxsize=8)  # the preview renders on every slider step; the mask is shared, so never modify it
def decode(data: str) -> Image.Image | None:
    """The ink mask (mode "L", 0 or 255), or None for an empty or damaged doodle: stored files may be hand-edited."""
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data, validate=True)))
        if img.size != SIZE:  # checked from the header, before any pixels are decoded
            return None
        return img.convert("L").point([0] * 128 + [255] * 128)
    except (binascii.Error, ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def canonical(data: str) -> str:
    """The doodle in the engine's own compact encoding (a 1-bit PNG), whoever made it: a browser canvas writes a
    full-colour PNG several times the size. "" for an empty or damaged doodle. Idempotent."""
    mask = decode(data)
    return encode(mask) if mask is not None else ""


# --- the drawing tools, as data: a client draws, the engine says what there is to draw with --------------------------

TOOLS = ("pen", "square", "italic", "spray", "line", "box", "oval", "fbox", "foval", "fill", "eraser")
def _tile(on, size: int = 8) -> tuple:
    """A dither tile from a rule: `on(x, y)` says whether the dot at (x, y) of the size x size tile is ink."""
    return tuple("".join("#" if on(x, y) else "." for x in range(size)) for y in range(size))


def _noise(seed: int, share: float) -> tuple:
    rng = random.Random(seed)
    return _tile(lambda x, y: rng.random() < share)


_ZIGZAG = (0, 1, 2, 3, 0, 3, 2, 1)
_WAVE = (0, 1, 1, 1, 0, 3, 3, 3)
INKS = {  # dither tiles, 4x4 or 8x8 ("#" is ink), anchored to the label so neighbouring strokes line up
    "solid": ("####",) * 4, "half": ("#.#.", ".#.#", "#.#.", ".#.#"), "quarter": ("#.#.", "....", "#.#.", "...."),
    "lines": ("####", "....", "####", "...."), "diagonal": ("##..", ".##.", "..##", "#..#"),
    "heavy": ("####", "#.##", "####", "##.#"),
    "eighth": _tile(lambda x, y: y % 2 == 0 and (x + 2 * (y // 2 % 2)) % 4 == 0),
    "upright": _tile(lambda x, y: x % 2 == 0),
    "crosshatch": _tile(lambda x, y: x % 4 == 0 or y % 4 == 0),
    "bricks": _tile(lambda x, y: y % 4 == 0 or x == (0 if y < 4 else 4)),
    "waves": _tile(lambda x, y: (y + _WAVE[x]) % 4 == 0),
    "zigzag": _tile(lambda x, y: (y + _ZIGZAG[x]) % 4 == 0),
    "diamonds": _tile(lambda x, y: abs(x - 3.5) + abs(y - 3.5) == 4),
    "rings": _tile(lambda x, y: 2.5 <= math.hypot(x - 3.5, y - 3.5) < 3.5),
    "plus": _tile(lambda x, y: (x % 4, y % 4) in {(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)}),
    "dashes": _tile(lambda x, y: (y == 0 and x < 4) or (y == 4 and x >= 4)),
    "static": _noise(3, 0.3),
    "snow": _noise(5, 0.12),
}
USES_INK = ("pen", "square", "italic", "line", "box", "oval", "fbox", "foval", "fill")  # tools that paint with the chosen pattern
USES_BRUSH = ("pen", "square", "italic", "spray", "line", "box", "oval", "fbox", "foval", "eraser")  # tools that have a width
BRUSH = (1, 24, 4)  # width in dots: smallest, largest, start
UNDO_LIMIT = 30
SPRAY_MS = 25  # how often the spray can sprays while the button is held
LABELS = {
    "pen": "Round brush", "square": "Square brush", "italic": "Calligraphy", "spray": "Spray can", "line": "Line",
    "box": "Rectangle", "oval": "Ellipse", "fbox": "Filled rectangle", "foval": "Filled ellipse", "fill": "Paint bucket", "eraser": "Eraser",
    "solid": "Solid", "half": "50 % checker", "quarter": "25 % dots", "lines": "Lines", "diagonal": "Diagonal lines",
    "heavy": "75 % dark", "eighth": "12 % sprinkle", "upright": "Pinstripes", "crosshatch": "Crosshatch", "bricks": "Bricks",
    "waves": "Waves", "zigzag": "Zigzag", "diamonds": "Diamonds", "rings": "Rings", "plus": "Plus signs",
    "dashes": "Dashes", "static": "TV static", "snow": "Snow",
}
GRID = 8  # the snap grid's spacing, in dots


def describe() -> dict:
    """The drawing tools for a client: what exists, how it is worded, which controls each tool uses, the limits."""
    return {
        "width": W, "height": SH,
        "tools": [[t, LABELS[t]] for t in TOOLS], "inks": [[i, LABELS[i], list(rows)] for i, rows in INKS.items()],
        "grid": GRID, "uses_ink": list(USES_INK), "uses_brush": list(USES_BRUSH),
        "brush": list(BRUSH), "undo_limit": UNDO_LIMIT, "spray_ms": SPRAY_MS,
    }
