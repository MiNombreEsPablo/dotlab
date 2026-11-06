from pathlib import Path

import pytest
from PIL import Image

from dotlab import core, imaging


def _save(tmp_path, img, name="in.png", **kw):
    path = tmp_path / name
    img.save(path, **kw)
    return str(path)


def _gradient(width=256, height=40):
    img = Image.new("L", (width, height))
    img.putdata([x for y in range(height) for x in range(width)])
    return img


def _values(img):
    return img.convert("L").tobytes()


def _white_fraction(img):
    return _values(img).count(255) / (img.width * img.height)


def test_default_pipeline_is_unchanged_from_before_dither_options(tmp_path):
    path = _save(tmp_path, _gradient())
    spec = core.LabelSpec(image_path=path)
    expected = Image.new("L", (core.W, core.H), 255)
    src = imaging.ImageOps.contain(Image.open(path).convert("L"), (core.W, core.SH))
    expected.paste(src, ((core.W - src.width) // 2, (core.SH - src.height) // 2))
    assert core.render(spec).tobytes() == expected.tobytes()


@pytest.mark.parametrize("dither", ["bayer4", "bayer8"])
def test_ordered_dither_is_pure_black_and_white_and_tracks_brightness(tmp_path, dither):
    for grey in (32, 128, 224):
        path = _save(tmp_path, Image.new("L", (200, 100), grey), f"g{grey}.png")
        out = imaging.process(core.LabelSpec(image_path=path, dither=dither))
        assert set(_values(out)) <= {0, 255}
        assert abs(_white_fraction(out) - grey / 255) < 0.06, (dither, grey)


def test_ordered_dither_makes_a_regular_pattern(tmp_path):
    path = _save(tmp_path, Image.new("L", (64, 64), 128))
    out = imaging.process(core.LabelSpec(image_path=path, dither="bayer4"))
    # a 4x4 matrix repeats exactly every 4 pixels
    assert out.crop((0, 0, 4, 4)).tobytes() == out.crop((4, 4, 8, 8)).tobytes() == out.crop((16, 8, 20, 12)).tobytes()


def test_bayer_matrix_uses_every_level_once():
    for n in (2, 4, 8):
        flat = [v for row in imaging._bayer_matrix(n) for v in row]
        assert sorted(flat) == list(range(n * n))


def test_hard_cutoff_still_wins_over_dither(tmp_path):
    path = _save(tmp_path, _gradient())
    out = imaging.process(core.LabelSpec(image_path=path, threshold=100, dither="bayer4"))
    assert set(_values(out)) <= {0, 255}
    assert out.getpixel((50, 5)) == 0 and out.getpixel((200, 5)) == 255  # left of the cutoff black, right white


def test_tone_controls():
    grey = Image.new("L", (4, 4), 100)
    assert imaging.tone(grey).getpixel((0, 0)) == 100  # defaults change nothing
    assert imaging.tone(grey, brightness=50).getpixel((0, 0)) > 100
    assert imaging.tone(grey, brightness=-50).getpixel((0, 0)) < 100
    assert imaging.tone(grey, gamma=2.0).getpixel((0, 0)) > 100
    assert imaging.tone(grey, gamma=0.5).getpixel((0, 0)) < 100
    assert imaging.tone(grey, brightness=-100).getpixel((0, 0)) == 0
    pair = Image.new("L", (2, 1))
    pair.putdata([200, 60])  # contrast pivots on the average, so it needs both a light and a dark pixel
    stretched = imaging.tone(pair, contrast=60)
    assert stretched.getpixel((0, 0)) > 200 and stretched.getpixel((1, 0)) < 60
    flattened = imaging.tone(pair, contrast=-60)
    assert flattened.getpixel((0, 0)) < 200 and flattened.getpixel((1, 0)) > 60
    assert imaging.tone(Image.new("L", (2, 2), 255), gamma=3.0).getpixel((0, 0)) == 255  # white and black stay put
    assert imaging.tone(Image.new("L", (2, 2), 0), gamma=0.3).getpixel((0, 0)) == 0


def test_tone_changes_the_printed_dots(tmp_path):
    path = _save(tmp_path, Image.new("L", (100, 100), 128))
    dark = core.to_bitmap(core.render(core.LabelSpec(image_path=path, brightness=-60)))
    light = core.to_bitmap(core.render(core.LabelSpec(image_path=path, brightness=60)))
    assert sum(_values(light)) > sum(_values(dark))  # more white dots when brightened


def test_transparent_areas_print_white_not_black(tmp_path):
    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))  # fully transparent, black underneath
    img.paste((0, 0, 0, 255), (5, 5, 10, 10))  # one opaque black square
    out = imaging.load_gray(_save(tmp_path, img))
    assert out.getpixel((0, 0)) == 255 and out.getpixel((7, 7)) == 0


