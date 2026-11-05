<p align="center"><img src="packaging/icons/t003-label-gui-128.png" alt="T003 Label Studio icon" width="96"></p>

# T003 Label Studio

Design and print stickers on the **ORGBRO T003** USB thermal label printer, with a live preview of exactly what the
printer will burn. Text, QR codes and images, plus a pile of early-web and cyberpunk styling, and every font can print
Japanese (日本語).

## What this is

A fun, Y2K-flavoured label studio for cheap thermal printers: made by a hobbyist for the joy of it, and open to anyone
who likes the same corner of the internet. It aims to stay small and playful. A new feature should be **fun**, or
**small and useful**; heavier "serious label software" ideas (batch printing, databases, accounts) are tagged on the
roadmap and only happen if they stay simple and are fun to build. It's maintained as a hobby, best effort, and
nothing here is a promise. Kind issues and pull requests are welcome.

## Features

- **Live 1-bit preview** that is the same bitmap that gets printed (what you see is what you stick).
- **Text:** 23 bundled open-licence fonts in five groups (Cyber, Pixel, Early web, Display, Clean), bold/italic, size,
  left/centre/right and top/middle/bottom alignment. Latin-only fonts borrow kana and kanji from Zen Kaku Gothic New;
  DotGothic16, Yusei Magic, Dela Gothic One and Stick have their own Japanese.
- **Effects:** dithered shadow, outline, 3D WordArt, glitch, neon glow, scanline text.
- **Backgrounds:** checker, dots, stripes, dithered gradient, stars, graph paper, scanlines, circuit board, hex grid,
  synthwave sun, matrix rain, halftone. **Borders:** solid, double, dotted, checker, Win95 bevel, marquee lights,
  cyber panel, HUD brackets, ruler ticks. **Bars:** under-construction hazard stripes.
- **QR codes, images** (drag and drop or paste), copies, darkness, saved **presets**. **Image and text together:** put the
  picture left, right, above, below or behind the text (and QR code), with a size control. **Image tab:** Floyd–Steinberg,
  ordered (Bayer) crosshatch or hard-cutoff dithering; sliders with exact-value boxes for brightness, contrast, gamma and
  the cutoff (double-click a slider to reset it); pixelate for chunky handheld-camera dots; mirror, flip and invert.
  Transparent PNGs print on white and phone photos keep their orientation.
- **Menus:** File (open/save a composition, export an image, **Print, Ctrl+P**), Edit (paste a clipboard image, clear it,
  copy the label as an image with Ctrl+Shift+C), View (themes), Help.
- **Save and share:** File > Save/Open composition keeps a whole label in one `.t003label` file (the image is embedded, so
  it works on another machine; drop one on the window to open it, or `t003-print --file x.t003label`). File > Export
  image writes the exact 1-bit label as a PNG, at printed size or enlarged 4×.
- Themes (View > Theme): Y2K candy plastic in blue or pink, gunmetal with LCD-green text, a four-shade olive
  "handheld" look (which also tints the preview; prints stay black on white), or the plain platform look.
- Help menu: version, an About box (with a printer-found check) and a manual **Check for updates** that compares your
  version with the latest GitHub release. It only runs when you ask.
- A CLI with the same options: `t003-print "NEON\nNIGHTS" --effect neon --frame brackets`.

## Install

Downloads are on the [Releases](../../releases) page. Every build runs a self-test (fonts, licences, icons, a Japanese
render, libusb) in CI before it is published.

