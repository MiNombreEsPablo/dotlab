"""The label's controls, described as data, so every client builds them from one description.

A client (the web UI today) renders `describe()` instead of repeating the lists of fonts, effects, backgrounds, ranges
and labels. Adding a choice in `spec.py` therefore shows up everywhere; adding a new `LabelSpec` field fails
tests/test_form.py until it is described here (or listed in `PENDING`, the controls still to be built by hand).

Not described here: the printer. The picture chooser and the doodle are fields of kind "image" and "doodle": the
schema places them, the client draws them (the doodle's tools are described by `doodle.describe()`).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import fonts, spec

LABELS = {  # how a choice is worded when `value.capitalize()` isn't enough
    "3d": "3D WordArt", "grid": "Graph paper", "dots": "Polka dots", "bevel": "Win95 bevel",
    "hexgrid": "Hex grid", "matrix": "Matrix rain", "circuit": "Circuit board", "chamfer": "Cyber panel",
    "brackets": "HUD brackets", "ticks": "Ruler ticks", "neon": "Neon glow",
    "floyd": "Floyd–Steinberg (smooth)", "bayer4": "Ordered 4×4 (crosshatch)", "bayer8": "Ordered 8×8 (finer)",
    "threshold": "Hard cutoff (flat art)",
    "only": "Image only", "left": "Left of text", "right": "Right of text",
    "top": "Above text", "bottom": "Below text", "behind": "Behind text",
}

OUTPUT = "output"  # not a tab: shown next to the Print button, whatever tab is open

# LabelSpec fields without a control in the schema yet. 
PENDING = frozenset()  # (the doodle was the last one)


@dataclass(frozen=True)
class Tab:
    id: str
    label: str
    needs: str = ""  # a LabelSpec field that must be set for the tab's controls to apply (dimmed until then)
    needs_hint: str = ""  # what to say while it is dimmed
    reset: tuple = ()  # field names a "Reset" button on the tab puts back to their defaults

    def describe(self) -> dict:
        return {"id": self.id, "label": self.label, "needs": self.needs, "needs_hint": self.needs_hint,
                "reset": list(self.reset)}


@dataclass(frozen=True)
class Field:
    name: str  # the LabelSpec field it sets
    kind: str  # "text" | "textarea" | "choice" | "toggle" | "number" | "slider" | "image" | "doodle"
    label: str
    tab: str  # a tab id, or OUTPUT
    row: str = ""  # fields with the same row title sit side by side under it (Bold and Italic: "Style")
    choices: tuple = ()  # choice: ((value, label, group), ...); group is "" when there are none
    none_label: str = ""  # choice: a leading item meaning "off", which turns `toggle` off
    toggle: str = ""  # the bool LabelSpec field that is on whenever a real choice is picked (border / border_style)
    gate: str = ""  # choice: picking this value sends the field of that name (a slider) instead of the choice itself
    minimum: float = 0
    maximum: float = 0
    step: float = 1
    scale: str = "linear"  # slider: "log" spreads a range like 0.3-3 evenly around `neutral`
    neutral: float = 0
    default: float | None = None  # slider: its start value when the spec's own default is None (threshold)
    suffix: str = ""  # shown after a number: "%", " dots"
    zero_label: str = ""  # number/slider: what 0 means, shown when the box is empty ("Auto (fit)", "Off")
    show_when: tuple = ()  # (field name, (values...)): only shown while that choice has one of those values
    enable_when: tuple = ()  # the same, but the control is only disabled otherwise
    tip: str = ""

    def describe(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "label": self.label, "tab": self.tab, "row": self.row,
            "choices": [list(c) for c in self.choices], "none_label": self.none_label, "toggle": self.toggle,
            "gate": self.gate, "minimum": self.minimum, "maximum": self.maximum, "step": self.step,
            "scale": self.scale, "neutral": self.neutral, "default": self.default, "suffix": self.suffix,
            "zero_label": self.zero_label, "show_when": [self.show_when[0], list(self.show_when[1])] if self.show_when else [],
            "enable_when": [self.enable_when[0], list(self.enable_when[1])] if self.enable_when else [], "tip": self.tip,
        }


def _choices(values) -> tuple:
    return tuple((v, LABELS.get(v, v.capitalize()), "") for v in values)


def _font_choices() -> tuple:
    return tuple((family, family, category) for category, families in fonts.categories() for family in families)


_SIDE_LAYOUTS = ("left", "right", "top", "bottom")  # the layouts in which the picture has a size
_IMAGE_FIELDS = (
    "image_layout", "image_size", "dither", "threshold", "brightness", "contrast", "gamma", "pixelate", "mirror",
    "flip", "invert",
)

TABS = (
    Tab("content", "Content"),
    Tab("text", "Text"),
    Tab("image", "Image", needs="image_path", needs_hint="Choose an image first (Content tab).", reset=_IMAGE_FIELDS),
    Tab("decoration", "Decoration"),
    Tab("doodle", "Doodle"),
)

FIELDS = (
    Field("text", "textarea", "Text", "content"),
    Field("qr", "text", "QR", "content", tip="Anything a phone can scan: a link, a Wi-Fi code, some words"),
    Field("image_path", "image", "Image", "content",
          tip="With the default layout the picture replaces the text and QR code;\nchoose another layout on the Image tab to combine them"),
    Field("font", "choice", "Font", "text", choices=_font_choices()),
    Field("bold", "toggle", "Bold", "text", row="Style"),
    Field("italic", "toggle", "Italic", "text", row="Style"),
    Field("size", "number", "Size", "text", minimum=0, maximum=120, zero_label="Auto (fit)",
          tip="Largest text size in dots; Auto picks the biggest that fits"),
    Field("align", "choice", "Align", "text", choices=_choices(spec.ALIGNMENTS)),
    Field("valign", "choice", "Vertical", "text", choices=_choices(spec.VALIGNMENTS)),
    Field("effect", "choice", "Effect", "text", choices=_choices(spec.EFFECTS)),
    Field("image_layout", "choice", "Layout", "image", row="Layout", choices=_choices(spec.IMAGE_LAYOUTS),
          tip="How the picture shares the label with the text and QR code.\n'Image only' prints just the picture and ignores the text."),
    Field("image_size", "number", "Picture size", "image", row="Layout", minimum=20, maximum=80, suffix="%",
          enable_when=("image_layout", _SIDE_LAYOUTS), tip="The picture's share of the label"),
    Field("dither", "choice", "Dither", "image", choices=_choices(spec.DITHERS + ("threshold",)), gate="threshold",
          tip="Floyd–Steinberg is smooth and best for photos; ordered dithering gives the regular\n"
              "crosshatch of 90s handheld cameras; a hard cutoff suits flat-colour art."),
    Field("threshold", "slider", "Cutoff", "image", minimum=0, maximum=255, default=160,
          show_when=("dither", ("threshold",)), tip="Pixels lighter than this print white, darker print black"),
    Field("brightness", "slider", "Brightness", "image", minimum=-100, maximum=100,
          tip="Drag, type a number, or double-click the slider to reset it"),
    Field("contrast", "slider", "Contrast", "image", minimum=-100, maximum=100,
          tip="Drag, type a number, or double-click the slider to reset it"),
    Field("gamma", "slider", "Gamma", "image", minimum=0.3, maximum=3.0, step=0.1, scale="log", neutral=1.0,
          tip="Above 1.0 lightens the mid-tones, below 1.0 darkens them. Double-click to reset."),
    Field("pixelate", "slider", "Pixelate", "image", minimum=0, maximum=32, zero_label="Off", suffix=" dots",
          tip="Chunky blocks, dithered at the low resolution: 3 gives the look of a 90s handheld camera"),
    Field("mirror", "toggle", "Mirror", "image", row="Options"),
    Field("flip", "toggle", "Flip", "image", row="Options"),
    Field("invert", "toggle", "Invert", "image", row="Options"),
    Field("border_style", "choice", "Border", "decoration", choices=_choices(spec.BORDER_STYLES), none_label="None",
          toggle="border"),
    Field("background", "choice", "Background", "decoration", choices=_choices(spec.BACKGROUNDS)),
    Field("bars", "toggle", "Under-construction bars", "decoration"),
    Field("doodle", "doodle", "Doodle", "doodle"),  # the drawing tools are the client's own; the schema places the tab
    Field("copies", "number", "Copies", OUTPUT, minimum=1, maximum=99),
    Field("density", "number", "Darkness", OUTPUT, minimum=0, maximum=15),
)


def covered() -> set[str]:
    """The LabelSpec fields the schema sets (a toggle's bool, and the field a gate sends, count as set)."""
    return {f.name for f in FIELDS} | {f.toggle for f in FIELDS if f.toggle} | {f.gate for f in FIELDS if f.gate}


def describe() -> dict:
    return {"tabs": [t.describe() for t in TABS], "fields": [f.describe() for f in FIELDS]}
