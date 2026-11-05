"""Send a label to the ORGBRO T003 thermal printer over Bluetooth (bluetooth.py).

No window toolkit in here, so it can be tested and reused from a CLI. Rendering lives in render.py and the label
description in spec.py; both are re-exported so `core` stays the one import for callers.
"""
from __future__ import annotations

from . import bluetooth as bt
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


def print_label(spec: LabelSpec, address: str = "auto") -> list[str]:
    """Print over Bluetooth to `address`, or "" / "auto" for the first known T003 (see `bluetooth.resolve`). Returns the
    problems the printer reports afterwards."""
    return bt.print_to(tspl(spec), address)