def test_exif_orientation_is_respected(tmp_path):
    img = Image.new("L", (40, 20), 255)
    img.paste(0, (0, 0, 10, 20))  # black bar on the left
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 clockwise to view": the stored picture is lying on its side
    path = _save(tmp_path, img, "photo.jpg", exif=exif)
    out = imaging.load_gray(path)
    assert out.size == (20, 40)  # turned upright




def _asym(tmp_path):
    """Black block top-left, light-grey bottom-right: easy to tell flipped from not."""
    img = Image.new("L", (80, 40), 255)
    img.paste(0, (0, 0, 20, 10))
    img.paste(200, (60, 30, 80, 40))
    return _save(tmp_path, img)


def test_mirror_flip_and_invert(tmp_path):
    path = _asym(tmp_path)
    base = imaging.process(core.LabelSpec(image_path=path, threshold=100))
    w, h = base.size
    assert base.getpixel((2, 2)) == 0 and base.getpixel((w - 3, h - 3)) == 255  # light grey is above the cutoff
    mirrored = imaging.process(core.LabelSpec(image_path=path, threshold=100, mirror=True))
    assert mirrored.getpixel((w - 3, 2)) == 0 and mirrored.getpixel((2, 2)) == 255
    flipped = imaging.process(core.LabelSpec(image_path=path, threshold=100, flip=True))
    assert flipped.getpixel((2, h - 3)) == 0 and flipped.getpixel((2, 2)) == 255
    inverted = imaging.process(core.LabelSpec(image_path=path, threshold=100, invert=True))
    assert inverted.getpixel((2, 2)) == 255 and inverted.getpixel((w - 3, h - 3)) == 0
    both = imaging.process(core.LabelSpec(image_path=path, threshold=100, mirror=True, flip=True))
    assert both.getpixel((w - 3, h - 3)) == 0


@pytest.mark.parametrize("dither", ["floyd", "bayer4", "bayer8"])
def test_pixelate_makes_whole_blocks_and_keeps_the_size(tmp_path, dither):
    path = _save(tmp_path, _gradient(200, 100))
    block = 5
    out = imaging.process(core.LabelSpec(image_path=path, pixelate=block, dither=dither))
    plain = imaging.process(core.LabelSpec(image_path=path, dither=dither))
    assert out.size == plain.size
    assert set(_values(out)) <= {0, 255}  # dithered at the low resolution, so already dots
    for by in range(0, out.height - block, block):
        for bx in range(0, out.width - block, block):
            tile = out.crop((bx, by, bx + block, by + block))
            assert len(set(_values(tile))) == 1, (bx, by)  # every block is one solid colour


def test_pixelate_keeps_the_dither_pattern_chunky(tmp_path):
    path = _save(tmp_path, Image.new("L", (96, 96), 128))
    out = imaging.process(core.LabelSpec(image_path=path, pixelate=3, dither="bayer4"))
    # one pattern period is 4 blocks of 3 dots = 12 dots, not 4
    assert out.crop((0, 0, 12, 12)).tobytes() == out.crop((12, 12, 24, 24)).tobytes()
    assert out.crop((0, 0, 4, 4)).tobytes() != out.crop((4, 4, 8, 8)).tobytes()


def test_pixelate_of_one_changes_nothing(tmp_path):
    path = _save(tmp_path, _gradient())
    assert imaging.process(core.LabelSpec(image_path=path, pixelate=1)).tobytes() == \
        imaging.process(core.LabelSpec(image_path=path)).tobytes()




