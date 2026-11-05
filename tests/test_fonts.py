import pytest
from PIL import ImageFont

from dotlab import core, fonts, render

JA_SAMPLE = "日本語 ひらがな カタカナ ｱｲｳ"


@pytest.mark.parametrize("font", fonts.BUNDLED, ids=lambda f: f.family)
def test_bundled_font_files_load_and_are_licensed(font):
    for filename in font.files.values():
        path = fonts.FONT_DIR / filename
        assert path.exists(), path
        ImageFont.truetype(str(path), 20)  # parses
    assert (fonts.FONT_DIR / "LICENSES" / font.license_file).exists()


@pytest.mark.parametrize("font", fonts.BUNDLED, ids=lambda f: f.family)
def test_bundled_families_resolve_to_bundled_files(font):
    for bold in (False, True):
        for italic in (False, True):
            path, _ = core.font_path(font.family, bold, italic)
            assert path.startswith(str(fonts.FONT_DIR)), path


def test_italic_degrades_to_synthetic_when_font_has_no_italic():
    assert core.font_path("Comic Neue", False, True)[1] is True  # real italic shipped
    assert core.font_path("Orbitron", False, True)[1] is False  # renderer shears it instead


@pytest.mark.parametrize("font", fonts.BUNDLED, ids=lambda f: f.family)
def test_ja_flag_matches_actual_coverage(font):
    path, _ = font.pick(False, False)
    assert all(render.covers(path, c) for c in "日ひカｱ") == font.ja


@pytest.mark.parametrize("font", fonts.BUNDLED, ids=lambda f: f.family)
def test_every_bundled_font_can_print_japanese(font):
    # either the font has the glyphs itself or the fallback supplies them: nothing falls through to a missing box
    path, _ = font.pick(True, False)
    fs = render._FontSet(path, 40, True)
    for ch in JA_SAMPLE.replace(" ", ""):
        chosen = fs.pick(ch)
        owner = path if chosen is fs.primary else fs._fallback_path
        assert render.covers(owner, ch), (font.family, ch)
    img = core.render(core.LabelSpec(text=JA_SAMPLE, font=font.family))
    assert img.point(lambda v: 255 - v).getbbox() is not None


def test_fallback_is_used_only_for_missing_glyphs():
    path, _ = core.font_path("Orbitron", True)
    fs = render._FontSet(path, 40, True)
    assert fs.pick("A") is fs.primary and fs.pick(" ") is fs.primary
    assert fs.pick("日") is not fs.primary
    ja_path, _ = core.font_path("DotGothic16", False)
    own = render._FontSet(ja_path, 40, False)
    assert own.pick("日") is own.primary  # a Japanese font keeps its own style


def test_mixed_script_text_shares_a_baseline():
    # a Latin run and a Japanese run on one line must sit on the same baseline
    path, _ = core.font_path("Orbitron", True)
    fs = render._FontSet(path, 40, True)
    probe = render.ImageDraw.Draw(render.Image.new("L", (1, 1)))
    placed, _, _, _ = render._layout(probe, "ABC日本語DEF", fs, "left", 8)
    assert len(placed) == 3 and len({baseline for _, _, _, baseline, _ in placed}) == 1
    xs = [x for _, _, x, _, _ in placed]
    assert xs == sorted(xs) and xs[0] == 0


@pytest.mark.parametrize("effect", core.EFFECTS)
def test_japanese_with_every_effect_stays_in_sticker(effect):
    spec = core.LabelSpec(text="日本語\nサイバー", font="Orbitron", effect=effect, background="scanlines", border=True)
    img = core.render(spec)
    assert img.crop((0, core.SH, core.W, core.H)).getextrema() == (255, 255)


def test_unknown_character_does_not_crash():
    core.render(core.LabelSpec(text="\U0001F680 rocket \ue000", font="Orbitron"))


def test_categories_cover_every_bundled_font_once():
    listed = [name for _, names in fonts.categories() for name in names]
    assert sorted(listed) == sorted(f.family for f in fonts.BUNDLED)


def test_nothing_depends_on_system_fonts(monkeypatch):
    # Windows/macOS have no fontconfig: resolution must come from the bundled files alone
    monkeypatch.setattr(render, "HAS_FONTCONFIG", False)
    render.font_path.cache_clear()
    render.list_font_families.cache_clear()
    try:
        path, _ = core.font_path("Some Font Nobody Has", True)
        assert path.startswith(str(fonts.FONT_DIR))
        assert core.list_font_families() == []
        img = core.render(core.LabelSpec(text="Hello 日本", font="Some Font Nobody Has"))
        assert img.point(lambda v: 255 - v).getbbox() is not None
    finally:  # don't leak the fontconfig-less results into other tests
        render.font_path.cache_clear()
        render.list_font_families.cache_clear()
