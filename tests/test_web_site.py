"""The static site that GitHub Pages serves is the dev server's layout written out as files (web/build_site.py)."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "src" / "dotlab" / "web"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, WEB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(WEB))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(WEB))
    return module


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "site"
    build_site = _load("build_site")
    return out, build_site.build(out, wheels=False), build_site


def test_the_site_has_the_page_the_engine_and_the_fonts(site):
    out, manifest, _ = site
    for name in ("index.html", "main.js", "style.css", "themes.css", "menus.js", ".nojekyll", "assets/icon-mark.png"):
        assert (out / name).is_file(), name
    assert all((out / "engine" / name).is_file() for name in manifest["python"])
    assert json.loads((out / "engine" / "manifest.json").read_text()) == manifest  # a file now, not a dynamic answer
    assert {p.name for p in (out / "fonts").glob("*.ttf")} == set(manifest["fonts"])


def test_every_bundled_font_has_its_licence_on_the_site(site):
    out, _, _ = site
    text = (out / "licenses.txt").read_text(encoding="utf-8")
    assert text.startswith("Dotlab is MIT licensed") and "Permission is hereby granted" in text
    from dotlab import fonts

    for family in fonts.BUNDLED:
        licence = (fonts.FONT_DIR / "LICENSES" / family.license_file)
        assert licence.is_file(), family.family
        assert licence.read_text(encoding="utf-8", errors="replace").strip()[:200] in text, family.family  # every text is in


def test_the_site_has_only_what_the_browser_needs(site):
    out, manifest, _ = site
    python = {p.relative_to(out).as_posix() for p in out.rglob("*.py")}
    assert python == {f"engine/{name}" for name in manifest["python"]}  # no dev server or build script
    for left_out in ("dev_server.py", "build_site.py", "test"):
        assert not (out / left_out).exists(), left_out
    assert not any("__pycache__" in p.parts or "node_modules" in p.parts for p in out.rglob("*"))


def test_the_site_never_refers_to_the_root_of_the_server(site):
    """A project site lives under /dotlab/, so a URL that starts with a slash would leave it."""
    out, _, _ = site
    pattern = re.compile(r"""(?:href|src)\s*=\s*["']/[^/]|url\(\s*["']?/[^/]|(?:fetch|import|Worker)\(\s*["'`]/[^/]""")
    for path in list(out.glob("*.html")) + list(out.glob("*.css")) + list(out.glob("**/*.js")):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.relative_to(out)


def test_building_never_writes_over_something(site, tmp_path):
    _, _, build_site = site
    (tmp_path / "keep.txt").write_text("mine")
    with pytest.raises(SystemExit, match="not empty"):
        build_site.build(tmp_path, wheels=False)
    assert (tmp_path / "keep.txt").read_text() == "mine"


def test_the_pinned_wheel_is_checked(site, tmp_path):
    _, _, build_site = site
    wheel = tmp_path / "w.whl"
    wheel.write_bytes(b"not the wheel")
    with pytest.raises(SystemExit, match="not the wheel"):
        build_site.verify_wheel(wheel, build_site.QRCODE_SHA256)
    assert len(build_site.QRCODE_SHA256) == 64 and build_site.QRCODE_WHEEL.startswith("qrcode-8.2-")
    assert build_site.QRCODE_REQUIREMENT == "qrcode==8.2"


def test_the_pin_names_one_version_in_all_three_places():
    """(Not compared with the qrcode installed here: CI's oldest-libraries job deliberately installs an old one.)"""
    build_site = _load("build_site")
    version = build_site.QRCODE_REQUIREMENT.split("==")[1]
    assert build_site.QRCODE_WHEEL == f"qrcode-{version}-py3-none-any.whl"


def test_the_workflow_deploys_only_when_the_repository_is_ready():
    text = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "vars.PAGES_ENABLED == 'true'" in text and "github.ref == 'refs/heads/main'" in text
    assert "pull_request" in text and "event_name != 'pull_request'" in text  # a pull request builds, never deploys
