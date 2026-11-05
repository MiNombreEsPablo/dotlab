"""The `t003-gui` command: open the web UI in a native window."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MISSING_WEBVIEW = (
    "The T003 Label Studio window needs pywebview, which isn't installed.\n"
    "  pip install 't003-label-gui[web]'      (Linux without WebKitGTK: 't003-label-gui[web-qt]')\n"
    "The command-line tool works without it: t003-print --help"
)
NO_TOOLKIT = (
    "pywebview found no window toolkit. On Linux install WebKitGTK and PyGObject from your distribution\n"
    "(Arch: webkit2gtk-4.1 python-gobject; Debian/Ubuntu: gir1.2-webkit2-4.1 python3-gi), or use QtWebEngine:\n"
    "  pip install 't003-label-gui[web-qt]'"
)


class ShellUnavailable(Exception):
    """The web window can't start here: pywebview or its window toolkit is missing."""


def run_shell() -> None:
    """The web UI in a native window (src/t003gui/web/desktop.py); raises ShellUnavailable when it can't open."""
    web = Path(__file__).resolve().parent / "web"
    sys.path.insert(0, str(web))  # the shell and the dev server import each other as plain modules
    try:
        import desktop
        desktop.main()
    except ImportError as e:
        if (e.name or "").split(".")[0] != "webview":
            raise
        raise ShellUnavailable(MISSING_WEBVIEW) from e
    except Exception as e:
        if type(e).__name__ == "WebViewException":  # pywebview's own: no toolkit it can use
            raise ShellUnavailable(f"{NO_TOOLKIT}\n({e})") from e
        raise


def web_shell() -> None:
    try:
        run_shell()
    except ShellUnavailable as e:
        sys.exit(str(e))


def unblock_downloaded_files() -> int:
    """Windows marks the files of a downloaded zip "from the internet", and .NET won't load code carrying that mark (the
    window toolkit needs it). Clear the mark on the app's own files so a freshly extracted download starts; returns how
    many files had one. T003_NO_UNBLOCK=1 skips it (for testing)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False) or os.environ.get("T003_NO_UNBLOCK"):
        return 0
    cleared = 0
    for path in Path(sys.executable).parent.rglob("*"):
        if path.suffix.lower() in (".dll", ".pyd", ".exe"):
            try:
                os.remove(f"{path}:Zone.Identifier")
                cleared += 1
            except OSError:
                pass  # no mark on this file (the usual case), or not ours to change
    return cleared


def shell_main() -> None:
    """The entry of the packaged app: the window, or `--selftest` to prove the bundle is complete."""
    from . import applog

    applog.start()  # a windowed build has no console: whatever goes wrong is in this file
    cleared = unblock_downloaded_files()
    if cleared:
        import logging

        logging.getLogger("t003gui").info("cleared the downloaded-from-the-internet mark on %d files", cleared)
    if "--selftest" in sys.argv:
        from .selftest import run

        sys.exit(run(web=True))
    try:
        run_shell()
    except ShellUnavailable as e:
        applog.record(e)
        sys.exit(f"{e}\n\nLog: {applog.log_path()}")
    except Exception as e:
        applog.record(e)
        raise SystemExit(f"T003 Label Studio couldn't start: {e}\n\nLog: {applog.log_path()}") from e


def main() -> None:
    if "--selftest" in sys.argv:  # an installed copy checks itself: fonts, licences, assets, libusb, a render
        from .selftest import run

        sys.exit(run())
    web_shell()  # `--web` (what the flag was called before the window became the default) is simply ignored
