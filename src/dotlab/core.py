"""The label engine's one import for tests and tools: rendering, the spec and the PNG export.

No window toolkit in here. Rendering lives in render.py and the label
description in spec.py; both are re-exported so `core` stays the one import for callers.
"""
from __future__ import annotations

from .protocol import STATUS_FLAGS, STATUS_QUERY, chunks, status_problems, tspl  # noqa: F401
from .render import PrinterError, font_path, label_bitmap, list_font_families, render, to_bitmap  # noqa: F401
from .spec import (  # noqa: F401
    ALIGNMENTS,
    BACKGROUNDS,
    BORDER_STYLES,
    DEFAULT_FONT,
    DITHERS,
    EFFECTS,
    H,
    IMAGE_LAYOUTS,
    IMAGE_SUFFIXES,
    MARGIN,
    SH,
    VALIGNMENTS,
    W,
    LabelSpec,
)

def export_png(spec: LabelSpec, path, scale: int = 1) -> None:
    """Save the label as a PNG (see `label_bitmap`)."""
    label_bitmap(spec, scale).save(path, format="PNG")

