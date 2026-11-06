import itertools
from dataclasses import replace

import pytest
from PIL import Image

from dotlab import core, layers, render, spec


@pytest.fixture
def picture(tmp_path):
    path = tmp_path / "ramp.png"
    img = Image.new("L", (90, 50))
    img.putdata([(x * 255) // 89 for y in range(50) for x in range(90)])
    img.save(path)
    return str(path)


def _same_as_layers(label):
    converted = replace(label, layers=render.legacy_layers(label))
    assert render.render(label).tobytes() == render.render(converted).tobytes()


LOOKS = [
    {}, {"border": True}, {"bars": True}, {"border": True, "border_style": "marquee", "bars": True},
    {"background": "stars"}, {"effect": "outline", "align": "left", "valign": "top"}, {"italic": True, "size": 30},
]


@pytest.mark.parametrize("look", LOOKS)
@pytest.mark.parametrize("layout", ["left", "right", "top", "bottom", "behind"])
def test_legacy_picture_layouts_render_the_same_as_their_layers(picture, layout, look):
    _same_as_layers(core.LabelSpec(text="Hello\nthere", image_path=picture, image_layout=layout, image_size=35, **look))


@pytest.mark.parametrize("look", LOOKS)
@pytest.mark.parametrize("text,qr", [("Hi", ""), ("", "https://example.com"), ("Hi", "https://example.com")])
def test_legacy_text_and_qr_render_the_same_as_their_layers(text, qr, look):
    _same_as_layers(core.LabelSpec(text=text, qr=qr, **look))


def test_image_only_keeps_its_picture_and_its_text_hidden_and_now_draws_the_frame(picture):
    label = core.LabelSpec(text="kept", qr="https://x.example", image_path=picture, border=True)
    converted = replace(label, layers=render.legacy_layers(label))
    got = layers.parse(converted.layers)
    assert [(l.t, l.hidden) for l in got] == [("image", False), ("qr", True), ("text", True)]  # nothing lost, nothing new printed
    assert render.render(converted).getpixel((1, 100)) == 0  # the border is drawn now
    shown = layers.encode([replace(l, hidden=False) for l in got])
    assert render.render(replace(label, layers=shown)).tobytes() != render.render(converted).tobytes()  # unhide: they print


def test_two_texts_and_a_sticker_all_draw():
    one = layers.encode([layers.Layer("text", 8, 8, 368, 100, text="Top")])
    three = layers.encode([
        layers.Layer("text", 8, 8, 368, 100, text="Top"),
        layers.Layer("text", 8, 116, 368, 100, text="Bottom"),
        layers.sticker_layer("star", 340, 40, 2),
    ])
    a, b = (core.render(core.LabelSpec(layers=t)) for t in (one, three))
    assert a.tobytes() != b.tobytes()
    assert 0 in set(b.crop((8, 116, 376, 216)).tobytes())  # the second text
    assert 0 in set(b.crop((316, 16, 366, 64)).tobytes())  # the sticker


def test_a_hidden_layer_is_not_drawn():
    shown = layers.Layer("text", 8, 8, 368, 208, text="Hi")
    hidden = layers.Layer("text", 8, 8, 368, 208, text="Hi", hidden=True)
    blank = core.render(core.LabelSpec(layers=layers.encode([hidden]))).tobytes()
    assert set(blank) == {255} and core.render(core.LabelSpec(layers=layers.encode([shown]))).tobytes() != blank


def test_parse_is_lenient_and_encode_round_trips():
    text = ('[{"t":"text","x":1,"y":2,"w":3,"h":99999,"text":"a","bold":"yes"},{"t":"nope"},5,'
            '{"t":"sticker","name":"missing"},{"t":"sticker","name":"star","scale":99,"x":4,"y":5},'
            '{"t":"image","fit":"sideways"}]')
    got = layers.parse(text)
    assert [l.t for l in got] == ["text", "sticker", "image"]
    assert got[0].w == layers.MIN_BOX and got[0].h == spec.SH and got[0].bold is True  # a box is never bigger than the label
    assert got[1].scale == 9 and got[1].w == got[1].h == 24 * 9 and got[2].fit == "contain"
    assert layers.parse(layers.canonical(text)) == got and layers.canonical(layers.canonical(text)) == layers.canonical(text)
    assert layers.parse("not json") == () and layers.parse("{}") == () and layers.canonical("") == ""


def test_at_most_max_layers_are_kept():
    many = layers.encode([layers.Layer("text", text=str(i)) for i in range(layers.MAX_LAYERS + 5)])
    assert len(layers.parse(many)) == layers.MAX_LAYERS


def test_layers_count_as_content():
    assert spec.has_content(core.LabelSpec(layers=layers.encode([layers.Layer("text", text="x")])))
    assert not spec.has_content(core.LabelSpec())


def test_a_label_file_carries_every_image_layer_and_a_preset_drops_them(picture, tmp_path):
    from dotlab import api, composition
    other = tmp_path / "other.png"
    Image.new("L", (20, 20), 0).save(other)
    text = layers.encode([layers.Layer("image", 0, 0, 100, 100, path=picture), layers.Layer("text", 100, 0, 200, 100, text="x"),
                          layers.Layer("image", 0, 110, 100, 100, path=str(other))])
    label = core.LabelSpec(layers=text)
    loaded = composition.loads(composition.dumps(label), tmp_path / "store")
    got = layers.parse(loaded.layers)
    assert [l.t for l in got] == ["image", "text", "image"]
    assert all(__import__("pathlib").Path(l.path).is_file() for l in got if l.t == "image")
    assert core.render(loaded).tobytes() == core.render(label).tobytes()
    import json
    kept = json.loads(api.preset_entry("p", {"layers": text}))["spec"]["layers"]
    assert layers.image_paths(kept) == {}


def test_every_text_layers_font_is_fetched():
    from dotlab import api
    text = layers.encode([layers.Layer("text", text="a", font="Orbitron"), layers.Layer("text", text="b", font="Bangers")])
    names = api.fonts_needed({"layers": text})
    assert any("Orbitron" in n for n in names) and any("Bangers" in n for n in names)


def test_empty_hidden_layers_are_not_content_but_anything_visible_and_said_is():
    from dotlab import spec as s
    assert not s.has_content(core.LabelSpec(layers=layers.encode([layers.Layer("text"), layers.Layer("qr", data="  ")])))
    assert not s.has_content(core.LabelSpec(layers=layers.encode([layers.Layer("text", text="x", hidden=True)])))
    assert s.has_content(core.LabelSpec(layers=layers.encode([layers.Layer("text"), layers.Layer("qr", data="x")])))


# --- regressions found by the review of the layers branch -------------------------------------------------------------------


def test_the_regular_weight_japanese_fallback_is_fetched_for_a_regular_text_layer():
    from dotlab import api, fonts
    regular = layers.encode([layers.Layer("text", text="あ", font="Orbitron", bold=False)])
    bold = layers.encode([layers.Layer("text", text="あ", font="Orbitron", bold=True)])
    from pathlib import PurePath
    assert PurePath(fonts.FALLBACK_JA.pick(False, False)[0]).name in api.fonts_needed({"layers": regular})
    assert PurePath(fonts.FALLBACK_JA.pick(True, False)[0]).name in api.fonts_needed({"layers": bold})


def test_a_sticker_over_the_frame_migrates_to_the_same_pixels():
    label = core.LabelSpec(text="Hi", border=True, bars=True, stickers='[["star",8,8,3],["heart",376,216,2]]')
    assert render.render(label).tobytes() == render.render(render.migrate(label)).tobytes()


def test_legacy_stickers_are_ignored_once_there_are_layers():
    text = layers.encode([layers.Layer("text", 8, 8, 368, 208, text="Hi")])
    assert core.render(core.LabelSpec(layers=text, stickers='[["star",100,100,4]]')).tobytes() == core.render(core.LabelSpec(layers=text)).tobytes()


def test_the_frame_is_over_pictures_but_under_stickers(picture):
    from dotlab import stickers
    star = layers.sticker_layer("star", 60, 7, 1)  # on the top hazard bar (14 dots high), which has white stripes
    ink = stickers.mask("star", 1)
    left, top = star.x, star.y
    covered = [(left + x, top + y) for y in range(ink.height) for x in range(ink.width) if ink.getpixel((x, y)) and 0 <= top + y < 14]
    assert covered
    with_sticker = core.render(core.LabelSpec(bars=True, layers=layers.encode([star])))
    assert all(with_sticker.getpixel(p) == 0 for p in covered)  # the sticker's ink survives: the bar is under it
    cover = layers.Layer("image", 0, 0, 384, 224, path=picture, fit="cover")
    over = core.render(core.LabelSpec(bars=True, layers=layers.encode([cover])))
    bare = core.render(core.LabelSpec(layers=layers.encode([cover])))
    assert over.crop((0, 0, 384, 14)).tobytes() != bare.crop((0, 0, 384, 14)).tobytes()  # the bar is over the picture


def test_a_picture_used_by_several_layers_is_embedded_once_and_a_missing_one_is_blanked(picture, tmp_path):
    import json

    from dotlab import composition
    one = layers.Layer("image", 0, 0, 100, 100, path=picture)
    text = layers.encode([one, layers.Layer("image", 100, 0, 100, 100, path=picture), layers.Layer("image", 0, 100, 50, 50, path="/nope/gone.png")])
    blob = composition.dumps(core.LabelSpec(layers=text))
    inside = json.loads(Image.open(__import__("io").BytesIO(blob)).text["dotlab"])
    assert len(inside["layer_images"]) == 1  # not once per layer
    assert "/nope" not in inside["spec"]["layers"] and picture not in inside["spec"]["layers"]  # nothing of this machine's disk
    got = layers.parse(composition.loads(blob, tmp_path / "s").layers)
    assert got[0].path == got[1].path and got[0].path and got[2].path == ""


def test_a_box_with_fractional_numbers_is_rounded_not_thrown_away():
    got = layers.parse('[{"t":"text","x":12.5,"y":3.2,"w":100.6,"h":50.4,"text":"a"}]')[0]
    assert (got.x, got.y, got.w, got.h) == (12, 3, 101, 50)


# --- second review ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("junk", ["[]", "null", '[{"t":"sticker","name":"nope"}]'])
def test_a_layers_text_with_no_valid_layer_leaves_the_old_fields_in_charge(junk):
    old = core.LabelSpec(text="Hi", stickers='[["star",100,100,2]]')
    assert render.render(replace(old, layers=junk)).tobytes() == render.render(old).tobytes()
    assert layers.parse(render.migrate(replace(old, layers=junk)).layers)  # and migration still converts them


def test_a_label_with_a_qr_code_too_long_to_draw_still_migrates_and_still_says_so_when_drawn():
    from dotlab.render import PrinterError
    old = core.LabelSpec(text="Hi", qr="x" * 5000)
    moved = render.migrate(old)
    assert [l.t for l in layers.parse(moved.layers)] == ["qr", "text"]
    with pytest.raises(PrinterError):
        render.render(moved)


def test_an_old_label_with_the_most_stickers_keeps_every_one_of_them(picture):
    from dotlab import stickers
    placed = stickers.encode([("star", 20 + i, 30, 1) for i in range(stickers.MAX_PLACED)])
    moved = render.migrate(core.LabelSpec(text="Hi", qr="x", image_path=picture, image_layout="left", stickers=placed))
    assert len(layers.parse(moved.layers)) == stickers.MAX_PLACED + 3


def test_a_label_file_cannot_pull_in_a_picture_from_this_machines_disk(picture, tmp_path):
    import io
    import json

    from dotlab import composition
    blob = composition.dumps(core.LabelSpec(layers=layers.encode([layers.Layer("text", text="x")])))
    inside = json.loads(Image.open(io.BytesIO(blob)).text["dotlab"])
    inside["spec"]["layers"] = layers.encode([layers.Layer("image", 0, 0, 50, 50, path=picture)])
    info = __import__("PIL.PngImagePlugin", fromlist=["PngInfo"]).PngInfo()
    info.add_text(composition.KEY, json.dumps(inside))
    out = io.BytesIO()
    Image.open(io.BytesIO(blob)).save(out, format="PNG", pnginfo=info)
    assert layers.image_paths(composition.loads(out.getvalue(), tmp_path / "s").layers) == {}


def test_one_missing_picture_does_not_take_the_others_out_of_the_saved_preview(picture):
    import io

    from dotlab import composition
    label = core.LabelSpec(layers=layers.encode([layers.Layer("image", 0, 0, 100, 100, path=picture),
                                                 layers.Layer("image", 150, 0, 100, 100, path="/nope/gone.png")]))
    preview = Image.open(io.BytesIO(composition.dumps(label))).convert("L")
    assert 0 in set(preview.crop((0, 0, 100, 100)).tobytes())  # the picture that is there is in the file's own picture


def test_a_box_cannot_be_bigger_than_the_label():
    got = layers.parse('[{"t":"image","w":10000,"h":10000,"fit":"cover"}]')[0]
    assert (got.w, got.h) == (spec.W, spec.SH)


# --- rotate and flip ----------------------------------------------------------------------------------------------------------


def _ink(img, box):
    region = img.crop(box).point(lambda v: 255 if v < 128 else 0).getbbox()
    return None if region is None else (region[0] + box[0], region[1] + box[1], region[2] + box[0], region[3] + box[1])


def _render(*items, **kw):
    return core.render(core.LabelSpec(layers=layers.encode(items), **kw))


def test_a_quarter_turn_makes_text_stand_up_inside_its_turned_box():
    flat = _render(layers.Layer("text", 20, 20, 300, 80, text="WIDE"))
    tall = _render(layers.Layer("text", 20, 20, 80, 190, text="WIDE", rot=90))  # the box turned with it: 80 wide, 190 tall
    a, b = _ink(flat, (0, 0, 384, 224)), _ink(tall, (0, 0, 384, 224))
    assert a[2] - a[0] > a[3] - a[1]  # lying down
    assert b[3] - b[1] > b[2] - b[0]  # standing up
    assert 20 <= b[0] and b[2] <= 100 and 20 <= b[1] and b[3] <= 210  # and inside its box


def test_turns_flips_and_their_compositions_are_exact():
    base = layers.Layer("text", 20, 20, 200, 120, text="Lg", font="Orbitron")
    plain = _render(base)
    assert _render(replace(base, rot=0)).tobytes() == plain.tobytes()
    assert _render(replace(base, rot=180)).tobytes() == _render(replace(base, mirror=True, flip=True)).tobytes()  # 180° = both flips
    assert _render(replace(base, rot=180)).tobytes() != plain.tobytes()
    box = (20, 20, 220, 140)
    flipped = _render(replace(base, mirror=True)).crop(box)
    assert flipped.tobytes() == plain.crop(box).transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()


def test_a_sticker_mirrors_and_turns_dot_for_dot():
    from dotlab import stickers
    mask = stickers.mask("arrow-right", 2)
    side = mask.width
    at = (40, 40)
    def drawn(**kw):
        layer = replace(layers.sticker_layer("arrow-right", 0, 0, 2), x=at[0], y=at[1], **kw)
        return _render(layer).crop((at[0], at[1], at[0] + side, at[1] + side))
    assert 0 in set(drawn().tobytes())  # it is there
    assert drawn(mirror=True).tobytes() == drawn().transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    assert drawn(rot=90).tobytes() == drawn().transpose(Image.Transpose.ROTATE_270).tobytes()  # clockwise
    assert drawn(rot=270).tobytes() == drawn().transpose(Image.Transpose.ROTATE_90).tobytes()


def test_a_turned_picture_fills_the_turned_box(tmp_path):
    path = tmp_path / "black.png"
    Image.new("L", (90, 50), 0).save(path)  # wide
    got = _render(layers.Layer("image", 50, 10, 100, 200, path=str(path), rot=90))  # in a tall box, turned
    box = _ink(got, (0, 0, 384, 224))
    assert box == (50, 20, 150, 200)  # 90x50 fits the box's own 200x100 as 180x100; turned it is 100 wide, 180 tall, centred in the box
    flat = _render(layers.Layer("image", 50, 10, 200, 100, path=str(path)))
    assert _ink(flat, (0, 0, 384, 224)) == (60, 10, 240, 110)


def test_a_turned_qr_code_is_still_drawn_inside_its_box():
    got = _render(layers.Layer("qr", 100, 40, 120, 120, data="https://example.com", rot=90, mirror=True))
    box = _ink(got, (0, 0, 384, 224))
    assert box is not None and 95 <= box[0] and box[2] <= 225 and 35 <= box[1] and box[3] <= 165


def test_a_turn_is_rounded_to_the_nearest_quarter():
    turns = [l.rot for l in layers.parse('[{"t":"text","rot":100},{"t":"text","rot":-90},{"t":"text","rot":400},{"t":"text","rot":"x"},{"t":"text","rot":270}]')]
    assert turns == [90, 270, 0, 0, 270]


def test_a_pngs_transparent_parts_let_the_paper_show_through(tmp_path):
    """A cut-out (black disc, rest see-through) over a background: the disc prints, the corners keep the pattern."""
    art = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for y in range(30, 70):
        for x in range(30, 70):
            art.putpixel((x, y), (0, 0, 0, 255))
    path = tmp_path / "cutout.png"
    art.save(path)
    box = layers.Layer("image", 0, 0, 100, 100, path=str(path))
    label = core.LabelSpec(background="checker", layers=layers.encode([box]))
    plain = core.LabelSpec(background="checker")
    out, base = render.render(label), render.render(plain)
    corner = [(x, y) for x in range(0, 20) for y in range(0, 20)]
    assert all(out.getpixel(p) == base.getpixel(p) for p in corner)  # the pattern shows where the PNG is clear
    assert all(out.getpixel((x, y)) == 0 for x in range(40, 60) for y in range(40, 60))  # and the picture prints
    opaque = tmp_path / "opaque.png"
    Image.new("RGB", (100, 100), "white").save(opaque)  # no transparency: still a white box over the pattern
    white = core.LabelSpec(background="checker", layers=layers.encode([layers.Layer("image", 0, 0, 100, 100, path=str(opaque))]))
    assert all(render.render(white).getpixel(p) == 255 for p in corner)


def test_remove_background_clears_the_flat_colour_round_a_picture_but_not_a_hole_inside_it(tmp_path):
    art = Image.new("RGB", (100, 100), "white")  # a black ring on white: no transparency in the file
    for y in range(100):
        for x in range(100):
            if 20 <= ((x - 50) ** 2 + (y - 50) ** 2) ** 0.5 <= 40 and ((x - 50) ** 2 + (y - 50) ** 2) ** 0.5 >= 28:
                art.putpixel((x, y), (0, 0, 0))
    path = tmp_path / "ring.png"
    art.save(path)

    def shown(cutout):
        box = layers.Layer("image", 0, 0, 100, 100, path=str(path), cutout=cutout, dither="threshold", threshold=128)
        return render.render(core.LabelSpec(background="checker", layers=layers.encode([box])))

    base = render.render(core.LabelSpec(background="checker"))
    off, on = shown(0), shown(30)
    corner = [(x, y) for x in range(0, 12) for y in range(0, 12)]
    assert all(off.getpixel(p) == 255 for p in corner)  # off: the white box covers the pattern
    assert all(on.getpixel(p) == base.getpixel(p) for p in corner)  # on: it shows
    assert on.getpixel((50, 16)) == 0  # the ring itself still prints
    assert on.getpixel((50, 50)) == 255 and off.getpixel((50, 50)) == 255  # the hole inside the ring is picture, not background
