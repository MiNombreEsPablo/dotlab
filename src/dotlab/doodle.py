"""Freehand doodles: a 1-bit ink mask the size of the sticker, stored in `LabelSpec.doodle` as base64 PNG text.

A string rather than a file, so a doodle travels with presets and label files and needs no extra plumbing. Light
pixels in the mask are ink: white (255) prints black, mid-grey (128) is white ink, which knocks the picture out to paper
(to add brightness on something dark); black ones are untouched label.
"""
from __future__ import annotations

import base64
import binascii
import io
import math
import random
from functools import lru_cache

from PIL import Image, UnidentifiedImageError

from .spec import SH, W

SIZE = (W, SH)
BLACK, WHITE = 255, 128  # a dot of the stored doodle: black ink, white ink (paper-coloured, to lighten something dark), or 0 = untouched
_BLACK_AT, _WHITE_AT = 192, 64  # what a decoded level counts as: >= 192 black ink, 64-191 white ink


def encode(mask: Image.Image) -> str:
    """Base64 PNG of `mask` (any mode, size W x SH): >= 192 is black ink, 64-191 white ink, less is untouched label.
    "" when nothing is drawn. A doodle with only black ink is a 1-bit PNG, as it always was."""
    if mask.size != SIZE:
        raise ValueError(f"a doodle is {W}x{SH} dots, not {mask.width}x{mask.height}")
    levels = mask.convert("L")
    black = levels.point([0] * _BLACK_AT + [255] * (256 - _BLACK_AT))
    white = levels.point([0] * _WHITE_AT + [255] * (_BLACK_AT - _WHITE_AT) + [0] * (256 - _BLACK_AT))
    if not (black.getbbox() or white.getbbox()):
        return ""
    if white.getbbox():
        bits = Image.new("L", SIZE, 0)
        bits.paste(BLACK, mask=black)
        bits.paste(WHITE, mask=white)
    else:
        bits = black.convert("1")
    out = io.BytesIO()
    bits.save(out, "PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


@lru_cache(maxsize=8)  # the preview renders on every slider step; the image is shared, so never modify it
def _levels(data: str) -> Image.Image | None:
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(base64.b64decode(data, validate=True)))
        if img.size != SIZE:  # checked from the header, before any pixels are decoded
            return None
        return img.convert("L")
    except (binascii.Error, ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def decode(data: str) -> Image.Image | None:
    """The black-ink mask (mode "L", 0 or 255), or None for an empty or damaged doodle: stored files may be hand-edited."""
    levels = _levels(data)
    return None if levels is None else levels.point([0] * _BLACK_AT + [255] * (256 - _BLACK_AT))


def decode_white(data: str) -> Image.Image | None:
    """The white-ink mask (mode "L", 0 or 255), or None when the doodle has none."""
    levels = _levels(data)
    if levels is None:
        return None
    mask = levels.point([0] * _WHITE_AT + [255] * (_BLACK_AT - _WHITE_AT) + [0] * (256 - _BLACK_AT))
    return mask if mask.getbbox() else None


def canonical(data: str) -> str:
    """The doodle in the engine's own compact encoding (a 1-bit PNG, or grey levels with white ink), whoever made it: a
    browser canvas writes a full-colour PNG several times the size. "" for an empty or damaged doodle. Idempotent."""
    levels = _levels(data)
    return encode(levels) if levels is not None else ""


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