def test_decoded_photo_is_cached_but_an_edited_file_is_read_again(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("L", (40, 40), 0).save(path)
    imaging._decode.cache_clear()
    first = imaging.load_gray(str(path))
    assert imaging.load_gray(str(path)) is first and imaging._decode.cache_info().hits >= 1  # no second decode

    Image.new("L", (40, 40), 255).save(path)  # same path, new content (and a new modification time)
    import os
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    again = imaging.load_gray(str(path))
    assert again is not first and again.getpixel((5, 5)) == 255


def test_processing_never_modifies_the_cached_picture(tmp_path):
    path = _save(tmp_path, _gradient())
    before = imaging.load_gray(path).tobytes()
    for kw in ({"invert": True}, {"mirror": True, "flip": True}, {"threshold": 100}, {"pixelate": 4}, {"gamma": 2.0}):
        imaging.process(core.LabelSpec(image_path=path, **kw))
    assert imaging.load_gray(path).tobytes() == before


def test_a_missing_file_still_raises_not_a_cached_ghost(tmp_path):
    import pytest as _pytest

    with _pytest.raises(FileNotFoundError):
        imaging.load_gray(str(tmp_path / "nope.png"))


def _picture(tmp_path, name="p.png", fmt="PNG", color=(10, 200, 30)):
    path = tmp_path / name
    Image.new("RGB", (40, 30), color).save(path, format=fmt)
    return path


def test_adopt_gives_a_picture_a_stable_home_that_remembers_its_name(tmp_path):
    first = imaging.adopt(_picture(tmp_path), "holiday.png")
    again = imaging.adopt(_picture(tmp_path, "copy.png"), "holiday.png")  # the same picture, chosen again
    other = imaging.adopt(_picture(tmp_path, "o.png", color=(1, 2, 3)), "holiday.png")  # another picture, the same name
    assert first == again != other
    assert Path(first).parent == imaging.pictures_dir() and Path(first).suffix == ".png"
    assert Path(first).name.endswith("-holiday.png")  # the name survives into the file, so a saved label can show it
    assert Image.open(first).size == (40, 30)
    assert not list(imaging.pictures_dir().glob("*.part"))


def test_adopt_makes_an_unnamed_or_odd_name_safe(tmp_path):
    assert Path(imaging.adopt(_picture(tmp_path), "")).name.count("-") == 0  # a paste has no name: the hash alone
    odd = Path(imaging.adopt(_picture(tmp_path), "../../etc/pass wd?.png"))
    assert odd.parent == imaging.pictures_dir() and "/" not in odd.name and "?" not in odd.name


@pytest.mark.parametrize("fmt, suffix", [("PNG", ".png"), ("JPEG", ".jpg"), ("BMP", ".bmp"), ("GIF", ".gif"), ("WEBP", ".webp")])
def test_adopt_names_the_file_after_what_it_really_is(tmp_path, fmt, suffix):
    path = imaging.adopt(_picture(tmp_path, "whatever.dat", fmt), "whatever.dat")  # the name's suffix doesn't matter
    assert Path(path).suffix == suffix
    assert core.render(core.LabelSpec(image_path=path)).size == (core.W, core.H)  # and it renders


def test_adopt_refuses_what_is_not_a_picture_with_a_sentence(tmp_path):
    text = tmp_path / "notes.png"
    text.write_text("hello")
    with pytest.raises(ValueError, match="notes.png isn't a picture"):
        imaging.adopt(text, "notes.png")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="That file isn't a picture"):
        imaging.adopt(empty)


def test_adopt_refuses_unsupported_picture_formats(tmp_path):
    path = tmp_path / "x.tif"
    Image.new("RGB", (8, 8)).save(path, format="TIFF")
    with pytest.raises(ValueError, match="TIFF picture"):
        imaging.adopt(path, "x.tif")


def test_adopt_refuses_huge_files(tmp_path, monkeypatch):
    monkeypatch.setattr(imaging, "MAX_PICTURE_BYTES", 100)
    path = tmp_path / "big.png"
    Image.effect_noise((64, 64), 100).convert("RGB").save(path)
    with pytest.raises(ValueError, match="MB"):
        imaging.adopt(path, "big.png")


def test_atkinson_is_pure_black_and_white_and_crisper_than_floyd_steinberg():
    from PIL import Image

    ramp = Image.new("L", (256, 64))
    ramp.putdata([x for _ in range(64) for x in range(256)])  # black to white, left to right
    out = imaging.atkinson_dither(ramp)
    assert set(out.getdata()) == {0, 255} and out.size == ramp.size
    dark, light = out.crop((0, 0, 24, 64)), out.crop((232, 0, 256, 64))
    assert dark.histogram()[0] > 0.9 * 24 * 64  # shadows block up solid
    assert light.histogram()[255] > 0.9 * 24 * 64  # and highlights blow out to clean white
    mid = out.crop((120, 0, 136, 64))
    assert 0.35 < mid.histogram()[255] / (16 * 64) < 0.65  # the mid-tones stay a mix
    assert imaging.atkinson_dither(ramp).tobytes() == out.tobytes()  # deterministic: the browser must match


def test_atkinson_is_a_choice_that_reaches_the_label(tmp_path):
    from PIL import Image

    from dotlab import core
    from dotlab.spec import LabelSpec

    path = tmp_path / "ramp.png"
    Image.linear_gradient("L").resize((200, 100)).save(path)
    floyd = core.render(LabelSpec(image_path=str(path)))
    atkinson = core.render(LabelSpec(image_path=str(path), dither="atkinson"))
    assert floyd.tobytes() != atkinson.tobytes()
    assert atkinson.crop((0, 0, 384, 224)).getcolors() and {c for _, c in atkinson.crop((0, 0, 384, 224)).getcolors()} <= {0, 255}
