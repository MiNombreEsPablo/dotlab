"""The web UI's dev server and the list of engine modules the browser downloads."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "dotlab"


def _dev_server():
    spec = importlib.util.spec_from_file_location("dev_server", ROOT / "src" / "dotlab" / "web" / "dev_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_lists_real_files():
    manifest = _dev_server().manifest()
    assert all((PACKAGE / name).is_file() for name in manifest["python"])
    assert "DejaVuSans.ttf" in manifest["fonts"] and "Orbitron[wght].ttf" in manifest["fonts"]
    assert manifest["pyodide"] and "Pillow" in manifest["packages"]


def test_the_browser_engine_imports_only_the_modules_it_downloads():
    """The browser fetches exactly `ENGINE_MODULES`. If `api` ever imports another module of the package (core, cli or
    anything else) the browser build breaks, so block every module that is not on the list."""
    shipped = {name[:-3] for name in _dev_server().ENGINE_MODULES}
    others = sorted(p.stem for p in PACKAGE.glob("*.py"))
    blocked = [f"dotlab.{stem}" for stem in others if stem not in shipped]
    assert "dotlab.core" in blocked and "dotlab.cli" in blocked  # the test is only as good as this list
    code = (
        "import sys\n"
        + "".join(f"sys.modules[{name!r}] = None\n" for name in blocked)
        + "from dotlab import api\n"
        "assert api.tspl_bytes({'text': 'x'}).startswith(b'SIZE ')\n"
        "assert len(api.preview_pixels({'text': 'x'})) > 0 and api.options()\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert result.returncode == 0 and "ok" in result.stdout, result.stderr


def test_the_server_serves_the_page_the_engine_and_fonts_but_not_arbitrary_files():
    import threading
    import urllib.error
    import urllib.request

    module = _dev_server()
    server = module.make_server(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path, timeout=10) as response:
                return response.status, response.headers.get("Content-Type", ""), response.read()
        except urllib.error.HTTPError as e:
            return e.code, "", b""

    try:
        assert get("/")[0] == 200 and b"Dotlab" in get("/")[2]
        assert get("/main.js")[1].startswith("text/javascript")
        assert get("/engine/api.py")[0] == 200 and get("/engine/core.py")[0] == 404  # only the shipped modules
        assert get("/fonts/DejaVuSans.ttf")[0] == 200 and get("/fonts/nope.ttf")[0] == 404
        assert get("/engine/manifest.json")[1] == "application/json"
        assert get("/files/browser.js")[0] == 200
        assert get("/licenses.txt")[0] == 200 and b"SIL OPEN FONT LICENSE" in get("/licenses.txt")[2].upper()
        assert get("/presets/local.js")[0] == 200
        assert get("/assets/icon-mark.png")[0] == 200 and get("/assets/icon-mark.png")[1] == "image/png"
        assert get("/assets/icon-256.png")[0] == 404  # only what the page uses
        assert get("/dev_server.py")[0] == 404  # python in web/ is never served
        assert get("/../pyproject.toml")[0] == 404 and get("/%2e%2e/pyproject.toml")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
