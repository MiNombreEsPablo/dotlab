import io
import json

import pytest
from PIL import Image, PngImagePlugin

from t003gui import cli, composition, core


def _file(payload, key=composition.KEY) -> bytes:
    """A PNG carrying `payload` (a dict, or raw text) the way a label file does, to test what the reader accepts."""
    info = PngImagePlugin.PngInfo()
    info.add_text(key, payload if isinstance(payload, str) else json.dumps(payload), zip=True)
    out = io.BytesIO()
    Image.new("1", (8, 8), 1).save(out, "PNG", pnginfo=info)
    return out.getvalue()


def _spec(**kw):
    base = dict(text="Hello\nWorld", qr="https://example.com", copies=3, density=9, font="Orbitron", bold=False,
                italic=True, size=40, align="left", valign="top", effect="shadow", border=True,
                border_style="double", background="grid", bars=True, threshold=99)
    return core.LabelSpec(**{**base, **kw})


def test_round_trip(tmp_path):
    path = tmp_path / ("a" + composition.SUFFIX)
    composition.save(path, _spec())
    assert composition.load(path) == _spec()
    assert not list(tmp_path.glob("*.tmp"))  # the atomic write cleaned up


def test_image_is_embedded_so_the_file_travels(tmp_path):
    art = tmp_path / "art.png"
    Image.new("L", (30, 20), 0).save(art)
    path = tmp_path / ("a" + composition.SUFFIX)
    composition.save(path, _spec(image_path=str(art)))
    art.unlink()  # as if the file were opened on another machine

    data = json.loads(Image.open(path).text[composition.KEY])
    assert data["spec"]["image_path"] == "" and data["image"]["name"] == "art.png"
    loaded = composition.load(path, image_dir=tmp_path / "out")
    assert loaded.image_path.startswith(str(tmp_path / "out")) and Image.open(loaded.image_path).size == (30, 20)
    assert core.render(loaded).size == (core.W, core.H)  # and it renders


def test_a_missing_image_keeps_its_path_instead_of_failing(tmp_path):
    path = tmp_path / ("a" + composition.SUFFIX)
    composition.save(path, _spec(image_path="/no/such/file.png"))
    assert composition.load(path).image_path == "/no/such/file.png"


def test_embedded_names_cannot_escape_the_image_folder(tmp_path):
    blob = "aGk="  # "hi"
    for name in ("../../evil.png", "/etc/passwd", "a/b/c.png", "x.sh", ""):
        payload = {"format": composition.FORMAT, "version": 1, "spec": {}, "image": {"name": name, "data": blob}}
        out = tmp_path / "out"
        path = composition.Path(composition.loads(_file(payload), image_dir=out).image_path)
        assert path.parent == out and path.suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


@pytest.mark.parametrize("blob, message", [
    (b"not a picture at all", "isn't a PNG"),
    (_file("not json"), "damaged"),
    (_file("[]"), "not a Dotlab label file"),
    (_file({"format": "other", "version": 1, "spec": {}}), "not a Dotlab label file"),
    (_file({"format": composition.FORMAT, "version": 99, "spec": {}}), "newer version"),
    (_file({"format": composition.FORMAT, "spec": {}}), "newer version"),
    (_file({"format": composition.FORMAT, "version": 1, "spec": {}, "image": {"name": "a.png", "data": "@@"}}), "damaged"),
    (_file({"format": composition.FORMAT, "version": 1, "spec": {}}, key="something-else"), "only an image"),
])
def test_bad_files_are_refused_with_a_reason(blob, message):
    with pytest.raises(ValueError, match=message):
        composition.loads(blob)


def test_the_file_is_a_picture_of_the_printed_label(tmp_path):
    spec = _spec()
    path = tmp_path / "a.png"
    composition.save(path, spec)
    picture = Image.open(path)
    assert (picture.size, picture.mode) == ((core.W, core.SH), "1")
    assert picture.tobytes() == core.label_bitmap(spec).tobytes()  # any viewer shows exactly what prints


