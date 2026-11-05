"""Draw a LabelSpec onto a 384x240 grayscale canvas. Everything stays inside the top SH rows."""
from __future__ import annotations

import functools
import math
import random
import shutil
import subprocess

import qrcode
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

from . import doodle
from . import fonts as bundled_fonts
from . import imaging
from .spec import (
    ALIGNMENTS,
    BACKGROUNDS,
    BORDER_STYLES,
    EFFECTS,
    H,
    IMAGE_LAYOUTS,
    MARGIN,
    SH,
    VALIGNMENTS,
    W,
    LabelSpec,
)

FALLBACK_FONT_PATHS = (str(bundled_fonts.FONT_DIR / "DejaVuSans-Bold.ttf"),)
BACKGROUND_FONTS = {"matrix": "DejaVu Sans Mono"}  # backgrounds that draw text, with the (bundled) font they use
HAS_FONTCONFIG = shutil.which("fc-match") is not None  # Linux; Windows/macOS use only the bundled fonts
ITALIC_SHEAR = 0.25
BAR_H = 14
MAX_FONT_SIZE = 120
# Space a border takes from the edge of the frame; text keeps this much distance plus a gap.
BORDER_INSET = {
    "solid": 3, "double": 9, "dotted": 6, "checker": 8, "bevel": 9, "marquee": 15,
    "chamfer": 10, "brackets": 7, "ticks": 9,
}


class PrinterError(Exception):
    pass


# --- fonts -------------------------------------------------------------------------------------------------------


@functools.cache
def font_path(family: str, bold: bool, italic: bool = False) -> tuple[str, bool]:
    """(file, has_native_slant): a bundled font if the family is one of ours, else fontconfig (which falls back
    for unknown names)."""
    bundled = bundled_fonts.bundled_font(family)
    if bundled:
        return bundled.pick(bold, italic)
    if not HAS_FONTCONFIG:
        return bundled_fonts.bundled_font("DejaVu Sans").pick(bold, italic)
    style = ("bold" if bold else "regular") + (":italic" if italic else "")
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}|%{slant}", f"{family}:{style}"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        path, _, slant = out.partition("|")
        if path:
            return path, slant.isdigit() and int(slant) > 0
    except (OSError, subprocess.SubprocessError):
        pass
    return bundled_fonts.bundled_font("DejaVu Sans").pick(bold, italic)


