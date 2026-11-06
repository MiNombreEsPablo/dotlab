"""Pixel stickers, enlarged with nearest-neighbour. Two sources, no image files to ship: a few shapes drawn in code on a
24x24 grid (below), and the 16x16 tiles of Kenney's 1-Bit Pack (CC0) in `sticker_tiles.py`.

A label carries its placed stickers as `LabelSpec.stickers` (JSON text: `[[name, centre x, centre y, scale], ...]`), so a
sticker can still be moved, resized or removed after it is placed. They are drawn under the doodle ink.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageDraw

from .spec import SH, W
from .sticker_tiles import TILES

GRID = 24


def _star(d: ImageDraw.ImageDraw) -> None:
    points = []
    for i in range(10):
        r = 11.5 if i % 2 == 0 else 4.8
        a = -math.pi / 2 + i * math.pi / 5
        points.append((11.5 + r * math.cos(a), 12.5 + r * math.sin(a)))
    d.polygon(points, fill=1)


def _up(d: ImageDraw.ImageDraw) -> None:
    for x in (0, 12):
        d.polygon([(x + 5.5, 1), (x + 11, 9), (x + 8, 9), (x + 8, 22), (x + 3, 22), (x + 3, 9), (x, 9)], fill=1)


def _bolt(d: ImageDraw.ImageDraw) -> None:
    d.polygon([(14, 0), (4, 13), (11, 13), (8, 23), (20, 9), (13, 9), (18, 0)], fill=1)


def _glass(d: ImageDraw.ImageDraw) -> None:
    d.polygon([(4, 1), (19, 1), (17, 9), (13, 13), (10, 13), (6, 9)], fill=1)
    d.rectangle((10, 13, 13, 19), fill=1)
    d.rectangle((5, 20, 18, 22), fill=1)
    d.line((8, 3, 11, 7, 9, 10), fill=0, width=1)  # the crack


def _tick(d: ImageDraw.ImageDraw) -> None:
    d.line((3, 13, 9, 19, 21, 5), fill=1, width=4, joint="curve")


def _cross(d: ImageDraw.ImageDraw) -> None:
    d.line((4, 4, 19, 19), fill=1, width=4)
    d.line((19, 4, 4, 19), fill=1, width=4)


def _sun(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((6, 6, 17, 17), fill=1)
    for k in range(8):
        a = k * math.pi / 4
        d.line((11.5 + 8.5 * math.cos(a), 11.5 + 8.5 * math.sin(a), 11.5 + 11 * math.cos(a), 11.5 + 11 * math.sin(a)), fill=1, width=3)


def _moon(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((3, 2, 20, 21), fill=1)
    d.ellipse((9, 0, 26, 19), fill=0)


def _cloud(d: ImageDraw.ImageDraw) -> None:
    for box in ((1, 10, 12, 20), (7, 4, 18, 15), (12, 9, 23, 20)):
        d.ellipse(box, fill=1)
    d.rectangle((6, 14, 17, 20), fill=1)


_DRAWN: dict[str, tuple[str, Callable[[ImageDraw.ImageDraw], None]]] = {  # drawn on a GRID x GRID image
    "fragile": ("Fragile glass", _glass), "up": ("This side up", _up), "bolt": ("Lightning", _bolt),
    "tick": ("Tick", _tick), "cross": ("Cross", _cross),
    "star": ("Star", _star), "sun": ("Sun", _sun), "moon": ("Moon", _moon), "cloud": ("Cloud", _cloud),
}


def _from_rows(rows):
    def draw(d: ImageDraw.ImageDraw) -> None:
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == "1":
                    d.point((x, y), fill=1)
    return draw


STICKERS: dict[str, tuple[str, Callable[[ImageDraw.ImageDraw], None]]] = {
    **_DRAWN, **{key: (title, _from_rows(rows)) for key, (title, rows) in TILES.items()},
}
_SIZES = {key: len(rows) for key, (_, rows) in TILES.items()}  # a sticker is square: its side in dots at scale 1


def size(name: str) -> int:
    """A sticker's side in dots at scale 1 (24 for the ones drawn in code, 16 for the tiles)."""
    return _SIZES.get(name, GRID)