def test_a_big_embedded_photo_survives(tmp_path):
    import os

    noise = tmp_path / "noise.png"
    Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3)).save(noise)  # incompressible, a few MB
    assert noise.stat().st_size > 2_000_000
    path = tmp_path / "a.png"
    composition.save(path, _spec(image_path=str(noise)))
    back = composition.load(path, image_dir=tmp_path / "out")
    assert composition.Path(back.image_path).read_bytes() == noise.read_bytes()


def test_unknown_fields_are_ignored():
    blob = _file({"format": composition.FORMAT, "version": 1, "spec": {"text": "hi", "from_the_future": 1}})
    assert composition.loads(blob).text == "hi"


def test_export_png_is_the_printed_sticker(tmp_path):
    spec = core.LabelSpec(text="Hi")
    one, four = tmp_path / "1.png", tmp_path / "4.png"
    core.export_png(spec, one)
    core.export_png(spec, four, scale=4)
    a, b = Image.open(one), Image.open(four)
    assert (a.size, a.mode) == ((core.W, core.SH), "1")
    assert (b.size, b.mode) == ((core.W * 4, core.SH * 4), "1")
    assert b.resize(a.size, Image.Resampling.NEAREST).tobytes() == a.tobytes()  # nothing but enlarged dots
    expected = core.to_bitmap(core.render(spec)).crop((0, 0, core.W, core.SH))
    assert a.tobytes() == expected.tobytes()


def test_cli_loads_a_composition_and_flags_override_it(tmp_path):
    saved = tmp_path / ("a" + composition.SUFFIX)
    composition.save(saved, core.LabelSpec(text="from file", effect="outline"))
    out = tmp_path / "p.png"
    cli.main(["--file", str(saved), "--preview", str(out)])
    expected = core.to_bitmap(core.render(core.LabelSpec(text="from file", effect="outline")))
    assert Image.open(out).tobytes() == expected.tobytes()
    with pytest.raises(SystemExit):
        cli.main(["--file", str(tmp_path / ("missing" + composition.SUFFIX))])
    with pytest.raises(SystemExit):
        cli.main(["--file", str(saved), "--preset", "x"])


def test_wrong_typed_fields_fall_back_to_their_defaults():
    blob = _file({"format": composition.FORMAT, "version": 1,
                  "spec": {"text": "hi", "copies": "two", "bold": 1, "gamma": 2, "threshold": None}})
    spec = composition.loads(blob)
    assert (spec.text, spec.copies, spec.bold, spec.gamma, spec.threshold) == ("hi", 1, True, 2, None)


# --- a doodle is compact in a file, whichever client drew it -------------------------------------------------------------

def _browser_style_doodle(boxes):
    """The doodle as a browser writes it: an opaque RGBA PNG, white dots = ink."""
    import base64
    import io

    from PIL import Image

    from t003gui.spec import SH, W

    canvas = Image.new("RGBA", (W, SH), (0, 0, 0, 255))
    for box in boxes:
        canvas.paste((255, 255, 255, 255), box)
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def test_saving_re_encodes_a_browsers_doodle_compactly_without_changing_it():
    from t003gui import doodle

    bulky = _browser_style_doodle([(10, 10, 90, 40), (200, 100, 210, 180)])
    spec = core.LabelSpec(text="x", doodle=bulky)
    saved = composition.loads(composition.dumps(spec))
    assert len(saved.doodle) < len(bulky) / 3
    assert doodle.decode(saved.doodle).tobytes() == doodle.decode(bulky).tobytes()  # the same ink, dot for dot
    assert composition.dumps(saved) == composition.dumps(composition.loads(composition.dumps(saved)))  # and stable


def test_canonical_is_idempotent_and_drops_what_is_not_a_doodle():
    from t003gui import doodle

    once = doodle.canonical(_browser_style_doodle([(5, 5, 50, 50)]))
    assert once and doodle.canonical(once) == once
    assert doodle.canonical("") == "" and doodle.canonical("not a png") == ""