@functools.cache
def list_font_families() -> list[str]:
    """Installed font families that cover English, as fontconfig names them (what font_path resolves against)."""
    if not HAS_FONTCONFIG:
        return []
    try:
        out = subprocess.run(
            ["fc-list", ":lang=en", "family"], capture_output=True, text=True, timeout=15, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    families = {line.split(",")[0].strip() for line in out.splitlines()}
    # macOS lists hidden internal families (".SF NS", ".Aqua Kana"); users can't sensibly pick those
    return sorted((f for f in families if f and not f.startswith(".")), key=str.casefold)


def _apply_weight(font: ImageFont.FreeTypeFont, bold: bool) -> None:
    """Variable fonts load at their default instance, so the bold toggle must set the weight axis itself."""
    try:
        axes = font.get_variation_axes()
    except (OSError, AttributeError):  # static font
        return
    target = 700 if bold else 400
    values = []
    for axis in axes:
        name = axis["name"].decode(errors="ignore") if isinstance(axis["name"], bytes) else str(axis["name"])
        if name.lower() == "weight":
            values.append(min(max(target, axis["minimum"]), axis["maximum"]))
        else:
            values.append(axis["default"])
    try:
        font.set_variation_by_axes(values)
    except OSError:
        pass


def _font(path: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in (path, *FALLBACK_FONT_PATHS):
        try:
            # BASIC layout on purpose: Raqm (when this Pillow has it) kerns differently and draws some fonts heavier, so
            # labels would depend on how each machine's Pillow was built, and the web build (Pyodide: no Raqm) would
            # print differently from the desktop.
            font = ImageFont.truetype(candidate, size, layout_engine=ImageFont.Layout.BASIC)
        except OSError:
            continue
        _apply_weight(font, bold)
        return font
    raise PrinterError(f"cannot load font {path!r}")


@functools.cache
def _cmap(path: str) -> frozenset[int] | None:
    try:
        return frozenset(TTFont(path, lazy=True, fontNumber=0).getBestCmap() or ())
    except Exception:  # fontTools raises many types for odd files; unreadable means "assume covered"
        return None


def covers(path: str, ch: str) -> bool:
    """Does the font file have a glyph for this character?"""
    cmap = _cmap(path)
    return cmap is None or ord(ch) in cmap


class _FontSet:
    """A primary font plus a Japanese fallback for the glyphs it lacks (Pillow has no per-glyph fallback)."""

    def __init__(self, path: str, size: int, bold: bool) -> None:
        self.path, self.size, self.bold = path, size, bold
        self.primary = _font(path, size, bold)
        self._fallback_path = bundled_fonts.FALLBACK_JA.pick(bold, False)[0]
        self._fallback: ImageFont.FreeTypeFont | None = None

    def pick(self, ch: str) -> ImageFont.FreeTypeFont:
        if ch.isspace() or covers(self.path, ch):
            return self.primary
        if covers(self._fallback_path, ch):
            if self._fallback is None:
                self._fallback = _font(self._fallback_path, self.size, self.bold)
            return self._fallback
        return self.primary  # nothing has it: let the primary draw its own missing-glyph box


# --- text --------------------------------------------------------------------------------------------------------


def _checker(w: int, h: int) -> Image.Image:
    even = bytes([255, 0] * (w // 2 + 1))[:w]
    odd = bytes([0, 255] * (w // 2 + 1))[:w]
    return Image.frombytes("L", (w, h), b"".join(even if y % 2 == 0 else odd for y in range(h)))


def _dots(w: int, h: int) -> Image.Image:
    """25% coverage: every other pixel on every other row (a light dither, used for glow)."""
    even = bytes([255, 0] * (w // 2 + 1))[:w]
    blank = bytes(w)
    return Image.frombytes("L", (w, h), b"".join(even if y % 2 == 0 else blank for y in range(h)))


def _runs(fs: _FontSet, line: str) -> list[list]:
    """Split a line into [text, font] runs so each glyph is drawn by a font that has it."""
    runs: list[list] = []
    for ch in line:
        font = fs.pick(ch)
        if runs and runs[-1][1] is font:
            runs[-1][0] += ch
        else:
            runs.append([ch, font])
    return runs


def _layout(probe: ImageDraw.ImageDraw, text: str, fs: _FontSet, align: str, spacing: int):
    """Place every run ourselves. Returns (placed, bbox, pitch, line_count), placed = [(run, font, x, baseline, line)].

    Pillow's multiline_text widens the line pitch by 2*stroke_width, so a stroked pass (outline, glow, halo)
    drifts further from the unstroked pass on every line. A fixed pitch keeps all passes registered, and
    baseline anchoring lets runs from different fonts sit on the same line.
    """
    primary = fs.primary
    pitch = probe.textbbox((0, 0), "A", font=primary)[3] + spacing
    ascent = primary.getmetrics()[0]
    lines = [_runs(fs, line) for line in text.split("\n")]
    widths = [sum(probe.textlength(run, font=f) for run, f in runs) for runs in lines]
    block = max(widths)
    placed, boxes = [], []
    for i, (runs, lw) in enumerate(zip(lines, widths)):
        x = {"left": 0, "center": (block - lw) / 2, "right": block - lw}[align]
        baseline = i * pitch + ascent
        for run, f in runs:
            placed.append((run, f, x, baseline, i))
            if run.strip():
                boxes.append(probe.textbbox((x, baseline), run, font=f, anchor="ls"))
            x += probe.textlength(run, font=f)
    if not boxes:
        return placed, (0, 0, 1, 1), pitch, len(lines)
    bbox = tuple(math.ceil(v) for v in (
        min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)))
    return placed, bbox, pitch, len(lines)


_BINARY = [0] * 128 + [255] * 128  # lookup table: 50 % threshold


def _text_layer(text, fs, align, effect, halo, shear):
    """Render text with its effect. Returns (value, alpha) cropped to the painted area:
    paste `value` through `alpha` to draw it (value holds the black/white pixels, alpha where they apply)."""
    spacing = fs.size // 5
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines, (l, t, r, b), pitch, n_lines = _layout(probe, text, fs, align, spacing)
    pad = 12
    ox, oy = pad - min(l, 0), pad - min(t, 0)
    w, h = r + ox + pad, b + oy + pad
    value, alpha = Image.new("L", (w, h), 255), Image.new("L", (w, h), 0)
    draws = (ImageDraw.Draw(value), ImageDraw.Draw(alpha))

    def draw_lines(draw, off, fill, stroke):
        for run, font, x, y, _ in lines:
            draw.text(
                (ox + off[0] + x, oy + off[1] + y), run, font=font, fill=fill, anchor="ls",
                stroke_width=stroke, stroke_fill=fill,
            )

    def put(off, fill, stroke=0):
        for draw, f in zip(draws, (fill, 255)):
            draw_lines(draw, off, f, stroke)

    def glyph(off=(0, 0), stroke=0):
        """Mask of the plain (optionally thickened) text."""
        m = Image.new("L", (w, h), 0)
        draw_lines(ImageDraw.Draw(m), off, 255, stroke)
        return m

    def paint(mask, fill):
        value.paste(fill, mask=mask)
        alpha.paste(255, mask=mask)

    if effect == "outline":
        put((0, 0), 0, 3)
        put((0, 0), 255)
    elif effect == "3d":
        for i in range(6, 0, -1):
            put((i, i), 0, 1)
        put((0, 0), 0, 2)
        put((0, 0), 255)
    elif effect == "shadow":
        if halo:
            put((4, 4), 255, 2)
            put((0, 0), 255, 2)
        shadow = glyph((4, 4))
        value.paste(255, mask=shadow)  # opaque white under the dither so the background doesn't show through
        value.paste(0, mask=ImageChops.multiply(shadow, _checker(w, h)))
        alpha.paste(255, mask=shadow)
        put((0, 0), 0)
    elif effect == "glitch":
        unit = max(0.15, fs.size / 60)  # displacements scale with the text so small labels stay legible
        base = glyph()
        sliced = base.copy()
        for i in range(n_lines):  # displaced horizontal slices on every line, like a bad VHS frame
            ly = i * pitch
            for frac, dx in ((0.22, 8), (0.58, -10)):
                y0 = min(h - 1, oy + ly + int(frac * pitch))
                y1 = min(h, y0 + max(2, fs.size // 10))
                shift = round((dx if i % 2 == 0 else -dx) * unit)
                band = base.crop((0, y0, w, y1))
                sliced.paste(0, (0, y0, w, y1))
                sliced.paste(band, (shift, y0))
        # the fringe copy and scanline gaps only read at larger sizes; small text keeps just the slice shifts
        ghost = Image.new("L", (w, h), 0)
        if fs.size >= 24:
            ghost = ImageChops.multiply(glyph((-max(1, round(6 * unit)), 0)), _checker(w, h))  # dithered fringe copy
        union = ImageChops.lighter(ImageChops.lighter(sliced, ghost), base)
        if halo:
            paint(union.filter(ImageFilter.MaxFilter(7)), 255)
        paint(union, 255)
        value.paste(0, mask=ghost)
        value.paste(0, mask=sliced)
        if fs.size >= 30:
            for y in range(oy, h, max(5, round(6 * unit))):  # thin white scanline gaps through the text
                value.paste(255, (0, y, w, y + 1), mask=sliced.crop((0, y, w, y + 1)))
    elif effect == "neon":
        glow = glyph(stroke=7)
        paint(glow, 255)
        value.paste(0, mask=ImageChops.multiply(glow, _dots(w, h)))  # dithered halo
        put((0, 0), 0, 3)
        put((0, 0), 255, 1)  # white tube gap between the outer line and the core
        put((0, 0), 0)
    elif effect == "scanlines":
        if halo:
            put((0, 0), 255, 3)
        put((0, 0), 0)
        period = max(4, fs.size // 9)
        gaps = Image.new("L", (w, h), 0)
        gd = ImageDraw.Draw(gaps)
        for y in range(oy, h, period):
            gd.rectangle([0, y, w, y + max(1, period // 3) - 1], fill=255)
        value.paste(255, mask=ImageChops.multiply(gaps, glyph()))
    else:
        if halo:
            put((0, 0), 255, 3)
        put((0, 0), 0)

    if shear:
        w2 = w + math.ceil(shear * h)
        coeffs = (1, shear, -shear * h, 0, 1, 0)
        value = value.transform((w2, h), Image.Transform.AFFINE, coeffs, fillcolor=255)
        alpha = alpha.transform((w2, h), Image.Transform.AFFINE, coeffs, fillcolor=0)
    # Anti-aliased edges would be turned into scattered dots by the Floyd-Steinberg pass over the whole label (ragged,
    # speckled letters). Binarising at 50 % coverage keeps the ink (about 97 % on average) and gives clean edges.
    value, alpha = value.point(_BINARY), alpha.point(_BINARY)
    box = alpha.getbbox() or (0, 0, 1, 1)
    return value.crop(box), alpha.crop(box)


def _fit_text_layer(text, path, bold, shear, align, effect, halo, box_w, box_h, max_size):
    """Largest font size (binary search) whose rendered layer fits the box."""
    sizes = list(range(8, max_size + 1, 2)) or [8]
    if sizes[-1] != max_size and max_size > 8:
        sizes.append(max_size)

    def build(size):
        return _text_layer(text, _FontSet(path, size, bold), align, effect, halo, shear)

    best, lo, hi = None, 0, len(sizes) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        layer = build(sizes[mid])
        if layer[0].width <= box_w and layer[0].height <= box_h:
            best, lo = layer, mid + 1
        else:
            hi = mid - 1
    return best or build(sizes[0])


# --- decoration --------------------------------------------------------------------------------------------------

_BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


@functools.cache
def _background(name: str) -> Image.Image:  # cached: some are slow and all are deterministic
    img = Image.new("L", (W, SH), 255)
    d = ImageDraw.Draw(img)
    if name == "checker":
        for y in range(0, SH, 8):
            for x in range(0, W, 8):
                if (x // 8 + y // 8) % 2 == 0:
                    d.rectangle([x, y, x + 7, y + 7], fill=0)
    elif name == "dots":
        for row, y in enumerate(range(3, SH, 8)):
            for x in range(3 + 4 * (row % 2), W, 8):
                d.rectangle([x, y, x + 1, y + 1], fill=0)
    elif name == "stripes":
        for k in range(-SH, W, 12):
            d.line([(k, SH), (k + SH, 0)], fill=0, width=3)
    elif name == "gradient":
        px = img.load()
        for y in range(SH):
            level = y / (SH - 1)  # white at the top fading to black at the bottom
            for x in range(W):
                if level > (_BAYER[y % 4][x % 4] + 0.5) / 16:
                    px[x, y] = 0
    elif name == "stars":
        for row, y in enumerate(range(10, SH, 28)):
            for x in range(10 + 14 * (row % 2), W, 28):
                d.line([(x - 4, y), (x + 4, y)], fill=0, width=1)
                d.line([(x, y - 4), (x, y + 4)], fill=0, width=1)
                d.line([(x - 3, y - 3), (x + 3, y + 3)], fill=0, width=1)
                d.line([(x - 3, y + 3), (x + 3, y - 3)], fill=0, width=1)
    elif name == "grid":
        for x in range(0, W, 16):
            d.line([(x, 0), (x, SH)], fill=0, width=1)
        for y in range(0, SH, 16):
            d.line([(0, y), (W, y)], fill=0, width=1)
    elif name == "scanlines":
        for y in range(0, SH, 4):
            d.line([(0, y), (W, y)], fill=0, width=1)
    elif name == "circuit":
        _circuit(d)
    elif name == "hexgrid":
        r = 12
        for col in range(-1, int(W / (1.5 * r)) + 2):
            for row in range(-1, int(SH / (math.sqrt(3) * r)) + 2):
                cx = col * 1.5 * r
                cy = row * math.sqrt(3) * r + (math.sqrt(3) / 2 * r if col % 2 else 0)
                pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
                d.line(pts + [pts[0]], fill=0, width=1)
    elif name == "synthwave":
        _synthwave(img)
    elif name == "matrix":
        _matrix(d)
    elif name == "halftone":
        for row, y in enumerate(range(4, SH, 8)):
            radius = 0.5 + 3.4 * y / SH  # dots swell towards the bottom
            for x in range(4 + 4 * (row % 2), W, 8):
                d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=0)
    return img


def _circuit(d: ImageDraw.ImageDraw) -> None:
    """PCB traces: random walks along 45-degree directions ending in via rings (seeded, so stable)."""
    rng = random.Random(7)
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
    for _ in range(26):
        x, y = rng.randrange(0, W, 8), rng.randrange(0, SH, 8)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], outline=0, width=2)
        for _ in range(rng.randint(2, 4)):
            dx, dy = rng.choice(dirs)
            n = rng.randrange(2, 6) * 8
            nx, ny = x + dx * n, y + dy * n
            d.line([(x, y), (nx, ny)], fill=0, width=2)
            x, y = nx, ny
        d.ellipse([x - 3, y - 3, x + 3, y + 3], outline=0, fill=255, width=2)


def _synthwave(img: Image.Image) -> None:
    """Striped dithered sun on the horizon over a perspective grid."""
    d = ImageDraw.Draw(img)
    horizon, cx, radius = int(SH * 0.55), W // 2, 62
    px = img.load()
    for y in range(horizon - radius, horizon):
        level = 0.3 + 0.55 * (y - (horizon - radius)) / radius  # denser towards the horizon
        half = math.sqrt(max(0, radius**2 - (y - horizon) ** 2))
        for x in range(int(cx - half), int(cx + half) + 1):
            if 0 <= x < W and level > (_BAYER[y % 4][x % 4] + 0.5) / 16:
                px[x, y] = 0
    for offset, thickness in ((6, 4), (16, 3), (27, 2), (40, 2), (55, 1)):  # slats get thicker near the horizon
        d.rectangle([0, horizon - offset, W, horizon - offset + thickness - 1], fill=255)
    d.rectangle([0, horizon, W, SH], fill=255)
    d.line([(0, horizon), (W, horizon)], fill=0, width=2)
    for i in range(-14, 15):
        d.line([(cx, horizon), (cx + i * 44, SH)], fill=0, width=1)
    for k in range(1, 8):
        y = horizon + int((k / 7) ** 2 * (SH - horizon))
        d.line([(0, y), (W, y)], fill=0, width=1)


def _matrix(d: ImageDraw.ImageDraw) -> None:
    """Falling columns of 0/1, dense at the head and thinning to a tail (seeded)."""
    rng = random.Random(11)
    font = _font(font_path(BACKGROUND_FONTS["matrix"], False)[0], 10)
    for x in range(2, W, 11):
        length, start = rng.randrange(4, 20), rng.randrange(-8, 14)
        for i in range(length):
            if rng.random() < (i + 1) / length:
                d.text((x, (start + i) * 11), rng.choice("01"), font=font, fill=0)


def sorted_box(xa: int, ya: int, xb: int, yb: int) -> list[int]:
    return [min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)]


def _border(d: ImageDraw.ImageDraw, style: str, x0: int, y0: int, x1: int, y1: int) -> None:
    if style == "double":
        d.rectangle([x0, y0, x1, y1], outline=0, width=2)
        d.rectangle([x0 + 5, y0 + 5, x1 - 5, y1 - 5], outline=0, width=2)
    elif style == "dotted":
        for x in range(x0 + 1, x1 - 2, 8):
            d.rectangle([x, y0 + 1, x + 3, y0 + 4], fill=0)
            d.rectangle([x, y1 - 4, x + 3, y1 - 1], fill=0)
        for y in range(y0 + 1, y1 - 2, 8):
            d.rectangle([x0 + 1, y, x0 + 4, y + 3], fill=0)
            d.rectangle([x1 - 4, y, x1 - 1, y + 3], fill=0)
    elif style == "checker":
        cell = 6
        for i, x in enumerate(range(x0, x1 + 1, cell)):
            if i % 2 == 0:
                for y in (y0, y1 - cell + 1):
                    d.rectangle([x, y, min(x + cell - 1, x1), y + cell - 1], fill=0)
        for i, y in enumerate(range(y0, y1 + 1, cell)):
            if i % 2 == 0:
                for x in (x0, x1 - cell + 1):
                    d.rectangle([x, y, x + cell - 1, min(y + cell - 1, y1)], fill=0)
    elif style == "bevel":
        d.rectangle([x0, y0, x1, y1], outline=0, width=1)
        d.rectangle([x0 + 1, y1 - 3, x1 - 1, y1 - 1], fill=0)  # dark bottom and right edges read as a raised panel
        d.rectangle([x1 - 3, y0 + 1, x1 - 1, y1 - 1], fill=0)
        d.rectangle([x0 + 4, y0 + 4, x1 - 6, y1 - 6], outline=0, width=1)
    elif style == "marquee":
        r = 4
        bulbs = [(x, y0 + 7) for x in range(x0 + 7, x1 - 6, 14)]
        bulbs += [(x1 - 7, y) for y in range(y0 + 7 + 14, y1 - 6, 14)]
        bulbs += [(x, y1 - 7) for x in range(x1 - 7, x0 + 6, -14)]
        bulbs += [(x0 + 7, y) for y in range(y1 - 7 - 14, y0 + 7, -14)]
        for i, (cx, cy) in enumerate(bulbs):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, fill=0 if i % 2 == 0 else 255, width=1)
    elif style == "chamfer":
        c = 10  # cut corners plus little tabs, like a game-UI panel
        # the 3-wide line is centred on its path, so keep the path 1 dot inside the frame
        ax0, ay0, ax1, ay1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
        pts = [(ax0 + c, ay0), (ax1 - c, ay0), (ax1, ay0 + c), (ax1, ay1 - c), (ax1 - c, ay1), (ax0 + c, ay1), (ax0, ay1 - c), (ax0, ay0 + c)]
        d.line(pts + [pts[0]], fill=0, width=3, joint="curve")
        d.rectangle([x0 + c + 10, y0, x0 + c + 44, y0 + 6], fill=0)
        d.rectangle([x1 - c - 44, y1 - 6, x1 - c - 10, y1], fill=0)
    elif style == "brackets":
        arm, t = 28, 4  # HUD corner brackets around a hairline frame
        d.rectangle([x0 + 6, y0 + 6, x1 - 6, y1 - 6], outline=0, width=1)
        for cx, sx in ((x0, 1), (x1, -1)):
            for cy, sy in ((y0, 1), (y1, -1)):
                d.rectangle(sorted_box(cx, cy, cx + sx * arm, cy + sy * t), fill=0)
                d.rectangle(sorted_box(cx, cy, cx + sx * t, cy + sy * arm), fill=0)
    elif style == "ticks":
        d.rectangle([x0 + 6, y0 + 6, x1 - 6, y1 - 6], outline=0, width=1)  # ruler scale around a hairline frame
        for i, x in enumerate(range(x0 + 6, x1 - 5, 8)):
            n = 6 if i % 5 == 0 else 3
            d.line([(x, y0 + 6), (x, y0 + 6 - n)], fill=0)
            d.line([(x, y1 - 6), (x, y1 - 6 + n)], fill=0)
        for i, y in enumerate(range(y0 + 6, y1 - 5, 8)):
            n = 6 if i % 5 == 0 else 3
            d.line([(x0 + 6, y), (x0 + 6 - n, y)], fill=0)
            d.line([(x1 - 6, y), (x1 - 6 + n, y)], fill=0)
    else:  # solid
        d.rectangle([x0, y0, x1, y1], outline=0, width=3)


def _hazard_bar(img: Image.Image, y0: int) -> None:
    band = Image.new("L", (W, BAR_H), 255)
    bd = ImageDraw.Draw(band)
    for x in range(-BAR_H, W + BAR_H, 20):
        bd.polygon([(x, BAR_H), (x + 10, BAR_H), (x + 10 + BAR_H, 0), (x + BAR_H, 0)], fill=0)
    bd.rectangle([0, 0, W - 1, BAR_H - 1], outline=0, width=1)
    img.paste(band, (0, y0))


def _picture(spec: LabelSpec, *args, **kwargs) -> Image.Image:
    """`imaging.process` with failures turned into messages that say what to do about them."""
    try:
        return imaging.process(spec, *args, **kwargs)
    except FileNotFoundError:
        raise PrinterError(f"The image file is missing: {spec.image_path}") from None
    except UnidentifiedImageError:
        raise PrinterError(f"Couldn't read {spec.image_path}: it isn't a picture file this app can open.") from None
    except OSError as e:  # e.g. permission denied
        raise PrinterError(f"Couldn't read the image {spec.image_path}: {e.strerror or e}") from e


def _qr_image(data: str, side: int) -> Image.Image:
    qr = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    try:
        qr.make(fit=True)
    except (ValueError, qrcode.exceptions.DataOverflowError):
        raise PrinterError("That text is too long for a QR code; shorten it.") from None
    matrix = qr.get_matrix()
    scale = max(1, side // len(matrix))
    img = Image.new("L", (len(matrix) * scale,) * 2, 255)
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if filled:
                draw.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=0)
    return img


# --- render ------------------------------------------------------------------------------------------------------


def _pick(value: str, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


def render(spec: LabelSpec) -> Image.Image:
    """Grayscale W x H canvas; everything is drawn inside the top SH rows."""
    img = _compose(spec)
    ink = doodle.decode(spec.doodle)
    if ink is not None:  # the doodle is the top layer, over the picture, QR and text alike
        img.paste(0, (0, 0), ink)
    return img


def _compose(spec: LabelSpec) -> Image.Image:
    img = Image.new("L", (W, H), 255)

    layout = _pick(spec.image_layout, IMAGE_LAYOUTS, "only") if spec.image_path else ""
    if layout == "only":
        src = _picture(spec)
        img.paste(src, ((W - src.width) // 2, (SH - src.height) // 2))
        return img

    background = _pick(spec.background, BACKGROUNDS, "none")
    if layout == "behind":  # the picture is the backdrop; text over it gets the same halo as over a pattern
        img.paste(_picture(spec, (W, SH), cover=True), (0, 0))
    elif background != "none":
        img.paste(_background(background), (0, 0))
    backdrop = background != "none" or layout == "behind"
    draw = ImageDraw.Draw(img)

    top, bottom = 0, SH  # frame: what's left after the hazard bars
    if spec.bars:
        _hazard_bar(img, 0)
        _hazard_bar(img, SH - BAR_H)
        top, bottom = BAR_H, SH - BAR_H
    margin = MARGIN
    if spec.border:
        style = _pick(spec.border_style, BORDER_STYLES, "solid")
        _border(draw, style, 0, top, W - 1, bottom - 1)
        margin = max(MARGIN, BORDER_INSET[style] + 4)

    ax0, ax1, ay0, ay1 = margin, W - margin, top + margin, bottom - margin
    if layout in ("left", "right", "top", "bottom"):  # carve the picture's share out; QR and text use what is left
        share = min(80, max(20, spec.image_size)) / 100
        if layout in ("left", "right"):
            size = int((ax1 - ax0) * share)
            region = (ax0, ay0, ax0 + size, ay1) if layout == "left" else (ax1 - size, ay0, ax1, ay1)
            ax0, ax1 = (ax0 + size + MARGIN, ax1) if layout == "left" else (ax0, ax1 - size - MARGIN)
        else:
            size = int((ay1 - ay0) * share)
            region = (ax0, ay0, ax1, ay0 + size) if layout == "top" else (ax0, ay1 - size, ax1, ay1)
            ay0, ay1 = (ay0 + size + MARGIN, ay1) if layout == "top" else (ay0, ay1 - size - MARGIN)
        src = _picture(spec, (region[2] - region[0], region[3] - region[1]))
        img.paste(src, (region[0] + (region[2] - region[0] - src.width) // 2,
                        region[1] + (region[3] - region[1] - src.height) // 2))
    text_w = ax1 - ax0
    if spec.qr:
        qimg = _qr_image(spec.qr, ay1 - ay0)
        qx = ax1 - qimg.width if spec.text else ax0 + (text_w - qimg.width) // 2
        qy = ay0 + (ay1 - ay0 - qimg.height) // 2
        draw.rectangle([qx - 4, qy - 4, qx + qimg.width + 3, qy + qimg.height + 3], fill=255)  # quiet zone
        img.paste(qimg, (qx, qy))
        text_w = qx - MARGIN - ax0

    if spec.text and text_w > 0:
        align = _pick(spec.align, ALIGNMENTS, "center")
        valign = _pick(spec.valign, VALIGNMENTS, "middle")
        effect = _pick(spec.effect, EFFECTS, "none")
        path, native_slant = font_path(spec.font, spec.bold, spec.italic)
        shear = ITALIC_SHEAR if spec.italic and not native_slant else 0
        max_size = min(MAX_FONT_SIZE, spec.size) if spec.size > 0 else MAX_FONT_SIZE
        value, alpha = _fit_text_layer(
            spec.text.replace("\\n", "\n"), path, spec.bold, shear, align, effect, backdrop,
            text_w, ay1 - ay0, max_size,
        )
        x = ax0 + {"left": 0, "center": (text_w - value.width) // 2, "right": text_w - value.width}[align]
        y = ay0 + {"top": 0, "middle": (ay1 - ay0 - value.height) // 2, "bottom": ay1 - ay0 - value.height}[valign]
        img.paste(value, (x, y), alpha)
    return img


def label_bitmap(spec: LabelSpec, scale: int = 1) -> Image.Image:
    """The exact 1-bit image that prints: just the sticker (no gap rows), optionally enlarged.

    Enlarging is nearest-neighbour so every printed dot stays a crisp square.
    """
    bitmap = to_bitmap(render(spec)).crop((0, 0, W, SH))
    if scale > 1:
        bitmap = bitmap.resize((W * scale, SH * scale), Image.Resampling.NEAREST)
    return bitmap


def to_bitmap(img: Image.Image) -> Image.Image:
    """The exact 1-bit image the printer will burn (also used for the GUI preview)."""
    return img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
