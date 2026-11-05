"""What an installed copy needs: every non-code file under the package is listed in package-data."""
import ast
import fnmatch
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "dotlab"


def _package_data_patterns() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"\[tool\.setuptools\.package-data\]\s*dotlab\s*=\s*(\[.*?\])", text, re.S)
    assert match, "pyproject.toml has no package-data for dotlab"
    return ast.literal_eval(match.group(1))


def test_package_data_covers_every_asset_and_font():
    """A wheel only contains what package-data lists. The editable dev install hid a wheel with no icons or
    arrows, so every non-code file under the package must match a pattern."""
    patterns = _package_data_patterns()
    for path in PACKAGE.rglob("*"):
        rel = path.relative_to(PACKAGE).as_posix()
        if path.is_dir() or path.suffix in {".py", ".pyc"} or "__pycache__" in rel:
            continue
        assert any(fnmatch.fnmatch(rel, pattern) for pattern in patterns), f"{rel} would be missing from the wheel"