| OS | Get | Needs | Notes |
|---|---|---|---|
| **Linux** (x86-64) | `T003-Label-Studio-*-x86_64.AppImage` | glibc 2.28 or newer: Ubuntu 20.04+, Debian 10+, RHEL/Alma/Rocky 8+, Fedora, Arch and anything newer | `chmod +x` and run. The window is Chromium inside: it needs the usual desktop libraries (`libnss3`, `libxcb-cursor0`, `libxkbcommon-x11`, `libasound2`, and on Fedora `libwayland-server`), which almost every desktop already has. If it doesn't start, run it as `./T003-Label-Studio-*.AppImage --appimage-extract-and-run` (no FUSE needed). Install the udev rule below so you can use the printer without root. |
| **Windows** (x64) | `…-windows-x64.zip` | Windows 10 or 11 | Unzip and run `T003 Label Studio.exe`. libusb needs the printer bound to the **WinUSB** driver (e.g. with [Zadig](https://zadig.akeo.ie/)), which stops Windows' own printing to that device. |
| **macOS** (Apple silicon or Intel) | `…-macos-arm64.zip` or `…-macos-x86_64.zip` | macOS 12 or newer | The app is unsigned: right-click → Open the first time. |

Not covered by a download? See the pip install below: it works on anything with Python 3.9+ and USB, including
Linux on ARM (Raspberry Pi), older macOS and Python-capable systems we don't build for.

> **What is tested.** Printing: Linux with real hardware only. Every release build runs its self-test in CI, and the
> Linux AppImage is also self-tested in Ubuntu 20.04, Debian 12 and Fedora containers. The macOS minimum (12) and the
> Linux minimum (glibc 2.28) are measured on each build, and the build fails if a dependency raises them, so the
> systems named in the table are what the measurements say, not a list of everything tried. Printing from Windows
> and macOS hasn't been tried on a physical machine, and Windows on ARM should work through x64 emulation but is
> untested; reports welcome.

**Linux udev rule** (lets your user open the printer):
```
sudo cp packaging/70-t003-label-printer.rules /etc/udev/rules.d/
sudo udevadm control --reload   # then replug the printer
```

## With pip, on any system with Python 3.9+

```bash
pip install "t003-label-gui[web] @ git+https://github.com/MiNombreEsPablo/t003-label-gui"   # the desktop window and the CLI
pip install "t003-label-gui @ git+https://github.com/MiNombreEsPablo/t003-label-gui"        # only the CLI
```

This reaches older distros and Python versions than the downloads above. The command-line tool `t003-print` needs no
window toolkit, so it also runs on a Raspberry Pi, a server or
anything else with Python and USB; on platforms without a bundled libusb, install the system one (`apt install
libusb-1.0-0`). The window is `t003-gui`.

## From source

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'   # [dev] = pytest
.venv/bin/t003-gui          # the app
.venv/bin/t003-print --help # the CLI
.venv/bin/pytest            # tests, no printer needed
packaging/install.sh        # KDE/GNOME launcher, icons and a print-label shortcut
```

## How it works

The T003 speaks TSPL over a plain USB printer interface. The app renders a 384×224 dot label (58 mm paper, 203 dpi,
28 mm stickers), sends it as a TSPL bitmap with pyusb/libusb, and needs no CUPS or kernel driver. See
[AGENTS.md](AGENTS.md) for the hardware facts and the code layout.

The T003 also has Bluetooth (classic serial and BLE) and takes the same TSPL over it. The app and CLI can print over
classic Bluetooth: choose **Bluetooth** under *Printer* in the Output box, or run `t003-print "Hi" --bluetooth`
(optionally `--bluetooth AA:BB:CC:DD:EE:FF`). The printer has to be on and not connected to a phone, and it doesn't
need pairing. With no address the app looks for a T003 (Linux: `bluetoothctl`; it scans for about 5 seconds if the
system hasn't seen the printer yet). Tested on Linux only: it needs Python's Bluetooth sockets, which macOS builds don't have and Windows may.

## Roadmap

Ordered by priority, with no promised dates. Several ideas are inspired by 90s handheld cameras and their thermal
printers. Each item has tags: `fun` (it's about play), `useful` (it makes the app handier), `polish` (a small quality
fix), `infra` (builds, packaging, CI), `research` (needs hardware or a question answered first) and `big` (a lot of
work to build and to keep working).

**Next**
- [ ] `useful` New label (Ctrl+N), File > Open Recent, and the last label restored when the app starts
- [ ] `useful` `big` Batch-print from a CSV (`{column}` placeholders in the text and QR fields)
- [ ] `useful` `big` Undo/redo (Edit menu), then an album: recent and saved labels as a thumbnail gallery
- [ ] `polish` One idea for saving a design: presets (kept in the app) and `.t003label` files overlap, so merge them (e.g. Save as preset in the File menu, or a templates folder) or make the difference obvious
- [ ] `fun` More stickers (the Doodle tab has 12 so far), and a sticker that can be moved or resized after it is placed
- [ ] `fun` Poster mode: split one large image across several stickers, with alignment marks

**Later**
- [ ] `fun` More themes: Win95/98 grey, and user-defined colour themes
- [ ] `useful` Zoomable preview (View > Zoom, Ctrl+plus/minus/0) with a ruler/grid overlay
- [ ] `fun` `big` Webcam capture: take a photo and print it (in the browser: `getUserMedia`)
- [ ] `polish` Accessibility pass: the image controls have screen-reader names; name the rest, try Orca and NVDA, and show a checkbox's state with a tick as well as colour
- [ ] `polish` A keyboard-shortcuts window (Ctrl+?) and F1 help, once there are enough shortcuts to list
- [ ] `polish` Move "Open presets folder" out of Help (it's a utility, so File or a Settings menu)
- [ ] `infra` Publish to PyPI, so `pip install t003-label-gui` works without the git URL (the wheel is already built and tested in CI); only if someone asks
- [ ] `infra` Native Linux ARM64 and Windows ARM64 builds (newer ARM Linux needs glibc 2.39; until then use the pip install); only if someone asks

**Needs hardware or research first**
- [ ] `research` Hardware testing on Windows and macOS (CI builds them, but they are untested with a printer). Testers wanted.
- [ ] `useful` `research` Windows printing through the spooler, so no Zadig/WinUSB driver is needed (needs a Windows machine to test)
- [ ] `big` One web UI for every client (in progress on the `web-ui` branch): the existing Python engine runs in the browser through Pyodide, prints over Web Bluetooth from Chrome on Android (tested), and the desktop app becomes a shell around the same page. No Firefox or iOS for printing. Only a text, font, effect and border slice exists so far

## Building releases

`python packaging/build.py` builds for the OS it runs on (PyInstaller does not cross-compile).
Bump `__version__` in `src/t003gui/__init__.py` first (the About box, `--version` and the package metadata all read it).
`.github/workflows/release.yml` builds Linux, Windows and macOS on tag push (`git tag v0.2.1 && git push --tags`; the tag must match `__version__`),
self-tests each, and attaches them to a GitHub release with checksums.

## Licence

MIT for the code (see [LICENSE](LICENSE)). The bundled fonts keep their own licences, mostly the SIL Open Font
License; all texts are in `src/t003gui/fonts/LICENSES/`.
