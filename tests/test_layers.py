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


def test_image_only_keeps_its_picture_but_no_longer_loses_the_frame(picture):
    label = core.LabelSpec(text="gone", image_path=picture, border=True)
    converted = replace(label, layers=render.legacy_layers(label))
    assert [l.t for l in layers.parse(converted.layers)] == ["image"]
    assert render.render(converted).getpixel((1, 100)) == 0  # the border is drawn now


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
    assert got[0].w == layers.MIN_BOX and got[0].h == layers.LIMIT and got[0].bold is True
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
