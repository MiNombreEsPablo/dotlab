from PIL import Image

from dotlab import core


def test_render_size_and_gap_stays_white():
    img = core.render(core.LabelSpec(text="hello", qr="https://example.com", border=True))
    assert img.size == (core.W, core.H)
    gap = img.crop((0, core.SH, core.W, core.H))
    assert gap.getextrema() == (255, 255)


def test_text_is_black_on_white():
    img = core.render(core.LabelSpec(text="X"))
    assert img.getextrema() == (0, 255)


def test_tspl_payload_layout():
    payload = core.tspl(core.LabelSpec(text="x", copies=3, density=9))
    assert payload.startswith(b"SIZE 72 mm,30 mm\r\n")
    assert b"DENSITY 9\r\n" in payload
    head, _, rest = payload.partition(b"BITMAP 0,0,48,240,0,")
    assert rest.endswith(b"\r\nPRINT 3,1\r\n")
    assert len(rest) == 48 * 240 + len(b"\r\nPRINT 3,1\r\n")


def test_image_threshold_removes_light_colours(tmp_path):
    path = tmp_path / "yellow.png"
    Image.new("RGB", (100, 100), (255, 230, 0)).save(path)
    img = core.render(core.LabelSpec(image_path=str(path), threshold=160))
    assert img.getextrema() == (255, 255)


def _ink_extent(img):
    """(min_x, max_x) of black pixels."""
    inverted = img.point(lambda v: 255 - v)
    left, _, right, _ = inverted.getbbox()
    return left, right - 1


def test_alignment_moves_text_block():
    left = _ink_extent(core.render(core.LabelSpec(text="Hi", align="left")))
    centre = _ink_extent(core.render(core.LabelSpec(text="Hi", align="center")))
    right = _ink_extent(core.render(core.LabelSpec(text="Hi", align="right")))
    assert left[0] <= core.MARGIN + 2
    assert right[1] >= core.W - core.MARGIN - 2
    assert left[0] < centre[0] < right[0]


def test_multiline_lines_align_within_block():
    # short line under a long one: left-aligned starts at the block's left edge, right-aligned ends at its right edge
    spec = core.LabelSpec(text="WWWWWWWW\ni", align="left")
    left = core.render(spec).crop((0, core.SH // 2 + 20, core.W, core.SH))
    spec.align = "right"
    right = core.render(spec).crop((0, core.SH // 2 + 20, core.W, core.SH))
    assert _ink_extent(left)[0] < _ink_extent(right)[0]


def test_font_choice_changes_output_and_resolves():
    import os
    bold, _ = core.font_path("DejaVu Sans", True)
    regular, _ = core.font_path("DejaVu Sans", False)
    assert os.path.exists(bold) and bold != regular
    a = core.render(core.LabelSpec(text="Hello", font="DejaVu Sans"))
    b = core.render(core.LabelSpec(text="Hello", font="Noto Sans Mono", bold=False))
    assert a.tobytes() != b.tobytes()


def test_unknown_font_and_bad_align_do_not_crash():
    core.render(core.LabelSpec(text="x", font="NoSuchFontXYZ", align="sideways"))


def test_version_is_single_sourced():
    import re
    from pathlib import Path

    import dotlab

    text = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert re.fullmatch(r"\d+\.\d+\.\d+(rc\d+)?", dotlab.__version__)  # rcN: a pre-release (the release workflow marks it so)
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    assert 'dynamic = ["version"]' in project and not re.search(r"^version\s*=", project, re.M)
    assert 'version = {attr = "dotlab.__version__"}' in text


def test_label_bitmap_is_the_sticker_only_and_export_uses_it(tmp_path):
    spec = core.LabelSpec(text="Hi")
    one, four = core.label_bitmap(spec), core.label_bitmap(spec, scale=4)
    assert (one.size, one.mode) == ((core.W, core.SH), "1") and four.size == (core.W * 4, core.SH * 4)
    out = tmp_path / "x.png"
    core.export_png(spec, out)
    assert Image.open(out).tobytes() == one.tobytes()


def test_density_and_copies_are_clamped_in_the_payload():
    payload = core.tspl(core.LabelSpec(text="x", density=99, copies=0))
    assert b"DENSITY 15" in payload and payload.endswith(b"PRINT 1,1\r\n")
