"""Rasterise src/t003gui/assets/icon.svg into the PNG/ICO/ICNS files the packages need.

    .venv/bin/python packaging/make_icons.py

Needs PySide6 (QtSvg). Outputs are committed, so this only runs when the SVG changes.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "src/t003gui/assets/icon.svg"
OUT = ROOT / "packaging/icons"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


def render(size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    QSvgRenderer(str(SVG)).render(painter)
    painter.end()
    return Image.frombuffer("RGBA", (size, size), bytes(image.constBits()), "raw", "BGRA", 0, 1)


def mark() -> None:
    """The icon without its blue orb, for the banner (it would vanish into the blue plate)."""
    lines = SVG.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "glossy orb" in line)
    svg = "\n".join(lines[:start] + lines[start + 5 :])  # comment, shadow, orb, gloss and the blank line after
    svg = svg.replace('viewBox="0 0 512 512"', 'viewBox="100 90 340 340"')
    image = QImage(256, 256, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    image.save(str(ROOT / "src/t003gui/assets/icon-mark.png"))


def main() -> None:
    QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    images = {size: render(size) for size in SIZES}
    for size, img in images.items():
        img.save(OUT / f"t003-label-gui-{size}.png")
    images[256].save(ROOT / "src/t003gui/assets/icon-256.png")  # used at runtime (no SVG plugin needed)
    images[256].save(OUT / "t003-label-gui.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    images[512].save(OUT / "t003-label-gui.icns")
    mark()
    print("wrote", len(SIZES), "PNGs, .ico, .icns")


if __name__ == "__main__":
    main()
