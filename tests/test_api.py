import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import ImageFont

from t003gui import api, core, fonts, protocol, render, spec

ROOT = Path(__file__).resolve().parent.parent


def test_label_from_json_accepts_text_dict_and_bytes():
    assert api.label_from_json('{"text": "hi", "bold": false}').text == "hi"
    assert api.label_from_json({"text": "hi"}).bold is True
    assert api.label_from_json(b'{"effect": "neon"}').effect == "neon"


def test_label_from_json_ignores_unknown_keys_and_bad_types():
    label = api.label_from_json({"text": "hi", "nonsense": 1, "copies": "many", "size": True})
    assert (label.text, label.copies, label.size) == ("hi", 1, 0)


@pytest.mark.parametrize("raw", ["[1, 2]", "3", '"text"', "null"])
def test_label_from_json_rejects_non_objects(raw):
    with pytest.raises(ValueError):
        api.label_from_json(raw)


def test_label_from_json_rejects_broken_json():
    with pytest.raises(ValueError):  # json.JSONDecodeError is a ValueError
        api.label_from_json("{not json")


def test_preview_pixels_is_the_printed_bitmap():
    pixels = api.preview_pixels({"text": "Hello", "border": True})
    assert len(pixels) == core.W * core.H
    assert set(pixels) <= {0, 255}
    assert 0 in pixels
    gap = pixels[core.W * core.SH:]
    assert set(gap) == {255}  # the rows below the sticker are never inked


def test_tspl_bytes_matches_the_core_payload():
    spec = core.LabelSpec(text="x", copies=2, density=5)
    assert api.tspl_bytes({"text": "x", "copies": 2, "density": 5}) == core.tspl(spec)
    assert core.tspl is protocol.tspl  # core re-exports it, one implementation


def test_status_problems_names_the_flags():
    assert protocol.status_problems(0) == []
    assert protocol.status_problems(0x01 | 0x04) == ["head open", "out of paper"]
    assert core.STATUS_FLAGS is protocol.STATUS_FLAGS


def test_options_lists_every_choice_and_font():
    opts = json.loads(api.options())
    assert opts["geometry"] == {"width": core.W, "height": core.H, "sticker_height": core.SH, "margin": core.MARGIN}
    assert opts["effects"] == list(core.EFFECTS) and opts["backgrounds"] == list(core.BACKGROUNDS)
    assert [f["family"] for f in opts["fonts"]] == [f.family for f in fonts.BUNDLED]
    assert opts["defaults"]["text"] == "" and opts["defaults"]["font"] == opts["default_font"]
    assert "star" in opts["stickers"]


def test_fonts_needed_names_files_in_the_bundled_folder():
    needed = api.fonts_needed({"font": "Orbitron", "bold": True})
    assert "Orbitron[wght].ttf" in needed
    assert "ZenKakuGothicNew-Bold.ttf" in needed  # the Japanese fallback
    assert "DejaVuSans-Bold.ttf" in needed  # the last resort
    assert len(needed) == len(set(needed))
    assert all((fonts.FONT_DIR / name).is_file() for name in needed)


def test_fonts_needed_for_an_unknown_font_falls_back_to_dejavu(monkeypatch):
    monkeypatch.setattr(render, "HAS_FONTCONFIG", False)  # as in the web build; with fontconfig a system font is used
    assert "DejaVuSans.ttf" in api.fonts_needed({"font": "No Such Font", "bold": False})


def test_fonts_needed_leaves_out_system_fonts(monkeypatch):
    monkeypatch.setattr(render, "font_path", lambda family, bold, italic=False: ("/usr/share/fonts/x.ttf", False))
    assert "x.ttf" not in api.fonts_needed({"font": "Whatever"})


def test_text_layout_is_pinned_to_basic():
    """Raqm kerns differently and draws some fonts heavier, so the same label would differ per machine's Pillow."""
    path, _ = render.font_path("DejaVu Sans", False)
    assert render._font(path, 24).layout_engine == ImageFont.Layout.BASIC


