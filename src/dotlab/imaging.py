"""Turn a picture file into the grayscale (or already 1-bit) image that gets pasted on the label.

Order: load (transparency over white, EXIF rotation) -> fit -> tone (gamma, brightness, contrast) -> dither.
The default dither, Floyd-Steinberg, is left to `to_bitmap` (which dithers the whole label); the other modes (Atkinson, ordered, cutoff) produce
pure black/white here, which `to_bitmap` then passes through untouched.
"""
from __future__ import annotations

import functools
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageOps, UnidentifiedImageError

from .spec import SH, W, LabelSpec


def load_gray(path: str) -> Image.Image:
    """Open an image as 8-bit gray: upright per its EXIF orientation, transparent areas white (not black).

    Decoding is the slow part for a phone photo (about 70 ms of an 85 ms preview), and the preview re-renders on
    every slider step, so the result is cached per file (path, modification time and size, so an edited file is read
    again). The returned image is shared: never modify it in place.
    """
    stat = os.stat(path)  # raises FileNotFoundError for a missing file, exactly as opening it would
    return _decode(path, stat.st_mtime_ns, stat.st_size)


@functools.lru_cache(maxsize=2)  # two pictures at most: a 48 MP photo is about 48 MB once decoded
def _decode(path: str, mtime_ns: int, size: int) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(path))
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(flat, rgba)
    return img.convert("L")


def tone(img: Image.Image, gamma: float = 1.0, brightness: int = 0, contrast: int = 0) -> Image.Image:
    """gamma > 1 lightens the mid-tones; brightness and contrast are -100..100 (0 = unchanged)."""
    if gamma != 1.0:
        inverse = 1.0 / max(gamma, 0.01)
        img = img.point([round(255 * (v / 255) ** inverse) for v in range(256)])
    if brightness:
        img = ImageEnhance.Brightness(img).enhance(max(0.0, 1 + brightness / 100))
    if contrast:
        img = ImageEnhance.Contrast(img).enhance(max(0.0, 1 + contrast / 100))
    return img


def _bayer_matrix(n: int) -> list[list[int]]:
    m = [[0]]
    while len(m) < n:
        size = len(m)
        big = [[0] * (2 * size) for _ in range(2 * size)]
        for y in range(size):
            for x in range(size):
                v = 4 * m[y][x]
                big[y][x], big[y][x + size], big[y + size][x], big[y + size][x + size] = v, v + 2, v + 3, v + 1
        m = big
    return m


@functools.lru_cache(maxsize=8)
def _threshold_map(n: int, width: int, height: int) -> Image.Image:
    """An n x n Bayer matrix tiled over a width x height image, as per-pixel thresholds 0..254."""
    m = _bayer_matrix(n)
    cells = n * n
    levels = [[min(254, int((v + 0.5) * 255 / cells)) for v in row] for row in m]
    img = Image.new("L", (width, height))
    img.putdata([levels[y % n][x % n] for y in range(height) for x in range(width)])
    return img


def ordered_dither(img: Image.Image, n: int) -> Image.Image:
    """Ordered (Bayer) dithering: the regular crosshatch pattern of 90s handheld cameras and early games."""
    above = ImageChops.subtract(img, _threshold_map(n, *img.size))  # > 0 where the pixel beats its threshold
    return above.point(lambda v: 255 if v > 0 else 0)


@functools.lru_cache(maxsize=4)  # the preview re-renders on every slider step; this is the slow dither
def _atkinson(data: bytes, width: int, height: int) -> bytes:
    pad = 2  # room for the error that spills past the right edge, and a margin so no neighbour test is needed
    stride = width + 2 * pad
    work = [0] * (stride * (height + 2))
    for y in range(height):
        work[y * stride + pad:y * stride + pad + width] = data[y * width:(y + 1) * width]
    out = bytearray(width * height)
    for y in range(height):
        row = y * stride + pad
        for x in range(width):
            i = row + x
            old = work[i]
            new = 255 if old >= 128 else 0
            out[y * width + x] = new
            share = (old - new) // 8  # a quarter of the error is deliberately dropped: that is what makes it crisp
            if share:
                work[i + 1] += share
                work[i + 2] += share
                j = i + stride
                work[j - 1] += share
                work[j] += share
                work[j + 1] += share
                work[j + stride] += share
    return bytes(out)


