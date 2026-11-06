import base64
import io
import json

import pytest
from PIL import Image

from dotlab import composition, core, doodle, stickers
from dotlab.spec import H, SH, W, LabelSpec, has_content


def _mask(*boxes) -> Image.Image:
    img = Image.new("L", (W, SH), 0)
    for box in boxes:
        img.paste(255, box)
    return img


def test_round_trip_and_empty():
    text = doodle.encode(_mask((10, 10, 29, 19)))
    ink = doodle.decode(text)
    assert ink.size == (W, SH) and ink.getpixel((10, 10)) == 255 and ink.getpixel((30, 10)) == 0
    assert doodle.encode(_mask()) == "" and doodle.decode("") is None


@pytest.mark.parametrize("bad", ["not base64!", base64.b64encode(b"nope").decode(),
                                 base64.b64encode(io.BytesIO().getvalue()).decode()])
def test_damaged_doodle_is_ignored(bad):
    assert doodle.decode(bad) is None
    assert core.render(LabelSpec(text="x", doodle=bad)).size == (W, core.H)


def test_wrong_size_is_ignored():
    out = io.BytesIO()
    Image.new("1", (10, 10), 1).save(out, "PNG")
    assert doodle.decode(base64.b64encode(out.getvalue()).decode()) is None


def test_ink_is_drawn_on_top_of_everything():
    plain = core.render(LabelSpec(text="HELLO", background="checker"))
    inked = core.render(LabelSpec(text="HELLO", background="checker", doodle=doodle.encode(_mask((0, 0, 99, 99)))))
    assert {inked.getpixel((x, y)) for x in range(99) for y in range(99)} == {0}
    assert inked.crop((100, 0, W, core.H)).tobytes() == plain.crop((100, 0, W, core.H)).tobytes()


def test_doodle_also_sits_on_an_image_only_label(tmp_path):
    path = tmp_path / "white.png"
    Image.new("RGB", (50, 50), "white").save(path)
    spec = LabelSpec(image_path=str(path), doodle=doodle.encode(_mask((5, 5, 14, 14))))
    assert core.render(spec).getpixel((5, 5)) == 0


def test_the_doodle_never_reaches_the_gap():
    img = core.render(LabelSpec(doodle=doodle.encode(_mask((0, 0, W - 1, SH - 1)))))
    assert {img.getpixel((x, y)) for x in (0, W - 1) for y in range(SH, core.H)} == {255}


def test_doodle_travels_in_a_composition_and_a_bad_type_falls_back():
    spec = LabelSpec(text="a", doodle=doodle.encode(_mask((1, 1, 5, 5))))
    assert composition.loads(composition.dumps(spec)).doodle == spec.doodle
    assert LabelSpec.from_dict({"doodle": 5}).doodle == ""


def test_every_sticker_has_ink_and_fits_the_sticker_at_every_size():
    from dotlab import stickers

    for name in stickers.STICKERS:
        side = stickers.size(name)
        assert side in (16, 24), name
        for scale in range(1, stickers.MAX_SCALE + 1):
            m = stickers.mask(name, scale)
            assert m.size == (side * scale,) * 2 and m.getbbox(), (name, scale)
            assert m.size[1] <= SH
        hist = stickers.mask(name, 1).histogram()
        assert hist[0] + hist[255] == side * side


# --- the vocabulary clients draw with (doodle.describe) ---------------------------------------------------------------

def test_describe_is_plain_json_and_complete():
    import json

    info = json.loads(json.dumps(doodle.describe()))
    assert [t for t, _ in info["tools"]] == list(doodle.TOOLS)
    assert [i for i, _, _ in info["inks"]] == list(doodle.INKS)
    assert set(info["uses_ink"]) <= set(doodle.TOOLS) and set(info["uses_brush"]) <= set(doodle.TOOLS)
    assert all(len(rows) in (4, 8) and all(len(r) == len(rows) for r in rows) for _, _, rows in info["inks"])
    assert all(set("".join(rows)) <= set("#.") and "#" in "".join(rows) for _, _, rows in info["inks"])
    assert info["width"] == W and info["height"] == SH
    lo, hi, start = info["brush"]
    assert lo <= start <= hi
    assert "sticker_scale" not in info and "max_stickers" not in info  # stickers are layers now


def test_stickers_reach_clients_as_bitmaps_that_match_the_masks():
    import json

    from dotlab import api

    published = json.loads(api.options())["stickers"]
    assert set(published) == set(stickers.STICKERS)
    for name, sticker in published.items():
        mask = stickers.mask(name, 1)
        side = stickers.size(name)
        assert len(sticker["rows"]) == side and all(len(r) == side for r in sticker["rows"])
        assert sticker["label"] == stickers.STICKERS[name][0]
        for y, row in enumerate(sticker["rows"]):
            assert all((c == "1") == bool(mask.getpixel((x, y))) for x, c in enumerate(row)), name
        assert "1" in "".join(sticker["rows"])  # none is empty


def test_a_browser_canvas_png_is_a_valid_doodle():
    """A browser writes the ink as an RGBA PNG (white = ink, on opaque black), not as the 1-bit PNG `encode` makes."""
    import base64
    import io

    from PIL import Image

    canvas = Image.new("RGBA", (W, SH), (0, 0, 0, 255))
    canvas.paste((255, 255, 255, 255), (10, 20, 30, 40))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    mask = doodle.decode(base64.b64encode(out.getvalue()).decode())
    assert mask is not None and mask.getbbox() == (10, 20, 30, 40) and mask.getpixel((15, 25)) == 255
    assert mask.getpixel((0, 0)) == 0