def test_api_and_protocol_import_without_usb():
    code = (
        "import sys; sys.modules['usb'] = None; sys.modules['libusb_package'] = None\n"
        "from t003gui import api, protocol\n"
        "assert api.tspl_bytes({'text': 'x'}).startswith(b'SIZE ')\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr


def test_fonts_needed_covers_every_font_a_render_opens(monkeypatch):
    """A client that loads fonts on demand (the web build) gets exactly `fonts_needed`; a font opened that is not on
    the list would silently fall back to another face there. Record what rendering really opens, for every effect,
    background, border, font and weight."""
    from pathlib import PurePath

    opened = []
    real = ImageFont.truetype
    monkeypatch.setattr(render.ImageFont, "truetype", lambda path, *a, **k: opened.append(path) or real(path, *a, **k))
    cases = [{"text": "Hi 日本語", "effect": e} for e in core.EFFECTS]
    cases += [{"text": "BG", "background": b} for b in core.BACKGROUNDS]
    cases += [{"text": "Box", "border": True, "border_style": s} for s in core.BORDER_STYLES]
    cases += [{"text": "Hello 日本語", "font": f.family, "bold": bold, "italic": italic}
              for f in fonts.BUNDLED for bold in (False, True) for italic in (False, True)]
    for raw in cases:
        opened.clear()
        api.preview_pixels(raw)
        needed = set(api.fonts_needed(raw))
        extra = {PurePath(p).name for p in opened if PurePath(p).parent == PurePath(fonts.FONT_DIR)} - needed
        assert not extra, (raw, extra)


def test_the_matrix_background_asks_for_its_mono_font():
    assert "DejaVuSansMono.ttf" in api.fonts_needed({"background": "matrix"})
    assert "DejaVuSansMono.ttf" not in api.fonts_needed({"background": "dots"})


def test_adopt_image_gives_back_a_path_for_the_label(tmp_path):
    from PIL import Image

    source = tmp_path / "in.png"
    Image.new("RGB", (20, 20), (0, 0, 0)).save(source)
    path = api.adopt_image(str(source), "in.png")
    assert api.hints({"text": "hi", "image_path": path})  # "Image only" hides the text: the hint now has a real picture
    assert 0 in api.preview_pixels({"image_path": path})


# --- exporting the label as an image ---------------------------------------------------------------------------------

def test_export_png_is_the_printed_sticker_at_the_chosen_size():
    import io

    from PIL import Image, ImageChops

    raw = {"text": "Hi", "border": True}
    for scale in spec.EXPORT_SCALES:
        image = Image.open(io.BytesIO(api.export_png(raw, scale)))
        assert image.format == "PNG" and image.size == (core.W * scale, core.SH * scale)
        assert ImageChops.difference(image.convert("L"), core.label_bitmap(core.LabelSpec(text="Hi", border=True), scale).convert("L")).getbbox() is None


def test_export_sizes_are_the_engines_and_other_sizes_snap_to_the_nearest():
    import io

    from PIL import Image

    sizes = json.loads(api.options())["export"]
    assert [s for s, _ in sizes["scales"]] == list(spec.EXPORT_SCALES) and sizes["extension"] == ".png"
    assert all(f"{core.W * s}×{core.SH * s}" in label for s, label in sizes["scales"])
    assert Image.open(io.BytesIO(api.export_png({"text": "x"}, 3))).width == core.W * 4  # 3 is closer to 4 than to 1
    assert Image.open(io.BytesIO(api.export_png({"text": "x"}, 0))).width == core.W
    assert Image.open(io.BytesIO(api.export_png({"text": "x"}, 99))).width == core.W * 4


def test_files_are_named_after_the_label():
    assert api.file_stem({"text": "  Neon Nights!\nsecond line"}) == "Neon Nights"
    assert api.file_stem({"text": ""}) == "label" and api.file_stem({"text": "***"}) == "label"
    assert len(api.file_stem({"text": "x" * 100})) == 40


# --- label files through the engine ------------------------------------------------------------------------------------

def test_a_label_file_round_trips_through_the_api(tmp_path):
    from PIL import Image

    picture = tmp_path / "p.png"
    Image.new("RGB", (40, 30), (200, 30, 30)).save(picture)
    original = {"text": "Hi", "border": True, "border_style": "bevel", "image_path": api.adopt_image(str(picture), "p.png"),
                "image_layout": "left", "dither": "bayer4", "copies": 3}
    text = api.composition_dumps(original)
    assert json.loads(text)["spec"]["image_path"] == "" and "image" in json.loads(text)  # the picture travels inside
    back = json.loads(api.composition_loads(text))
    assert back["text"] == "Hi" and back["border_style"] == "bevel" and back["copies"] == 3
    assert back["image_layout"] == "left" and back["dither"] == "bayer4"
    assert back["image_path"] and Path(back["image_path"]).read_bytes() == picture.read_bytes()
    assert api.preview_pixels(back) == api.preview_pixels(original)  # the same label


@pytest.mark.parametrize("text, expected", [
    ("{broken", "not a label file"),
    ('{"format": "something else", "spec": {}}', "not a T003 label file"),
    ('{"format": "t003-label", "version": 99, "spec": {}}', "newer version"),
    ('{"format": "t003-label", "version": 1, "spec": {}, "image": {"data": "***"}}', "damaged"),
])
def test_a_file_that_is_not_a_label_gets_a_sentence(text, expected):
    with pytest.raises(ValueError, match=expected):
        api.composition_loads(text)


def test_the_label_file_type_is_published():
    assert json.loads(api.options())["composition"] == {"extension": ".t003label", "mime": "application/json"}