def atkinson_dither(img: Image.Image) -> Image.Image:
    """Atkinson error diffusion (the original Macintosh's): only three quarters of each pixel's error is passed on, so
    highlights and shadows blow out to clean white and black and the mid-tones stay lively."""
    gray = img.convert("L")
    return Image.frombytes("L", gray.size, _atkinson(gray.tobytes(), *gray.size))


def _dither(img: Image.Image, spec: LabelSpec, *, final: bool) -> Image.Image:
    """Gray to dots per the spec. Floyd-Steinberg is left to `to_bitmap` unless the picture will be enlarged first."""
    if spec.threshold is not None:
        return img.point(lambda v: 255 if v >= spec.threshold else 0)
    if spec.dither == "atkinson":
        return atkinson_dither(img)
    if spec.dither == "bayer4":
        return ordered_dither(img, 4)
    if spec.dither == "bayer8":
        return ordered_dither(img, 8)
    return img if final else img.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")


def process(spec: LabelSpec, box: tuple[int, int] = (W, SH), cover: bool = False) -> Image.Image:
    """The picture for `spec`, fitted inside `box` (default: the whole sticker); `cover` fills the box and crops.

    With `pixelate` the tone and dither happen at the low resolution and the dots are then enlarged, so the pattern
    itself turns chunky (the look of 90s handheld cameras) instead of staying one dot wide inside each block.
    """
    gray = load_gray(spec.image_path)
    img = ImageOps.fit(gray, box) if cover else ImageOps.contain(gray, box)
    if spec.mirror:
        img = ImageOps.mirror(img)
    if spec.flip:
        img = ImageOps.flip(img)
    block = max(1, spec.pixelate)
    size = img.size
    if block > 1:
        img = img.resize((-(-size[0] // block), -(-size[1] // block)), Image.Resampling.BOX)
    img = tone(img, spec.gamma, spec.brightness, spec.contrast)
    if spec.invert:
        img = ImageOps.invert(img)
    img = _dither(img, spec, final=block == 1)
    if block > 1:
        img = img.resize((img.width * block, img.height * block), Image.Resampling.NEAREST).crop((0, 0, *size))
    return img


MAX_PICTURE_BYTES = 40 * 1024 * 1024  # a phone photo is a few MB; this keeps a mistake (a video, an archive) out
_FORMAT_SUFFIX = {"PNG": ".png", "JPEG": ".jpg", "BMP": ".bmp", "GIF": ".gif", "WEBP": ".webp"}


def pictures_dir() -> Path:
    return Path(tempfile.gettempdir()) / "dotlab" / "images"


def adopt(source, name: str = "") -> str:
    """Give a picture a client has received (an upload, a paste, a drop) a stable home and return its path, ready for
    `LabelSpec.image_path`. The file is checked to be a picture we can read, and stored under a name made from its
    content, so choosing the same picture twice is one file. Raises ValueError with a sentence to show the user."""
    source = Path(source)
    label = name or "That file"
    size = source.stat().st_size
    if size > MAX_PICTURE_BYTES:
        raise ValueError(f"{label} is {size / 1e6:.0f} MB; pictures up to {MAX_PICTURE_BYTES // 2**20} MB are accepted.")
    try:
        with Image.open(source) as img:
            kind = img.format
            img.verify()  # a cheap integrity check that doesn't decode every pixel
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise ValueError(f"{label} isn't a picture I can read (PNG, JPEG, BMP, GIF or WebP).") from e
    suffix = _FORMAT_SUFFIX.get(kind)
    if suffix is None:
        raise ValueError(f"{label} is a {kind} picture; use PNG, JPEG, BMP, GIF or WebP.")
    data = source.read_bytes()
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).stem).strip(" .")[:40]  # the name the user knows it by
    target = pictures_dir() / (f"{hashlib.sha256(data).hexdigest()[:16]}{'-' + stem if stem else ''}{suffix}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(target)  # never a half-written picture under its final name
    return str(target)
