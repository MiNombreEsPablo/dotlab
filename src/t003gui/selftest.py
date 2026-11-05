"""`t003-gui --selftest`: prove an installed or frozen build is complete, without a printer or a display.

CI runs this against every packaged app, so a missing font, icon or libusb in a bundle fails the build.
"""
from __future__ import annotations

import os
import sys


def _report(text: str, *, error: bool) -> None:
    print(text, file=sys.stderr if error else sys.stdout)
    log = os.environ.get("T003_SELFTEST_LOG")  # windowed Windows builds have no console, so CI reads this file
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def run(web: bool = False) -> int:
    """`web`: also check what the web window needs (the page, the engine's sources, the window toolkit)."""
    from . import core, fonts
    from .web import dev_server

    problems: list[str] = []
    for font in fonts.BUNDLED:
        for filename in font.files.values():
            if not (fonts.FONT_DIR / filename).exists():
                problems.append(f"missing font file {filename}")
        if not (fonts.FONT_DIR / "LICENSES" / font.license_file).exists():
            problems.append(f"missing licence {font.license_file}")
    for asset in ("icon-256.png", "icon-mark.png"):
        if not (dev_server.ASSETS / asset).exists():
            problems.append(f"missing asset {asset}")

    if web:
        for name in ("index.html", "main.js", "style.css", "themes.css", "engine/pyodide.js", "printer/bridge.js"):
            if not (dev_server.WEB / name).exists():
                problems.append(f"missing web file {name}")
        try:
            import webview  # noqa: F401
        except ImportError as e:
            problems.append(f"the window toolkit (pywebview) is missing: {e}")
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            try:  # the window toolkit really loads (.NET and WebView2's wrapper): importing webview alone doesn't try
                import webview.platforms.winforms  # noqa: F401
            except Exception as e:  # not only ImportError: a .NET failure is a RuntimeError
                problems.append(f"the Windows window toolkit doesn't load: {e}")
        if not sys.platform.startswith("linux"):
            try:  # the Bluetooth backend (WinRT, CoreBluetooth) is picked by name at run time: prove it was bundled
                from bleak import BleakClient, BleakScanner  # noqa: F401
            except ImportError as e:
                problems.append(f"Bluetooth printing (bleak) is missing: {e}")
        if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
            try:  # loads Chromium and the system libraries it needs, so a missing one fails here and not on a user's screen
                from PySide6 import QtWebEngineWidgets  # noqa: F401
            except ImportError as e:
                problems.append(f"QtWebEngine doesn't load: {e}")

    spec = core.LabelSpec(text="日本語 TEST", font="Orbitron", effect="neon", background="circuit", qr="t003")
    if core.render(spec).point(lambda v: 255 - v).getbbox() is None:
        problems.append("rendering produced a blank label")
    if not core.tspl(spec).startswith(b"SIZE "):
        problems.append("TSPL payload is malformed")
    backend = core._backend()
    if backend is None:
        problems.append("no libusb backend found: " + (core.backend_problem() or "pyusb found no libusb"))
    printer = core.printer_presence() if backend is not None else "not checked"  # informational: CI has no printer

    if problems:
        _report("selftest FAILED:\n  " + "\n  ".join(problems), error=True)
        return 1
    _report(
        f"selftest ok: {len(fonts.BUNDLED)} bundled font families, Japanese render, TSPL, libusb; printer {printer}",
        error=False,
    )
    return 0
