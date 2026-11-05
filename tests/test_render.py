import itertools

import pytest
from PIL import Image

from dotlab import core


def _inked(img):
    return img.point(lambda v: 255 - v).getbbox()


@pytest.mark.parametrize("effect", core.EFFECTS)
@pytest.mark.parametrize("background", core.BACKGROUNDS)
def test_effects_and_backgrounds_stay_in_sticker(effect, background):
    img = core.render(core.LabelSpec(text="Hi\nthere", effect=effect, background=background, qr="x"))
    assert img.size == (core.W, core.H)
    assert img.crop((0, core.SH, core.W, core.H)).getextrema() == (255, 255)


@pytest.mark.parametrize("style", core.BORDER_STYLES)
@pytest.mark.parametrize("bars", [False, True])
def test_borders_and_bars_stay_in_sticker_and_leave_room(style, bars):
    spec = core.LabelSpec(text="Hello", border=True, border_style=style, bars=bars)
    img = core.render(spec)
    assert img.crop((0, core.SH, core.W, core.H)).getextrema() == (255, 255)
    assert _inked(img) is not None


def test_size_caps_text_and_auto_fills():
    small = core.render(core.LabelSpec(text="Hi", size=20))
    auto = core.render(core.LabelSpec(text="Hi"))
    assert _inked(small)[3] - _inked(small)[1] < _inked(auto)[3] - _inked(auto)[1]
    # a cap larger than what fits can't overflow the label
    huge = core.render(core.LabelSpec(text="Hi there friend", size=120))
    left, top, right, bottom = _inked(huge)
    assert left >= 0 and right <= core.W and bottom <= core.SH


def test_valign_positions():
    top = _inked(core.render(core.LabelSpec(text="Hi", size=40, valign="top")))
    mid = _inked(core.render(core.LabelSpec(text="Hi", size=40, valign="middle")))
    bot = _inked(core.render(core.LabelSpec(text="Hi", size=40, valign="bottom")))
    assert top[1] < mid[1] < bot[1]
    assert top[1] <= core.MARGIN + 2
    assert bot[3] >= core.SH - core.MARGIN - 2


def test_italic_changes_output_and_stays_within_width():
    plain = core.render(core.LabelSpec(text="Hello there", font="DejaVu Sans Mono", italic=False))
    slanted = core.render(core.LabelSpec(text="Hello there", font="DejaVu Sans Mono", italic=True))
    assert plain.tobytes() != slanted.tobytes()
    assert _inked(slanted)[2] <= core.W - core.MARGIN + 1


def test_effects_differ_from_plain():
    plain = core.render(core.LabelSpec(text="Hi")).tobytes()
    for effect in core.EFFECTS[1:]:
        assert core.render(core.LabelSpec(text="Hi", effect=effect)).tobytes() != plain


def test_invalid_choices_fall_back():
    core.render(core.LabelSpec(text="x", effect="sparkle", background="lava", border=True, border_style="wavy",
                               valign="sideways"))


def test_all_combos_render_quickly():
    import time
    start = time.time()
    for effect, bg in itertools.product(("none", "3d"), ("none", "gradient")):
        core.render(core.LabelSpec(text="WELCOME TO MY\nHOMEPAGE", effect=effect, background=bg, italic=True))
    assert time.time() - start < 5


def _line_tops(mask):
    rows = [y for y in range(mask.height) if mask.crop((0, y, mask.width, y + 1)).getbbox()]
    return [rows[0]] + [b for a, b in zip(rows, rows[1:]) if b - a > 1]


def test_stroked_effects_stay_registered_on_every_line():
    # outline/3d/neon draw a thickened copy and a plain copy; if their line pitch differs the effect only looks
    # right on line one (Pillow's multiline_text adds 2*stroke_width per line)
    from dotlab import render

    fs = render._FontSet(render.font_path("DejaVu Sans", True)[0], 40, True)
    probe = render.ImageDraw.Draw(Image.new("L", (1, 1)))
    placed, _, _, _ = render._layout(probe, "AAA\nAAA\nAAA", fs, "left", 8)
    pitches = [b[3] - a[3] for a, b in zip(placed, placed[1:])]
    assert len(set(pitches)) == 1 and pitches[0] > 0

    def tops(stroke):
        m = Image.new("L", (400, 300), 0)
        d = render.ImageDraw.Draw(m)
        for run, font, x, y, _ in placed:
            d.text((20 + x, 20 + y), run, font=font, fill=255, anchor="ls", stroke_width=stroke, stroke_fill=255)
        return _line_tops(m)

    plain, thick = tops(0), tops(7)
    # a thickened copy grows by the same amount around every line, so tops shift by a constant
    assert len({p - t for p, t in zip(plain, thick)}) == 1


def test_bold_applies_to_variable_fonts():
    # variable fonts load at their default weight; bold must set the weight axis itself
    path, _ = core.font_path("Orbitron", True)
    if "[" not in path:
        pytest.skip("no variable font installed to test with")
    bold = core.render(core.LabelSpec(text="HELLO", font="Orbitron", bold=True, size=60))
    light = core.render(core.LabelSpec(text="HELLO", font="Orbitron", bold=False, size=60))
    ink = lambda im: sum(255 - v for v in im.get_flattened_data()) if hasattr(im, "get_flattened_data") else sum(255 - v for v in im.getdata())
    assert ink(bold) > ink(light) * 1.2


def test_font_family_list_matches_fontconfig_names():
    families = core.list_font_families()
    if not families:
        pytest.skip("fontconfig not available")
    assert families == sorted(set(families), key=str.casefold)  # unique, sorted
    assert all(f and "[" not in f and not f.startswith(".") for f in families)  # no foundry tags, no hidden fonts


@pytest.mark.parametrize("effect", core.EFFECTS)
@pytest.mark.parametrize("italic", [False, True])
def test_text_is_pure_black_and_white_before_dithering(effect, italic):
    """Anti-aliased gray edges would be turned into scattered dots by the label-wide Floyd-Steinberg pass (ragged,
    speckled letters). Text layers are binarised, so a text-only label never has gray left to dither."""
    canvas = core.render(core.LabelSpec(text="Glossy\nOrb", font="Righteous", effect=effect, italic=italic))
    assert set(canvas.tobytes()) <= {0, 255}


def test_text_binarisation_keeps_the_ink():
    """Thresholding at 50 % coverage must not thin the text out (it keeps about 97 % of the dithered ink)."""
    spec = core.LabelSpec(text="Shelf 3 Resistors", font="DejaVu Sans", bold=True, size=24)
    ink = core.to_bitmap(core.render(spec)).convert("L").tobytes().count(0)
    assert ink > 1500


def test_unprintable_content_gives_a_readable_error(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    for spec, text in (
        (core.LabelSpec(qr="x" * 5000), "too long"),
        (core.LabelSpec(image_path=str(tmp_path / "gone.png")), "missing"),
        (core.LabelSpec(image_path=str(bad)), "isn't a picture file"),
    ):
        with pytest.raises(core.PrinterError, match=text):
            core.render(spec)
