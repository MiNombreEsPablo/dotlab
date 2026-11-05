"""Print over Bluetooth: the transport details every client shares.

The T003 is dual-mode and takes the same TSPL (protocol.py) over both transports:

- Classic serial (RFCOMM), used by the desktop app and CLI on Linux through `send` below: it needs Python's Bluetooth
  sockets, which Linux has and macOS and Windows lack.
- BLE (GATT): the web build uses it from a browser (Web Bluetooth) and the desktop app on Windows and macOS from Python
  (`ble.py`, through `bleak`). Its UUIDs and timings are in `BLE` so every client reads them from one place.

`print_to` picks the transport for the system.

No window toolkit in here. Pairing is not needed (RFCOMM connects to an unpaired printer, verified on Linux); the
printer only has to be switched on, in range and not held by a phone.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time

from . import protocol
from .render import PrinterError

NAME_PREFIX = "T003"  # the printer advertises as "T003-XXXX"
RFCOMM_CHANNEL = 1  # the printer's serial-port channel
RFCOMM_CHUNK = 512  # bytes per write
RFCOMM_GAP = 0.02  # seconds between writes; without a gap the printer's buffer can overflow
SCAN_SECONDS = 5  # how long "auto" looks for a printer the system has not seen yet
SETTLE = 1.0  # seconds to let the printer take the last bytes before asking for its status
BLE = {  # measured on the T003: TSPL written to `write` is answered with the status byte on `notify`
    "service": "000018f0-0000-1000-8000-00805f9b34fb",
    "write": "00002af1-0000-1000-8000-00805f9b34fb",
    "notify": "00002af0-0000-1000-8000-00805f9b34fb",
    "chunk": 180,  # bytes per write: a whole label in ~0.6 s (20 bytes works too, but takes 16 s)
    "gap_ms": 5,
}
_ADDRESS = re.compile(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}")


def normalize_address(text: str) -> str | None:
    """"aa-bb-cc-dd-ee-ff" -> "AA:BB:CC:DD:EE:FF", or None when it isn't a Bluetooth address."""
    address = text.strip().upper().replace("-", ":")
    return address if _ADDRESS.fullmatch(address) else None


def known_printers() -> list[tuple[str, str]]:
    """[(address, name)] of T003s the system's Bluetooth has seen (paired or just scanned). Best effort (Linux's
    bluetoothctl); never raises."""
    try:
        out = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "Device" and parts[2].startswith(NAME_PREFIX):
            address = normalize_address(parts[1])
            if address:
                found.append((address, parts[2]))
    return found


def scan(seconds: int = SCAN_SECONDS) -> None:
    """Let the system's Bluetooth look around for a few seconds, so a printer it has not seen yet becomes known
    (Linux's bluetoothctl). Best effort; never raises."""
    try:
        subprocess.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], capture_output=True, text=True,
                       timeout=seconds + 5)
    except (OSError, subprocess.SubprocessError):
        pass


def resolve(target: str) -> str:
    """The address to print to: `target` itself when it is one, or the first known T003 for "" / "auto"."""
    text = target.strip()
    if text.lower() in ("", "auto"):
        printers = known_printers()
        if not printers:  # the system only lists devices it has seen: look around once before giving up
            scan()
            printers = known_printers()
        if not printers:
            raise PrinterError(
                "No T003 found over Bluetooth. Switch the printer on (and disconnect it from any phone), "
                "or give its address (AA:BB:CC:DD:EE:FF)."
            )
        return printers[0][0]
    address = normalize_address(text)
    if address is None:
        raise PrinterError(f"{text!r} is not a Bluetooth address (expected AA:BB:CC:DD:EE:FF).")
    return address


def uses_ble() -> bool:
    """Whether this system prints over BLE (Windows, macOS) instead of RFCOMM (Linux)."""
    return not sys.platform.startswith("linux")


def print_to(payload: bytes, target: str) -> list[str]:
    """Send `payload` to `target` ("" / "auto" or an address) over the transport this system has; see `send`."""
    if uses_ble():
        from . import ble

        return ble.send(payload, target)
    return send(payload, resolve(target))


def _connect(address: str, channel: int):
    if not (hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")):
        raise PrinterError("This Python has no Bluetooth sockets (Linux does; macOS doesn't): use the web page (Chrome or Edge) instead.")
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(10)
    try:
        sock.connect((address, channel))
    except OSError:
        sock.close()
        raise
    return sock


def _reason(e: OSError) -> str:
    return e.strerror or str(e)


def _drain(sock) -> None:
    """Throw away bytes left over from an earlier session, so the status reply read later is this session's."""
    sock.settimeout(0.2)
    try:
        while sock.recv(64):
            pass
    except (socket.timeout, BlockingIOError):
        pass


def send(payload: bytes, address: str, channel: int = RFCOMM_CHANNEL, *, connect=_connect) -> list[str]:
    """Write a TSPL payload over RFCOMM; returns printer problems reported afterwards (empty if fine), like core.send."""
    try:
        sock = connect(address, channel)
    except OSError as e:
        raise PrinterError(
            f"Can't reach the printer over Bluetooth ({_reason(e)}). Is it switched on, in range and not "
            "connected to a phone?"
        ) from e
    try:
        _drain(sock)
        sock.settimeout(5)
        for part in protocol.chunks(payload, RFCOMM_CHUNK):
            sock.sendall(part)
            time.sleep(RFCOMM_GAP)
        time.sleep(SETTLE)
        sock.sendall(protocol.STATUS_QUERY)
        sock.settimeout(1.5)
        try:
            reply = sock.recv(64)
        except socket.timeout:
            return []
        return protocol.status_problems(reply[0]) if reply else []
    except OSError as e:
        raise PrinterError(f"Bluetooth connection lost while printing ({_reason(e)}).") from e
    finally:
        sock.close()
