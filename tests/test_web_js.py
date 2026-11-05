"""The web UI's JavaScript that has no DOM (the doodle's drawing engine) is tested with Node's own test runner."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _node_major() -> int:
    node = shutil.which("node")
    if node is None:
        return 0
    out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()  # "v24.18.0"
    return int(out.lstrip("v").split(".")[0] or 0)


@pytest.mark.skipif(_node_major() < 22, reason="needs Node.js 22 or newer (it runs ES modules without a build step)")
def test_the_doodle_raster_passes_its_node_tests():
    result = subprocess.run(["node", "--test", "src/dotlab/web/test/*.test.js"], capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