# --- placed stickers (LabelSpec.stickers): objects under the ink, not part of it ------------------------------------------

def test_there_are_plenty_of_stickers_and_the_largest_size_fits_the_sticker():
    assert len(stickers.STICKERS) >= 70
    assert stickers.GRID * stickers.MAX_SCALE <= SH


def test_stickers_text_round_trips_and_bad_entries_are_dropped():
    placed = (("star", 100, 50, 3), ("heart", -4, 20, 1))
    assert stickers.parse(stickers.encode(placed)) == placed
    assert stickers.encode(()) == "" and stickers.parse("") == ()
    messy = '[["star",1,2,99],["nope",1,2,3],["heart",1,2],["cat","x",2,3],["ghost",true,2,3],5,["sun",1.5,2,3]]'
    assert stickers.parse(messy) == (("star", 1, 2, stickers.MAX_SCALE),)  # clamped; the rest skipped
    for junk in ("not json", "{}", "null", "[[", '"star"'):
        assert stickers.parse(junk) == ()
    many = stickers.encode([("star", 1, 1, 1)] * (stickers.MAX_PLACED + 5))
    assert len(stickers.parse(many)) == stickers.MAX_PLACED
    assert stickers.canonical(messy) == stickers.canonical(stickers.canonical(messy))


def test_a_placed_sticker_is_drawn_centred_and_under_the_doodle_ink():
    text = stickers.encode([("star", 100, 100, 2)])
    out = core.render(LabelSpec(stickers=text))
    m = stickers.mask("star", 2)
    left = 100 - (m.width >> 1)
    dark = {(x, y) for y in range(H) for x in range(W) if out.getpixel((x, y)) == 0}
    assert dark == {(left + x, left + y) for y in range(m.height) for x in range(m.width) if m.getpixel((x, y))}
    # ink is drawn over the sticker: a dot of ink on a bare spot of label shows, and the sticker's other dots are unchanged
    ink = Image.new("L", (W, SH), 0)
    ink.putpixel((0, 0), 255)
    both = core.render(LabelSpec(stickers=text, doodle=doodle.encode(ink)))
    assert both.getpixel((0, 0)) == 0 and both.getpixel((left + 10, left + 10)) == out.getpixel((left + 10, left + 10))


def test_stickers_never_draw_below_the_sticker_or_off_the_label():
    text = stickers.encode([("star", 380, SH - 1, 9), ("star", 0, 0, 9), ("star", -500, 9000, 3)])
    out = core.render(LabelSpec(stickers=text))
    assert out.size == (W, H)
    assert all(out.getpixel((x, y)) == 255 for y in range(SH, H) for x in range(0, W, 7))
    assert any(out.getpixel((x, y)) == 0 for y in range(SH) for x in range(W))


def test_stickers_alone_are_content_and_travel_in_presets_and_files():
    from dotlab import api

    text = stickers.encode([("cat", 40, 40, 2)])
    assert has_content(LabelSpec(stickers=text)) and not has_content(LabelSpec())
    assert composition.loads(composition.dumps(LabelSpec(stickers=text))).stickers == text
    entry = json.loads(api.preset_entry("cats", {"stickers": text, "image_path": "x.png"}))
    assert entry["spec"]["stickers"] == text and entry["spec"]["image_path"] == ""
    assert api.preview_pixels({"stickers": text}) != api.preview_pixels({})
    assert LabelSpec.from_dict({"stickers": 5}).stickers == ""


def test_every_sticker_is_in_exactly_one_group_and_the_groups_reach_clients():
    from dotlab import api

    listed = [name for _, keys in stickers.GROUPS for name in keys]
    assert sorted(listed) == sorted(stickers.STICKERS) and len(listed) == len(set(listed))
    groups = json.loads(api.options())["sticker_groups"]
    assert [(g["label"], tuple(g["stickers"])) for g in groups] == list(stickers.GROUPS)


def test_the_kenney_tiles_are_square_bitmaps_with_their_licence_shipped():
    from pathlib import Path

    from dotlab import sticker_tiles

    for key, (title, rows) in sticker_tiles.TILES.items():
        assert title and len(rows) == 16 and all(len(r) == 16 and set(r) <= {"0", "1"} for r in rows), key
        assert any("1" in r for r in rows), key
    licence = Path(stickers.__file__).parent / "assets" / "LICENSE.kenney-1-bit-pack.txt"
    assert "Creative Commons Zero" in licence.read_text(encoding="utf-8")


def test_white_ink_is_stored_drawn_over_the_picture_and_survives_canonical():
    both = Image.new("L", (W, SH), 0)
    both.paste(255, (0, 0, 20, 20))  # black ink
    both.paste(128, (30, 0, 50, 20))  # white ink
    text = doodle.encode(both)
    assert doodle.decode(text).getbbox() == (0, 0, 20, 20) and doodle.decode_white(text).getbbox() == (30, 0, 50, 20)
    assert doodle.canonical(text) == text
    assert doodle.decode_white(doodle.encode(_mask((1, 1, 5, 5)))) is None  # black only: no white plane
    img = core.render(LabelSpec(background="checker", doodle=text)).convert("L")
    assert img.crop((0, 0, 20, 20)).getextrema() == (0, 0)  # black ink
    assert img.crop((30, 0, 50, 20)).getextrema() == (255, 255)  # white ink knocks the checker out to paper
