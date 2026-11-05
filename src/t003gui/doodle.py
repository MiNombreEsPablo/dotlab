"""Freehand doodles: a 1-bit ink mask the size of the sticker, stored in `LabelSpec.doodle` as base64 PNG text. Qt-free.

A string rather than a file, so a doodle travels with presets and label files and needs no extra plumbing. White
pixels in the mask are ink (printed black), black ones are untouched label.
"""
from __future__ import annotations

import base64
import binascii
import io
from functools import lru_cache

from PIL import Image, UnidentifiedImageError

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

TOOLS = ("pen", "square", "italic", "spray", "line", "box", "oval", "fill", "stamp", "eraser")
INKS = {  # 4x4 dither tiles ("#" is ink), anchored to the label so neighbouring strokes line up
    "solid": ("####",) * 4, "half": ("#.#.", ".#.#", "#.#.", ".#.#"), "quarter": ("#.#.", "....", "#.#.", "...."),
    "lines": ("####", "....", "####", "...."), "diagonal": ("##..", ".##.", "..##", "#..#"),
}
USES_INK = ("pen", "square", "italic", "line", "box", "oval", "fill")  # tools that paint with the chosen pattern
USES_BRUSH = ("pen", "square", "italic", "spray", "line", "box", "oval", "eraser")  # tools that have a width
BRUSH = (1, 24, 4)  # width in dots: smallest, largest, start
STICKER_SCALE = (1, 6, 2)  # stickers are enlarged by whole numbers: smallest, largest, start
UNDO_LIMIT = 30
SPRAY_MS = 25  # how often the spray can sprays while the button is held
LABELS = {
    "pen": "Round brush", "square": "Square brush", "italic": "Calligraphy", "spray": "Spray can", "line": "Line",
    "box": "Rectangle", "oval": "Ellipse", "fill": "Paint bucket", "stamp": "Sticker", "eraser": "Eraser",
    "solid": "Solid", "half": "50 % checker", "quarter": "25 % dots", "lines": "Lines", "diagonal": "Diagonal lines",
}


def describe() -> dict:
    """The drawing tools for a client: what exists, how it is worded, which controls each tool uses, the limits."""
    return {
        "width": W, "height": SH,
        "tools": [[t, LABELS[t]] for t in TOOLS], "inks": [[i, LABELS[i], list(rows)] for i, rows in INKS.items()],
        "uses_ink": list(USES_INK), "uses_brush": list(USES_BRUSH),
        "brush": list(BRUSH), "sticker_scale": list(STICKER_SCALE), "undo_limit": UNDO_LIMIT, "spray_ms": SPRAY_MS,
    }
