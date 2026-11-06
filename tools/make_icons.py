"""Draws Dotlab's logo and writes the files under src/dotlab/assets/. Run: python tools/make_icons.py

Everything is 1-bit pixel art drawn on its own grid and enlarged by whole numbers only (nearest-neighbour), so no size
is ever resampled into grey:
  - the tile, 64x64: a printer in front of the Synthwave sun and grid (the look of the app's own Synthwave background).
    Full-bleed and opaque, with the printer inside the circle a maskable icon keeps (80% of the width), so one drawing
    is the 192, 256 and 512 icons.
  - the mark, 16x16: the printer on its floor, as an SVG of squares. The banner paints it with the theme's text colour
    (a CSS mask), so every look gets its own tint.
  - the favicon, the mark on a white plate (a transparent black mark would vanish on a dark browser tab), at 16 and 32.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "src" / "dotlab" / "assets"
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
SIZE, HORIZON = 64, 36

MARK = """
................
................
....########....
....#......#....
....#.#..#.#....
....#......#....
....#.#.##.#....
.##############.
.#............#.
.#.##.#######.#.
.#............#.
.##############.
................
################
.#.#.#.#.#.#.#.#
#.#.#.#.#.#.#.#.
""".strip().splitlines()


def tile() -> Image.Image:
    im = Image.new("1", (SIZE, SIZE), 1)
    px, d = im.load(), ImageDraw.Draw(im)
    r = 20  # the sun: dense at the top, thinning towards the horizon
    for y in range(HORIZON - r, HORIZON):
        for x in range(SIZE):
            if (x - 32) ** 2 + (y - HORIZON) ** 2 <= r * r:
                level = 0.9 * (1 - (y - (HORIZON - r)) / r) + 0.08
                if (BAYER[y % 4][x % 4] + 0.5) / 16 < level:
                    px[x, y] = 0
    for k in range(1, 7):  # the grid: rows bunch up towards the horizon, columns run to the vanishing point
        y = HORIZON + round((SIZE - 1 - HORIZON) * (k / 6) ** 2)
        d.line([(0, y), (SIZE - 1, y)], fill=0)
    for m in range(-5, 6):
        d.line([(32, HORIZON), (32 + m * 13, SIZE - 1)], fill=0)
    d.line([(0, HORIZON), (SIZE - 1, HORIZON)], fill=0)
    d.rectangle([22, 26, 41, 41], fill=1, outline=0)  # the sticker coming out of the slot
    for j, row in enumerate(["X.XX", "XX.X"]):
        for i, ch in enumerate(row):
            if ch == "X":
                d.rectangle([25 + i * 4, 30 + j * 4, 26 + i * 4, 31 + j * 4], fill=0)
    d.rounded_rectangle([17, 40, 47, 52], radius=3, fill=1, outline=0)  # the printer
    d.rectangle([20, 43, 44, 43], fill=0)  # slot
    d.rectangle([20, 47, 21, 48], fill=0)  # LED
    d.rectangle([26, 47, 41, 48], outline=0)  # button
    return im


def mark_svg() -> str:
    cells = [(x, y) for y, row in enumerate(MARK) for x, c in enumerate(row) if c == "#"]
    path = "".join(f"M{x} {y}h1v1h-1z" for x, y in cells)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">'
            f'<path d="{path}"/></svg>\n')


def favicon() -> Image.Image:
    im = Image.new("1", (16, 16), 1)
    for y, row in enumerate(MARK):
        for x, c in enumerate(row):
            if c == "#":
                im.putpixel((x, y), 0)
    return im


def enlarged(im: Image.Image, factor: int) -> Image.Image:
    return im.resize((im.width * factor, im.height * factor), Image.NEAREST)


def main() -> None:
    for old in ("icon.svg", "icon-mark.png"):
        (ASSETS / old).unlink(missing_ok=True)
    t = tile()
    for factor in (3, 4, 8):  # 192 (home screen), 256 (README), 512 (install)
        enlarged(t, factor).save(ASSETS / f"icon-{SIZE * factor}.png", optimize=True)
    (ASSETS / "icon-mark.svg").write_text(mark_svg(), encoding="utf-8")
    f = favicon()
    for factor in (1, 2):
        enlarged(f, factor).save(ASSETS / f"favicon-{16 * factor}.png", optimize=True)


if __name__ == "__main__":
    main()