GROUPS = (  # the picker's themes, in order: (title, sticker keys). Every sticker is in exactly one (a test checks).
    ("Signs & marks", ("fragile", "up", "warning", "forbidden", "poison", "bolt", "question", "bang", "plus", "tick", "cross",
                       "arrow-up", "arrow-right", "arrow-down", "arrow-left")),
    ("Hearts & faces", ("heart", "heart-line", "heart-broken", "face-smile", "face-laugh", "face-angry", "face-meh",
                        "bubble-heart", "bubble-smile", "bubble-skull", "bubble-x", "skull", "bone")),
    ("Treasure & magic", ("key", "key-fancy", "key-skeleton", "potion", "potion-jar", "flask", "hourglass", "trophy", "crown",
                          "shield", "sword", "bow", "dollar")),
    ("Critters", ("cat", "dog", "horse", "bird", "duck", "bat", "snake", "croc", "octopus", "spider")),
    ("Nature & sky", ("sun", "moon", "star", "cloud", "tree", "pine", "cactus", "flame", "campfire")),
    ("Food", ("apple", "pear", "carrot", "cheese", "steak")),
    ("Games & music", ("die-2", "die-3", "die-4", "die-5", "die-6", "spade", "card", "rook", "pawn", "gamepad", "handheld",
                       "mouse", "note", "speaker")),
)
MAX_SCALE = 9  # 24 x 9 = 216 dots, still inside the sticker's height
MAX_PLACED = 40  # stickers on one label


@lru_cache(maxsize=512)
def mask(name: str, scale: int = 2) -> Image.Image:
    """The sticker as an ink mask (mode "L", 0 or 255), `scale` times enlarged. Shared: never modify it."""
    scale = min(MAX_SCALE, max(1, scale))
    side = size(name)
    img = Image.new("1", (side, side), 0)
    STICKERS[name][1](ImageDraw.Draw(img))
    return img.convert("L").point([0] * 128 + [255] * 128).resize((side * scale,) * 2, Image.Resampling.NEAREST)


# --- placed stickers: the label's `stickers` text -------------------------------------------------------------------


@lru_cache(maxsize=16)
def parse(text: str) -> tuple[tuple[str, int, int, int], ...]:
    """The placed stickers, bottom to top, as (name, centre x, centre y, scale). Anything that isn't a well-formed entry
    is skipped (stored files may be hand-edited), scales are clamped, and no more than MAX_PLACED are kept."""
    try:
        raw = json.loads(text) if text else []
    except ValueError:
        return ()
    if not isinstance(raw, list):
        return ()
    placed = []
    for item in raw:
        if (isinstance(item, list) and len(item) == 4 and isinstance(item[0], str) and item[0] in STICKERS
                and all(isinstance(v, int) and not isinstance(v, bool) and abs(v) < 10_000 for v in item[1:])):
            placed.append((item[0], item[1], item[2], min(MAX_SCALE, max(1, item[3]))))
    return tuple(placed[:MAX_PLACED])


def encode(placed) -> str:
    """The `stickers` text for these placements, or "" for none."""
    return json.dumps([list(p) for p in placed], separators=(",", ":")) if placed else ""


def canonical(text: str) -> str:
    """The text in the engine's own form ("" when nothing valid is placed). Idempotent."""
    return encode(parse(text))


def layer(text: str) -> Image.Image | None:
    """All placed stickers as one ink mask (mode "L", W x SH, 0 or 255), or None when there are none. A sticker that
    hangs over an edge is cut there."""
    placed = parse(text)
    if not placed:
        return None
    out = Image.new("L", (W, SH), 0)
    for name, cx, cy, scale in placed:
        m = mask(name, scale)
        out.paste(255, (cx - (m.width >> 1), cy - (m.height >> 1)), m)
    return out
