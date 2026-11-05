"""Command-line printing: print-label "text" --qr URL --image FILE ..."""
from __future__ import annotations

import argparse
import sys

from . import __version__, composition, core
from .spec import has_content
from .presets import PresetStore

EXAMPLES = r"""
examples:
  print-label "Hello"                          auto-fit text
  print-label "Line 1\nLine 2" --border        multiple lines
  print-label "Left" --align left --font "Noto Sans Mono" --no-bold
  print-label "WELCOME!" --effect 3d --frame marquee          early-web style
  print-label "Under\nConstruction" --bars --effect outline
  print-label "Hi" --background stars --effect shadow --italic
  print-label "Wi-Fi" --qr "WIFI:S:x;;"        text left, QR right
  print-label --image art.png --threshold 160  hard cutoff, good for flat colours
  print-label --image photo.jpg --dither bayer4 --contrast 20   crosshatch dither, a bit more punch
  print-label "Mug" --image mug.png --layout left      photo with a caption
  print-label --image photo.jpg --pixelate 3 --dither bayer4    chunky handheld-camera look
  print-label --preset shelf --copies 3        saved GUI preset
  print-label "x" --preview out.png            render to PNG, don't print
"""


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="print-label",
        description="Print to the ORGBRO T003 label printer (384x224 dots).",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"t003-label-gui {__version__}")
    p.add_argument("text", nargs="?", help=r"text to print (use \n for newlines)")
    p.add_argument("--qr", help="QR code content")
    p.add_argument("--image", help="image file to print")
    p.add_argument("--threshold", type=int, help="image: hard black/white cutoff 0-255 instead of dithering")
    p.add_argument("--layout", dest="image_layout", choices=core.IMAGE_LAYOUTS,
                   help="image with text/QR: only (default, image replaces them), left, right, top, bottom, behind")
    p.add_argument("--image-size", type=int, help="image: its share of the label for left/right/top/bottom, 20-80 (default 40)")
    p.add_argument("--dither", choices=core.DITHERS, help="image: how gray becomes dots (default floyd)")
    p.add_argument("--brightness", type=int, help="image: -100..100")
    p.add_argument("--contrast", type=int, help="image: -100..100")
    p.add_argument("--gamma", type=float, help="image: above 1 lightens the mid-tones (default 1.0)")
    p.add_argument("--pixelate", type=int, help="image: chunky blocks of this many dots (3 = handheld-camera look)")
    p.add_argument("--mirror", action="store_true", help="image: flip left-right")
    p.add_argument("--flip", action="store_true", help="image: flip top-bottom")
    p.add_argument("--invert", action="store_true", help="image: negative")
    p.add_argument("--font", help="font family, e.g. 'Noto Sans Mono' (default DejaVu Sans)")
    p.add_argument("--bold", action=argparse.BooleanOptionalAction, default=None, help="bold text (default on)")
    p.add_argument("--align", choices=core.ALIGNMENTS, help="text alignment (default center)")
    p.add_argument("--italic", action=argparse.BooleanOptionalAction, default=None, help="italic text")
    p.add_argument("--size", type=int, help="largest text size in dots (default: auto-fit)")
    p.add_argument("--valign", choices=core.VALIGNMENTS, help="vertical alignment (default middle)")
    p.add_argument("--effect", choices=core.EFFECTS, help="text effect: dithered shadow, outline or 3D WordArt")
    p.add_argument("--background", choices=core.BACKGROUNDS, help="background pattern")
    p.add_argument("--border", action="store_true", help="draw a plain border")
    p.add_argument("--frame", choices=core.BORDER_STYLES, help="border style (implies a border)")
    p.add_argument("--bars", action="store_true", help="under-construction hazard bars top and bottom")
    p.add_argument("--copies", type=int, help="number of copies (default 1)")
    p.add_argument("--density", type=int, help="darkness 0-15 (default 7)")
    p.add_argument("--preset", help="start from a preset saved in the GUI; other flags override it")
    p.add_argument("--file", metavar="FILE", help="start from a label file saved by the web UI (a PNG with the design inside); other flags override it")
    p.add_argument("--address", default="auto", metavar="ADDRESS",
                   help="Bluetooth address of the printer (default: the first T003 the system knows)")
    p.add_argument("--preview", metavar="PNG", help="write the rendered label to PNG instead of printing")
    args = p.parse_args(argv)

    spec = core.LabelSpec()
    if args.file and args.preset:
        p.error("use either --file or --preset, not both")
    if args.file:
        try:
            spec = composition.load(args.file)
        except (OSError, ValueError) as e:
            p.error(f"can't open {args.file}: {e}")
    if args.preset:
        spec = PresetStore().get(args.preset)
        if spec is None:
            p.error(f"no preset named {args.preset!r}")
    for field in ("text", "qr", "threshold", "image_layout", "image_size", "dither", "brightness", "contrast", "gamma", "pixelate", "copies",
                  "density", "font", "bold", "italic", "size", "align", "valign", "effect", "background"):
        if getattr(args, field) is not None:
            setattr(spec, field, getattr(args, field))
    if args.image:
        spec.image_path = args.image
    if args.border or args.frame:
        spec.border = True
    if args.frame:
        spec.border_style = args.frame
    if args.bars:
        spec.bars = True
    for flag in ("mirror", "flip", "invert"):
        if getattr(args, flag):
            setattr(spec, flag, True)
    if not has_content(spec):
        p.error("give some text, --qr, --image, --preset or --file")

    try:
        if args.preview:
            core.to_bitmap(core.render(spec)).save(args.preview)
            return
        for problem in core.print_label(spec, args.address):
            print(f"printer: {problem}", file=sys.stderr)
    except (core.PrinterError, OSError, ValueError) as e:  # ValueError: e.g. a QR code too big to encode
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
