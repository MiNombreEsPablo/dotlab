"""Label description and the geometry constants shared by rendering and printing.

Geometry: 58 mm paper, 384 printable dots wide (203 dpi). The label pitch is 240 dots
(sticker + 2 mm gap) but the sticker itself is only ~224 dots tall, so content stays in SH.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields

W, H = 384, 240  # printable dots; H is the label pitch
SH = 224  # sticker height in dots
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
MARGIN = 8

DEFAULT_FONT = "DejaVu Sans"
ALIGNMENTS = ("left", "center", "right")
VALIGNMENTS = ("top", "middle", "bottom")
EFFECTS = ("none", "shadow", "outline", "3d", "glitch", "neon", "scanlines")
BACKGROUNDS = (
    "none", "checker", "dots", "stripes", "gradient", "stars", "grid",
    "scanlines", "circuit", "hexgrid", "synthwave", "matrix", "halftone",
)
IMAGE_LAYOUTS = ("only", "left", "right", "top", "bottom", "behind")  # image + text arrangement
DITHERS = ("floyd", "bayer4", "bayer8")  # images; a hard cutoff is `threshold`
BORDER_STYLES = ("solid", "double", "dotted", "checker", "bevel", "marquee", "chamfer", "brackets", "ticks")


@dataclass
class LabelSpec:
    text: str = ""
    qr: str = ""
    image_path: str = ""
    image_layout: str = "only"  # "only" ignores text/QR; the rest share the label with them
    image_size: int = 40  # left/right/top/bottom: the image's share of the usable area, 20-80 %
    threshold: int | None = None  # images: hard cutoff instead of dithering
    dither: str = "floyd"  # images: how gray becomes dots
    brightness: int = 0  # images: -100..100
    contrast: int = 0  # images: -100..100
    gamma: float = 1.0  # images: > 1 lightens the mid-tones
    pixelate: int = 0  # images: chunky blocks of this many dots (0 = off)
    mirror: bool = False  # images: left-right
    flip: bool = False  # images: top-bottom
    invert: bool = False  # images: negative
    copies: int = 1
    density: int = 7
    # text
    font: str = DEFAULT_FONT  # family name, resolved through fontconfig
    bold: bool = True
    italic: bool = False  # synthetic slant when the font has no italic face
    size: int = 0  # 0 = largest that fits, otherwise a cap in dots
    align: str = "center"  # lines within the block and the block within the text area
    valign: str = "middle"
    effect: str = "none"
    # decoration
    border: bool = False
    border_style: str = "solid"
    background: str = "none"
    bars: bool = False  # hazard-stripe "under construction" bars top and bottom
    doodle: str = ""  # freehand ink drawn over everything: a base64 PNG mask, see doodle.py

    @classmethod
    def from_dict(cls, raw: dict) -> "LabelSpec":
        """Build a spec from stored JSON (presets, composition files): unknown keys are ignored, and a value of the
        wrong type falls back to the field's default, so a hand-edited file cannot crash rendering later."""
        defaults, values = cls(), {}
        for f in fields(cls):
            if f.name not in raw:
                continue
            value, default = raw[f.name], getattr(defaults, f.name)
            if default is None:  # threshold: an int or None
                ok = value is None or (isinstance(value, int) and not isinstance(value, bool))
            elif isinstance(default, bool):
                ok = isinstance(value, bool)
            elif isinstance(default, float):
                ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            elif isinstance(default, int):
                ok = isinstance(value, int) and not isinstance(value, bool)
            else:
                ok = isinstance(value, str)
            if ok:
                values[f.name] = value
        return cls(**values)


def layout_hint(spec: LabelSpec) -> str:
    """The text and QR code are silently dropped by the default "Image only" layout: say so, and where to change it.
    Empty when there is nothing to say. Shared by every client, so they all word it the same."""
    if spec.image_path and spec.image_layout == "only" and (spec.text or spec.qr):
        what = "text and QR code aren't" if spec.text and spec.qr else ("text isn't" if spec.text else "QR code isn't")
        return f"The {what} printed: the layout is \u201cImage only\u201d. Choose another layout on the Image tab."
    return ""


CONTENT_FIELDS = ("text", "qr", "image_path", "doodle")  # what a label can say; a border or a pattern alone is not content


def has_content(spec: LabelSpec) -> bool:
    """Is there anything to print? Text, a QR code, a picture or a doodle; blank text does not count. Every client uses
    this (print, export and copy all refuse an empty label), so no one of them can forget a field again."""
    return any(str(getattr(spec, field)).strip() for field in CONTENT_FIELDS)


EXPORT_SCALES = (1, 4)  # the sizes a label can be exported at: as printed (one image dot per printed dot) or enlarged 4x


def export_size_label(scale: int) -> str:
    """How an export size is worded in a dialog or a menu."""
    what = "printed size" if scale == 1 else f"enlarged {scale}\u00d7"
    return f"PNG image, {what} ({W * scale}\u00d7{SH * scale})"


def export_size_name(scale: int) -> str:
    """The short wording, for a picker beside the Save button."""
    name = "Printed size" if scale == 1 else f"Enlarged {scale}\u00d7"
    return f"{name} ({W * scale}\u00d7{SH * scale})"


def file_stem(spec: LabelSpec) -> str:
    """A name for a file made from this label: its first line of text, made safe, or "label"."""
    first_line = (spec.text.strip().splitlines() or [""])[0]
    return re.sub(r"[^\w -]+", "", first_line).strip()[:40] or "label"
