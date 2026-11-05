"""The web UI's looks are data (web/themes.css); these checks keep that data complete and in step with the page."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "src" / "dotlab" / "web"
THEMES_CSS = (WEB / "themes.css").read_text(encoding="utf-8")
STYLE_CSS = (WEB / "style.css").read_text(encoding="utf-8")


def _blocks() -> dict[str, set[str]]:
    """{look: the custom properties its block defines}; the System look's dark variant is 'system-dark'."""
    blocks, current = {}, None
    for line in THEMES_CSS.splitlines():
        start = re.match(r'\s*:root[^{]*\{\s*$', line)
        if start:
            named = re.search(r'data-theme="([a-z0-9-]+)"', line)
            name = named.group(1) if named else "y2k-blue"
            if name == "system" and line.startswith("  "):  # inside the @media (prefers-color-scheme: dark) block
                name = "system-dark"
            current = blocks.setdefault(name, set())
        elif current is not None and re.match(r"\s*}\s*$", line):
            current = None
        elif current is not None:
            token = re.match(r"\s*(--[a-z0-9-]+):", line)
            if token:
                current.add(token.group(1))
    return blocks


def test_every_look_is_there():
    assert set(_blocks()) == {"y2k-blue", "y2k-pink", "gunmetal", "handheld", "system", "system-dark"}


def test_the_looks_that_stand_alone_define_every_token_so_nothing_leaks_in_from_the_candy_plastic():
    blocks = _blocks()
    for look in ("gunmetal", "handheld", "system"):
        missing = blocks["y2k-blue"] - blocks[look]
        assert not missing, f"{look} leaves {sorted(missing)} to be inherited from Y2K Blue"


def test_pink_and_the_dark_system_look_only_override_tokens_that_exist():
    blocks = _blocks()
    assert blocks["y2k-pink"] <= blocks["y2k-blue"], sorted(blocks["y2k-pink"] - blocks["y2k-blue"])
    assert blocks["system-dark"] <= blocks["system"], sorted(blocks["system-dark"] - blocks["system"])


def test_the_stylesheet_only_uses_tokens_that_are_defined():
    defined = _blocks()["y2k-blue"] | set(re.findall(r"(--[a-z0-9-]+)\s*:", STYLE_CSS))  # (--fill is set per slider)
    used = set(re.findall(r"var\((--[a-z0-9-]+)", STYLE_CSS))
    assert not (used - defined), sorted(used - defined)


def test_no_colour_is_written_in_a_rule():
    """style.css says where things go; the colours live in the themes. (Allowed: white for the sticker tiles and the
    candy gloss, which is white by nature.)"""
    rules = re.sub(r"/\*.*?\*/", "", STYLE_CSS, flags=re.S)
    colours = re.findall(r"#[0-9a-fA-F]{3,8}\b", rules)
    assert sorted(set(colours)) == ["#fff"], sorted(set(colours))


def test_the_picker_lists_exactly_the_looks_there_are():
    keys = re.findall(r'\["([a-z0-9-]+)", "[^"]+"\]', (WEB / "themes.js").read_text(encoding="utf-8").split("export const DEFAULT_THEME")[0])
    assert keys == ["y2k-blue", "y2k-pink", "gunmetal", "handheld", "system"]
    assert set(keys) == set(_blocks()) - {"system-dark"}


def test_the_page_loads_the_themes_and_restores_the_saved_look_before_painting():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert html.index("themes.css") < html.index("style.css")
    assert 'id="menubar"' in html and 'id="theme"' not in html  # the looks are in the View menu now
    assert html.index("localStorage.getItem(\"dotlab:theme\")") < html.index("<body>")  # set before the first paint


def test_the_fonts_the_looks_name_are_bundled_and_served():
    from importlib.util import module_from_spec, spec_from_file_location

    served = spec_from_file_location("dev_server", WEB / "dev_server.py")
    module = module_from_spec(served)
    served.loader.exec_module(module)
    fonts = set(module.manifest()["fonts"])
    for name in re.findall(r'src: url\("fonts/([^"]+)"\)', THEMES_CSS):
        assert name.replace("%5B", "[").replace("%5D", "]") in fonts, name
