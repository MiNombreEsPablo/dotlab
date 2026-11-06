"""Serve the web UI for development: `python src/dotlab/web/dev_server.py [port]`, then open http://localhost:8000.

The URL layout is the one the published site will have: the files of web/ as they are, plus
  /engine/<module>.py        the engine's Python sources, straight from src/dotlab
  /engine/manifest.json      what the browser has to load (Pyodide version, packages, modules)
  /fonts/<file>.ttf          the bundled fonts, fetched on demand
  /assets/<file>.png         the few images the page uses (the banner's mark)
  /licenses.txt              the project's licence and every font's, made on the fly
so the browser build can be built later by copying exactly these files.
"""
from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

WEB = Path(__file__).resolve().parent
PACKAGE = WEB.parent  # src/dotlab: the web UI lives inside the package, so every install ships it
FONTS = PACKAGE / "fonts"

# api and what it imports, no more: the browser must not need USB or anything else
ENGINE_MODULES = ["__init__.py", "spec.py", "render.py", "imaging.py", "doodle.py", "stickers.py", "sticker_tiles.py", "fonts.py",
                  "protocol.py", "bluetooth.py", "form.py", "composition.py", "presets.py", "about.py", "api.py"]
ASSETS = PACKAGE / "assets"
SITE_ASSETS = ["icon-mark.png"]  # what the page uses (the banner's mark)
PYODIDE = "314.0.7"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/x-python", ".py")
mimetypes.add_type("font/ttf", ".ttf")


def licenses_text() -> str:
    """The project's licence and the licence of every bundled font family, for the site to publish with them."""
    licence = PACKAGE.parent.parent / "LICENSE"  # in a checkout; an installed copy keeps it in its dist-info instead
    parts = ["Dotlab is MIT licensed:\n\n" + (licence.read_text(encoding="utf-8").strip() if licence.is_file()
                                                          else "see https://github.com/MiNombreEsPablo/dotlab/blob/main/LICENSE")]
    folder = FONTS / "LICENSES"
    parts.append("The bundled fonts are open source; each family's licence follows.")
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        title = path.name.replace("LICENSE.", "", 1).replace("-", " ")
        parts.append(f"{'=' * 78}\n{title}\n{'=' * 78}\n{path.read_text(encoding='utf-8', errors='replace').strip()}")
    return "\n\n".join(parts) + "\n"


def manifest() -> dict:
    return {
        "pyodide": PYODIDE,
        "packages": ["Pillow", "fonttools", "micropip"],  # Pyodide's own builds
        "pypi": ["qrcode"],  # pure Python, installed from PyPI at start-up (to be hosted with the site later)
        "python": ENGINE_MODULES,
        "fonts": sorted(p.name for p in FONTS.glob("*.ttf")),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(path.read_bytes(), ctype if not ctype.startswith("text/") else ctype + "; charset=utf-8")

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/licenses.txt":
            return self._send(licenses_text().encode("utf-8"), "text/plain; charset=utf-8")
        if path == "/engine/manifest.json":
            return self._send(json.dumps(manifest()).encode(), "application/json")
        if path.startswith("/engine/") and path[len("/engine/"):] in ENGINE_MODULES:
            return self._file(PACKAGE / path[len("/engine/"):])
        if path.startswith("/fonts/") and path[len("/fonts/"):] in manifest()["fonts"]:
            return self._file(FONTS / path[len("/fonts/"):])
        if path.startswith("/assets/") and path[len("/assets/"):] in SITE_ASSETS:
            return self._file(ASSETS / path[len("/assets/"):])
        target = (WEB / (path.lstrip("/") or "index.html")).resolve()
        if target.is_file() and WEB in target.parents and target.suffix != ".py":
            return self._file(target)
        self._send(b"not found", "text/plain", 404)

    def log_message(self, *args) -> None:
        pass


def make_server(port: int = 8000, bind: str = "127.0.0.1") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((bind, port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"web UI on http://localhost:{port}  (Ctrl+C to stop)")
    make_server(port).serve_forever()
