# What the printer's USB drive tells us

The T003 ships with a USB stick (volume `443E-3AAC`, read 2026-11-06) holding a driver and a picture tutorial per OS
(Linux, Windows, macOS, ChromeOS). **There is no label software and no file format**: the printer is meant to be a
plain system printer fed by a PDF/print dialog. Everything below comes from the Linux package, `printer-driver-orgsta`
3.13.27 (CUPS filter `rastertosnailtspl`, plus `ORGSTA-T003.ppd`), read with `strings`/`objdump`. The binaries are not
in this repo (proprietary, 47 MB for the Windows one); the hashes below identify what was read.

| file | sha256 |
| --- | --- |
| `T003-ORGSTA-drive-Linux_3.13.27_all.deb` | `54c7153076723e8ec76515be05ce34251e0f7ca87212892d8574385bfcce5e7d` |
| `T003-ORGSTA-drive-Windows 02-2024.exe` | `48c896daacbde47a6f3031f0e84cfe21610f08b4cd03151f8b8de5bea21d22e7` |
| `T003-ORGSTA-drive-macOS 3.13.18.pkg` | `fe5f3cbbb2eb17652e22abdc8045ffebc9c705293b310165a162f8efaefd41cc` |
| `T003-ORGSTA-drive-ChromeOS 0-1-4-prod.zip` | `a1f69f85478105f4ae0f7b5465df6d0c1b6d71b80e7f2b970a929ffa76bad3e0` |

## The PPD

- `1284DeviceID: MFG:ORGSTA;CMD:TSPL2;MDL:T003` — the printer speaks TSPL2, as we found. One resolution: **203 dpi**.
- Max media width 204.1 pt (72 mm: the `SIZE 72 mm` we send); custom heights up to 6480 pt.
- Preset sizes (mm): 30×20, 40×30 (default), 50×30, 50×50, 50×80. None is our 72×30 sticker.
- Options: gap height 0–10 (the number is millimetres, default 3), paper type (Normal = "as set on the printer",
  LabelGaps, LabelMark, Continue), post-print action (None, TearOff (default), PeelOff, Cut, PartialCut), direct
  thermal vs transfer, speed, **darkness 1–15 in the dialog**, mirror, negative, brightness, halftone.

## The command stream the vendor filter sends

Per page, in this order (`jobSetup`, then `doPrintImage`/`endPage`). `\r\n` after every line.

```
SIZE %.1f mm, %.1f mm            page size in mm
<gap>                            see below; omitted entirely for paper type "Normal"
REFERENCE 0,0
DIRECTION %d,0                   1 normally, 0 for the "Rotation180" origin
SPEED %s                         only when the speed is a number > 0
DENSITY %d                       only when 0..30 (the dialog offers 1-15)
SET RIBBON OFF | ON              Direct thermal | Transfer
OFFSET 0.0 mm
SET TEAR/PEEL/CUTTER ON|OFF      from the post-print action
CLS
BITMAP 0,0,<bytes per row>,<rows>,0,<data>     mode 0, MSB first, 1 = white
\r\n
PRINT 1,<copies>
```

`<gap>` is `GAP 0, 0` for paper type Continue (or a gap of 0), `GAP <g> mm, 0.0 mm` for LabelGaps, `BLINE <g> mm,
0.0 mm` for LabelMark. An unknown type logs "Unknown paper type" and sends nothing.

## How it compares with `protocol.tspl`

Ours: `SIZE 72 mm,30 mm`, `GAP 2 mm,0 mm`, `DIRECTION 1,0`, `DENSITY n`, `CLS`, `BITMAP 0,0,48,224,0,…`, `PRINT n,1`.
The bitmap and the order of the common commands match the vendor's, so the vendor driver confirms the core of what
we do (same mode, same bit sense). Differences worth knowing:

- **`DENSITY` goes to 30** in the vendor code (`0..30`), the dialog stops at 15. We clamp at 15. Untested on hardware:
  anything above 15 may do nothing or print darker; try it on a spare sticker before widening `spec.density`.
- **`PRINT 1,<copies>`** (one set, N copies) where we send `PRINT <copies>,1`. Same result in TSPL.
- Things the vendor sends and we don't: `REFERENCE 0,0`, `OFFSET 0.0 mm`, `SET RIBBON OFF`, `SET TEAR ON` (the PPD
  default post-action is TearOff), `SET PEEL OFF`, `SET CUTTER OFF`, and a `SPEED` line. These are the first suspects
  for the continuous-paper "Label error" noted in AGENTS.md: our probes sent `SIZE` + `GAP 0` and nothing else, so the
  firmware may have been left in a tear/peel/cutter state the vendor resets on every job.
- `SIZE` and `GAP` use a space after the comma and `GAP 0, 0` has no units (zero either way).

## Not worth chasing

- The tutorial PDFs only show installing the driver and printing a PDF; darkness is set from the print dialog.
- Windows/macOS/ChromeOS packages are the same filter family (`rastertosnail*` also exists for ZPL, EPL, PPLI, XPL; the
  T003's PPD selects the TSPL one).
