import pytest
from PIL import Image

from dotlab import core

MARGIN = core.MARGIN
AX0, AX1, AY0, AY1 = MARGIN, core.W - MARGIN, MARGIN, core.SH - MARGIN  # usable area with no border or bars


@pytest.fixture
def black(tmp_path):
    path = tmp_path / "black.png"
    Image.new("L", (100, 100), 0).save(path)
    return str(path)


def _ink_box(img, area):
    """Bounding box of black pixels inside `area` (left, top, right, bottom), or None."""
    region = img.crop(area).point(lambda v: 255 if v < 128 else 0)
    box = region.getbbox()
    return None if box is None else (box[0] + area[0], box[1] + area[1], box[2] + area[0], box[3] + area[1])


def _spec(black, layout, **kw):
    return core.LabelSpec(text="Hello", image_path=black, image_layout=layout, **kw)


def test_only_ignores_the_text_exactly_as_before(black):
    with_text = core.render(_spec(black, "only"))
    assert with_text.tobytes() == core.render(core.LabelSpec(image_path=black)).tobytes()


@pytest.mark.parametrize("layout", ["left", "right"])
def test_side_layouts_split_the_width_and_keep_text_clear_of_the_picture(black, layout):
    img = core.render(_spec(black, layout, image_size=40))
    size = int((AX1 - AX0) * 0.4)
    pic = (AX0, AY0, AX0 + size, AY1) if layout == "left" else (AX1 - size, AY0, AX1, AY1)
    rest = (AX0 + size + MARGIN, AY0, AX1, AY1) if layout == "left" else (AX0, AY0, AX1 - size - MARGIN, AY1)
    assert img.getpixel(((pic[0] + pic[2]) // 2, core.SH // 2)) == 0  # the (black) picture is in its strip
    ink = _ink_box(img, rest)
    assert ink is not None  # the text is in the remaining area ...
    gap = (pic[2], AY0, rest[0], AY1) if layout == "left" else (rest[2], AY0, pic[0], AY1)
    assert _ink_box(img, gap) is None  # ... and nothing crosses the gutter between them


@pytest.mark.parametrize("layout", ["top", "bottom"])
def test_band_layouts_split_the_height(black, layout):
    img = core.render(_spec(black, layout, image_size=50))
    size = int((AY1 - AY0) * 0.5)
    pic = (AX0, AY0, AX1, AY0 + size) if layout == "top" else (AX0, AY1 - size, AX1, AY1)
    rest = (AX0, AY0 + size + MARGIN, AX1, AY1) if layout == "top" else (AX0, AY0, AX1, AY1 - size - MARGIN)
    assert img.getpixel((core.W // 2, (pic[1] + pic[3]) // 2)) == 0
    assert _ink_box(img, rest) is not None


def test_image_size_controls_the_share_and_is_clamped(black):
    def picture_width(size):
        img = core.render(core.LabelSpec(image_path=black, image_layout="left", image_size=size))
        box = _ink_box(img, (0, 0, core.W, core.SH))
        return box[2] - box[0]

    assert picture_width(30) < picture_width(60)
    assert picture_width(1) == picture_width(20)  # clamped to 20-80 %
    assert picture_width(500) == picture_width(80)


def test_behind_fills_the_label_with_the_picture_and_keeps_the_text_readable(tmp_path):
    grey = tmp_path / "grey.png"
    Image.new("L", (60, 30), 100).save(grey)  # a wide picture: "behind" must cover, not letterbox
    spec = core.LabelSpec(text="Hi", image_path=str(grey), image_layout="behind")
    img = core.render(spec)
    assert all(img.getpixel(p) == 100 for p in ((1, 1), (core.W - 2, 1), (1, core.SH - 2), (core.W - 2, core.SH - 2)))
    plain = core.render(core.LabelSpec(image_path=str(grey), image_layout="behind"))
    assert img.tobytes() != plain.tobytes()  # the text is drawn
    assert 255 in set(img.tobytes()) and 0 in set(img.tobytes())  # with a white halo and black ink over the grey


def test_qr_and_text_still_share_what_the_picture_leaves(black):
    spec = core.LabelSpec(text="Hi", qr="https://example.com", image_path=black, image_layout="left", image_size=30)
    img = core.render(spec)
    assert img.size == (core.W, core.H) and _ink_box(img, (AX0, AY0, AX1, AY1)) is not None
    right_half = _ink_box(img, (core.W // 2 + 40, AY0, AX1, AY1))
    assert right_half is not None  # the QR code is on the right of the remaining area


def test_borders_and_bars_still_apply(black):
    plain = core.render(_spec(black, "right"))
    framed = core.render(_spec(black, "right", border=True, bars=True))
    assert framed.tobytes() != plain.tobytes()
    assert set(framed.crop((0, core.SH, core.W, core.H)).tobytes()) == {255}  # nothing below the sticker


def test_unknown_layout_falls_back_to_image_only(black):
    assert core.render(_spec(black, "sideways")).tobytes() == core.render(_spec(black, "only")).tobytes()


def test_layouts_work_with_every_image_look(black):
    for kw in ({"dither": "bayer4"}, {"threshold": 120}, {"pixelate": 4}, {"mirror": True, "invert": True}):
        for layout in ("left", "top", "behind"):
            assert core.render(_spec(black, layout, **kw)).size == (core.W, core.H)

