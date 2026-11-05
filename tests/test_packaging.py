"""What an installed copy needs, and that the command-line tool works with only the core dependencies."""
import ast
import fnmatch
import re
import subprocess
import sys
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


def _run_core_only(code: str) -> subprocess.CompletedProcess:
    blocker = "import sys; "  # any import of pywebview now fails
    return subprocess.run([sys.executable, "-c", blocker + code], capture_output=True, text=True, cwd=ROOT, timeout=60)


def test_core_and_cli_work_without_the_window_extras(tmp_path):
    out = tmp_path / "label.png"
    result = _run_core_only(
        "from dotlab import cli, core, composition, presets, imaging; "
        f"cli.main(['Hello', '--preview', {str(out)!r}]); "
        "print('ok')"
    )
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr
    assert out.exists()

