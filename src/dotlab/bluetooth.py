"""How the page talks to the printer over Bluetooth: the numbers every client needs, in one place.

The T003 is dual-mode and takes the same TSPL (protocol.py) over both transports; `api.options()` hands these to the
browser, so nothing about the printer is repeated in JavaScript:

- BLE (GATT), for Web Bluetooth (Android, and Windows and macOS): the service and characteristics in `BLE`.
- Classic serial (RFCOMM), for Web Serial (desktop Chrome and Edge, and the only way on Linux, where BlueZ can't open this
  printer's BLE link): the Serial Port service in `SERIAL`. The printer must be paired in the OS first.

No code runs here and no window toolkit is needed: the module is shipped to the browser's Python (Pyodide) as it is.
"""
from __future__ import annotations

NAME_PREFIX = "T003"  # the printer advertises as "T003-XXXX"
RFCOMM_CHUNK = 512  # bytes per write over classic serial
RFCOMM_GAP = 0.02  # seconds between writes; without a gap the printer's buffer can overflow
BLE = {  # measured on the T003: TSPL written to `write` is answered with the status byte on `notify`
    "service": "000018f0-0000-1000-8000-00805f9b34fb",
    "write": "00002af1-0000-1000-8000-00805f9b34fb",
    "notify": "00002af0-0000-1000-8000-00805f9b34fb",
    "chunk": 180,  # bytes per write: a whole label in ~0.6 s (20 bytes works too, but takes 16 s)
    "gap_ms": 5,
}
SERIAL = {  # classic Bluetooth serial (RFCOMM) from a browser (Web Serial): the Serial Port Profile service, and the pacing
    "service": "00001101-0000-1000-8000-00805f9b34fb",
    "chunk": RFCOMM_CHUNK,
    "gap_ms": int(RFCOMM_GAP * 1000),
}
