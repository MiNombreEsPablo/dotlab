"""Fonts shipped with the app, so labels print the same on any machine (and so nothing depends on system fonts or
fontconfig, which Windows and macOS lack).

All are SIL OFL (DejaVu: its own free licence) (licence texts in fonts/LICENSES). Latin-only display fonts borrow Japanese glyphs from
FALLBACK_JA at render time, and the `ja` ones cover Japanese themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FONT_DIR = Path(__file__).with_name("fonts")


@dataclass(frozen=True)
class BundledFont:
    family: str
    category: str
    files: dict[str, str]  # "regular" | "bold" | "italic" | "bolditalic" -> file in FONT_DIR
    ja: bool = False  # covers kana and kanji itself
    note: str = ""
    license: str = ""  # file in FONT_DIR/LICENSES; default LICENSE.<family slug>

    @property
    def license_file(self) -> str:
        return self.license or f"LICENSE.{self.family.lower().replace(' ', '-')}"

    def pick(self, bold: bool, italic: bool) -> tuple[str, bool]:
        """(path, has_native_slant), degrading gracefully when a style isn't shipped."""
        chain = {
            (True, True): ("bolditalic", "bold", "italic", "regular"),
            (True, False): ("bold", "regular"),
            (False, True): ("italic", "regular"),
            (False, False): ("regular",),
        }[(bold, italic)]
        key = next(k for k in chain if k in self.files)
        return str(FONT_DIR / self.files[key]), "italic" in key


CYBER, PIXEL, WEB, DISPLAY, CLEAN = "Cyber / sci-fi", "Pixel / arcade", "Early web", "Display", "Clean"

BUNDLED = (
    BundledFont("Orbitron", CYBER, {"regular": "Orbitron[wght].ttf"}, note="variable weight"),
    BundledFont("Audiowide", CYBER, {"regular": "Audiowide-Regular.ttf"}),
    BundledFont("Oxanium", CYBER, {"regular": "Oxanium[wght].ttf"}, note="variable weight"),
    BundledFont("Share Tech Mono", CYBER, {"regular": "ShareTechMono-Regular.ttf"}),
    BundledFont("Rajdhani", CYBER, {"regular": "Rajdhani-Regular.ttf", "bold": "Rajdhani-Bold.ttf"}),
    BundledFont("Press Start 2P", PIXEL, {"regular": "PressStart2P-Regular.ttf"}),
    BundledFont("VT323", PIXEL, {"regular": "VT323-Regular.ttf"}),
    BundledFont("Silkscreen", PIXEL, {"regular": "Silkscreen-Regular.ttf", "bold": "Silkscreen-Bold.ttf"}),
    BundledFont("Pixelify Sans", PIXEL, {"regular": "PixelifySans[wght].ttf"}, note="variable weight"),
    BundledFont("DotGothic16", PIXEL, {"regular": "DotGothic16-Regular.ttf"}, ja=True),
    BundledFont(
        "Comic Neue", WEB,
        {"regular": "ComicNeue-Regular.ttf", "bold": "ComicNeue-Bold.ttf",
         "italic": "ComicNeue-Italic.ttf", "bolditalic": "ComicNeue-BoldItalic.ttf"},
    ),
    BundledFont("Bangers", WEB, {"regular": "Bangers-Regular.ttf"}),
    BundledFont("Righteous", WEB, {"regular": "Righteous-Regular.ttf"}),
    BundledFont("Yusei Magic", WEB, {"regular": "YuseiMagic-Regular.ttf"}, ja=True, note="marker"),
    BundledFont("Bungee", DISPLAY, {"regular": "Bungee-Regular.ttf"}),
    BundledFont("Black Ops One", DISPLAY, {"regular": "BlackOpsOne-Regular.ttf"}),
    BundledFont("Monoton", DISPLAY, {"regular": "Monoton-Regular.ttf"}),
    BundledFont("Major Mono Display", DISPLAY, {"regular": "MajorMonoDisplay-Regular.ttf"}),
    BundledFont("Dela Gothic One", DISPLAY, {"regular": "DelaGothicOne-Regular.ttf"}, ja=True),
    BundledFont("Stick", DISPLAY, {"regular": "Stick-Regular.ttf"}, ja=True),
    BundledFont(
        "DejaVu Sans", CLEAN,
        {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf",
         "italic": "DejaVuSans-Oblique.ttf", "bolditalic": "DejaVuSans-BoldOblique.ttf"},
        license="LICENSE.dejavu",
    ),
    BundledFont(
        "DejaVu Sans Mono", CLEAN, {"regular": "DejaVuSansMono.ttf", "bold": "DejaVuSansMono-Bold.ttf"},
        license="LICENSE.dejavu",
    ),
    BundledFont(
        "Zen Kaku Gothic New", CLEAN,
        {"regular": "ZenKakuGothicNew-Regular.ttf", "bold": "ZenKakuGothicNew-Bold.ttf"}, ja=True,
    ),
)

FALLBACK_JA = next(f for f in BUNDLED if f.family == "Zen Kaku Gothic New")
_BY_FAMILY = {f.family.casefold(): f for f in BUNDLED}


def bundled_font(family: str) -> BundledFont | None:
    return _BY_FAMILY.get(family.casefold())


def categories() -> list[tuple[str, list[str]]]:
    """[(category, [family, ...])] in display order, for the GUI picker."""
    order = (CYBER, PIXEL, WEB, DISPLAY, CLEAN)
    return [(cat, [f.family for f in BUNDLED if f.category == cat]) for cat in order]
