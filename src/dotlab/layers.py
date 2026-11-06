"""Layers: everything on a label that is placed (text, a picture, a QR code, a sticker) as one kind of object.

A label's `layers` is JSON text, bottom to top: `[{"t": "text", "x": 8, "y": 8, "w": 368, "h": 208, "text": "Hi"}, ...]`.
Every layer has a box (`x`, `y` = top-left corner, `w`, `h`, in dots) and the properties of its type; only the
properties that differ from the defaults are written. Like `stickers.parse`, `parse` is lenient (stored files may be
hand-edited): unknown types and malformed entries are dropped, numbers are clamped, and at most MAX_LAYERS are kept.
Toolkit-free; `render` draws the layers and `form` describes their controls.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from functools import lru_cache
from types import SimpleNamespace

from . import stickers
from .spec import DEFAULT_FONT, SH, W

TYPES = ("text", "image", "qr", "sticker")
FITS = ("contain", "cover")  # an image inside its box: whole picture, or filling the box and cropped
MAX_LAYERS = stickers.MAX_PLACED + 8  # what an older label could hold (40 stickers, a picture, a QR code, a text) with room to spare
MIN_BOX = 8  # the smallest side a box can have, in dots
LIMIT = 10_000  # how far a box may be moved (and how big a stored number can be)


@dataclass(frozen=True)
class Layer:
    t: str
    x: int = 0
    y: int = 0
    w: int = W
    h: int = SH
    hidden: bool = False
    rot: int = 0  # turned clockwise this many degrees (0, 90, 180, 270): the box is the layer as it lies on the label
    mirror: bool = False  # left-right (any layer; a picture does it before dithering)
    flip: bool = False  # top-bottom
    # text
    text: str = ""
    font: str = DEFAULT_FONT
    bold: bool = True
    italic: bool = False
    size: int = 0  # 0 = the largest that fits the box, otherwise a cap in dots
    align: str = "center"
    valign: str = "middle"
    effect: str = "none"
    # image
    path: str = ""
    fit: str = "contain"
    dither: str = "floyd"
    threshold: int | None = None
    brightness: int = 0
    contrast: int = 0
    gamma: float = 1.0
    pixelate: int = 0
    invert: bool = False
    cutout: int = 0  # 0 = off, 1-100: the flat background (the colour along the picture's edge) is see-through
    # qr
    data: str = ""
    # sticker (its box is the sticker as drawn: side x scale)
    name: str = ""
    scale: int = 1

    def picture(self) -> SimpleNamespace:
        """The image fields under the names `imaging.process` reads them by."""
        return SimpleNamespace(
            image_path=self.path, dither=self.dither, threshold=self.threshold, brightness=self.brightness,
            contrast=self.contrast, gamma=self.gamma, pixelate=self.pixelate, mirror=self.mirror, flip=self.flip,
            invert=self.invert, cutout=self.cutout)

    def to_dict(self) -> dict:
        """Only what differs from the defaults (`t` always)."""
        default, full = _DEFAULTS[self.t], asdict(self)
        return {k: v for k, v in full.items() if k == "t" or v != getattr(default, k) or k in ("x", "y", "w", "h")}


_DEFAULTS = {t: Layer(t) for t in TYPES}
_FIELDS = {f.name: f for f in fields(Layer)}


def _clean(raw) -> Layer | None:
    if not isinstance(raw, dict) or raw.get("t") not in TYPES:
        return None
    default = _DEFAULTS[raw["t"]]
    values = {"t": raw["t"]}
    for name in _FIELDS:
        if name == "t" or name not in raw:
            continue
        value, base = raw[name], getattr(default, name)
        if base is None:  # threshold: an int or None
            ok = value is None or (isinstance(value, int) and not isinstance(value, bool))
        elif isinstance(base, bool):
            ok = isinstance(value, bool)
        elif isinstance(base, float):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif isinstance(base, int):
            if isinstance(value, float) and abs(value) < LIMIT:  # a box edited by hand or by another client: round it
                value = round(value)
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = isinstance(value, str)
        if ok:
            values[name] = value
    layer = Layer(**values)
    layer = _replace(layer, rot=round(layer.rot / 90) * 90 % 360)  # (quarter turns only: anything else is the nearest)
    if layer.t == "sticker":
        if layer.name not in stickers.STICKERS:
            return None
        scale = min(stickers.MAX_SCALE, max(1, layer.scale))
        side = stickers.size(layer.name) * scale
        layer = _replace(layer, scale=scale, w=side, h=side)
    else:
        layer = _replace(layer, w=min(W, max(MIN_BOX, layer.w)), h=min(SH, max(MIN_BOX, layer.h)))  # (a box is never bigger than the label)
        if layer.fit not in FITS:
            layer = _replace(layer, fit="contain")
    return _replace(layer, x=min(LIMIT, max(-LIMIT, layer.x)), y=min(LIMIT, max(-LIMIT, layer.y)))


def _replace(layer: Layer, **changes) -> Layer:
    return Layer(**{**{f: getattr(layer, f) for f in _FIELDS}, **changes})


@lru_cache(maxsize=16)
def parse(text: str) -> tuple[Layer, ...]:
    """The layers, bottom to top. Anything that is not a well-formed layer is skipped."""
    try:
        raw = json.loads(text) if text else []
    except ValueError:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(layer for layer in map(_clean, raw) if layer is not None)[:MAX_LAYERS]


def encode(items) -> str:
    """The `layers` text for these layers, or "" for none."""
    return json.dumps([layer.to_dict() for layer in items], separators=(",", ":")) if items else ""


def canonical(text: str) -> str:
    """The text in the engine's own form ("" when nothing valid is there). Idempotent."""
    return encode(parse(text))


def sticker_layer(name: str, cx: int, cy: int, scale: int) -> Layer:
    """A sticker as a layer, from the older (name, centre x, centre y, scale) placement."""
    scale = min(stickers.MAX_SCALE, max(1, scale))
    side = stickers.size(name) * scale
    return Layer("sticker", cx - (side >> 1), cy - (side >> 1), side, side, name=name, scale=scale)


def image_paths(text: str) -> dict[int, str]:
    """{index in the canonical layer list: path} of the layers that have a picture."""
    return {i: layer.path for i, layer in enumerate(parse(text)) if layer.t == "image" and layer.path}


def with_paths(text: str, paths: dict[int, str]) -> str:
    """The layers with the picture path of layer i replaced by paths[i] (for the layers named in `paths`)."""
    return encode([_replace(layer, path=paths[i]) if i in paths else layer for i, layer in enumerate(parse(text))])


def has_content(text: str) -> bool:
    """Is any visible layer saying something: text that isn't blank, a QR code, a picture or a sticker?"""
    return any(not layer.hidden and (layer.text.strip() or layer.data.strip() or layer.path or layer.name)
               for layer in parse(text))


def map_paths(text: str, change) -> str:
    """The layers with every picture path replaced by change(path) (paths that are empty are left alone)."""
    return encode([_replace(layer, path=change(layer.path)) if layer.t == "image" and layer.path else layer
                   for layer in parse(text)])
