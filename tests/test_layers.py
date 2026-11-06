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
