"""Our own pixel stickers: 24x24 1-bit icons drawn in code (no image files to ship), enlarged with nearest-neighbour. Qt-free.

They are stamped into the doodle ink, so a sticker is just part of the drawing.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageDraw

GRID = 24


def _star(d: ImageDraw.ImageDraw) -> None:
    points = []
    for i in range(10):
        r = 11.5 if i % 2 == 0 else 4.8
        a = -math.pi / 2 + i * math.pi / 5
        points.append((11.5 + r * math.cos(a), 12.5 + r * math.sin(a)))
    d.polygon(points, fill=1)


def _heart(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((1, 3, 12, 13), fill=1)
    d.ellipse((11, 3, 22, 13), fill=1)
    d.polygon([(1, 10), (22, 10), (11.5, 22)], fill=1)


def _smiley(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((1, 1, 22, 22), outline=1, width=2)
    d.rectangle((7, 7, 9, 11), fill=1)
    d.rectangle((14, 7, 16, 11), fill=1)
    d.arc((5, 5, 18, 18), 20, 160, fill=1, width=2)


def _warning(d: ImageDraw.ImageDraw) -> None:
    d.polygon([(11.5, 1), (23, 22), (0, 22)], fill=1)
    d.polygon([(11.5, 5), (20, 20), (3, 20)], fill=0)
    d.rectangle((10, 10, 12, 14), fill=1)
    d.rectangle((10, 16, 12, 17), fill=1)


def _arrow(d: ImageDraw.ImageDraw) -> None:
    d.polygon([(1, 9), (13, 9), (13, 3), (23, 12), (13, 21), (13, 15), (1, 15)], fill=1)


def _up(d: ImageDraw.ImageDraw) -> None:
    for x in (0, 12):
        d.polygon([(x + 5.5, 1), (x + 11, 9), (x + 8, 9), (x + 8, 22), (x + 3, 22), (x + 3, 9), (x, 9)], fill=1)


def _bolt(d: ImageDraw.ImageDraw) -> None:
    d.polygon([(14, 0), (4, 13), (11, 13), (8, 23), (20, 9), (13, 9), (18, 0)], fill=1)


def _skull(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((3, 1, 20, 16), fill=1)
    d.rectangle((7, 13, 16, 21), fill=1)
    d.ellipse((6, 7, 10, 12), fill=0)
    d.ellipse((13, 7, 17, 12), fill=0)
    d.rectangle((11, 13, 12, 15), fill=0)
    for x in (10, 13):
        d.line((x, 18, x, 21), fill=0)


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


def _forbidden(d: ImageDraw.ImageDraw) -> None:
    d.ellipse((1, 1, 22, 22), outline=1, width=3)
    d.line((4, 19, 19, 4), fill=1, width=3)


STICKERS: dict[str, tuple[str, Callable[[ImageDraw.ImageDraw], None]]] = {
    "fragile": ("Fragile glass", _glass), "up": ("This side up", _up), "warning": ("Warning", _warning),
    "forbidden": ("Forbidden", _forbidden), "skull": ("Skull", _skull), "bolt": ("Lightning", _bolt),
    "arrow": ("Arrow", _arrow), "heart": ("Heart", _heart), "star": ("Star", _star), "smiley": ("Smiley", _smiley),
    "tick": ("Tick", _tick), "cross": ("Cross", _cross),
}
MAX_SCALE = 6


@lru_cache(maxsize=64)
def mask(name: str, scale: int = 2) -> Image.Image:
    """The sticker as an ink mask (mode "L", 0 or 255), `scale` times enlarged. Shared: never modify it."""
    scale = min(MAX_SCALE, max(1, scale))
    img = Image.new("1", (GRID, GRID), 0)
    STICKERS[name][1](ImageDraw.Draw(img))
    return img.convert("L").point([0] * 128 + [255] * 128).resize((GRID * scale,) * 2, Image.Resampling.NEAREST)
