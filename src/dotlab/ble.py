"""Print over BLE from Python: what the desktop app uses on Windows and macOS, where classic Bluetooth sockets aren't
available to Python (Linux uses RFCOMM, bluetooth.py).

It is the same exchange the web build does from a browser (web/printer/ble.js): the TSPL goes to the `write`
characteristic in `bluetooth.BLE["chunk"]` pieces with `gap_ms` between them, then the status query, and the status
byte comes back on `notify`. `bleak` does the Bluetooth part on both systems (WinRT, CoreBluetooth); it is imported
only here, when printing. No pairing is needed. `target` is "" / "auto" (the first T003 in range, by its name) or the
device's address as the system names it (a MAC on Windows, a UUID on macOS, which hides MACs).
"""
from __future__ import annotations

import asyncio

from . import protocol
from .bluetooth import BLE, NAME_PREFIX, SCAN_SECONDS, SETTLE
from .render import PrinterError

STATUS_WAIT = 1.5  # seconds to wait for the printer's answer to the status query before taking silence as "fine"


def _load_bleak():
    try:
        import bleak
    except ImportError as e:
        raise PrinterError("Bluetooth printing needs the 'bleak' package: pip install bleak") from e
    return bleak


async def _find(bleak, target: str):
    if target.strip().lower() in ("", "auto"):
        device = await bleak.BleakScanner.find_device_by_filter(
            lambda d, adv: ((d.name or getattr(adv, "local_name", None) or "").startswith(NAME_PREFIX)), timeout=SCAN_SECONDS)
    else:
        device = await bleak.BleakScanner.find_device_by_address(target.strip(), timeout=SCAN_SECONDS)
    if device is None:
        raise PrinterError(
            "No T003 found over Bluetooth. Switch the printer on (and disconnect it from any phone), "
            "or give its address."
        )
    return device


async def _write(client, payload: bytes, response: bool) -> None:
    for part in protocol.chunks(payload, BLE["chunk"]):
        await client.write_gatt_char(BLE["write"], part, response=response)
        await asyncio.sleep(BLE["gap_ms"] / 1000)


async def _send(payload: bytes, target: str, bleak) -> list[str]:
    device = await _find(bleak, target)
    reply: asyncio.Future = asyncio.get_running_loop().create_future()

    def on_status(_sender, data: bytearray) -> None:
        if data and not reply.done():
            reply.set_result(data[0])

    async with bleak.BleakClient(device) as client:
        characteristic = client.services.get_characteristic(BLE["write"])
        response = "write-without-response" not in (characteristic.properties if characteristic else [])
        await client.start_notify(BLE["notify"], on_status)
        await _write(client, payload, response)
        await asyncio.sleep(SETTLE)
        await _write(client, protocol.STATUS_QUERY, response)
        try:
            status = await asyncio.wait_for(reply, STATUS_WAIT)
        except asyncio.TimeoutError:
            return []  # like the other transports, no answer isn't an error
        return protocol.status_problems(status)


def send(payload: bytes, target: str = "auto", *, bleak=None) -> list[str]:
    """Print a TSPL payload; returns the problems the printer reports afterwards (empty if fine), like `bluetooth.send`."""
    bleak = bleak or _load_bleak()
    try:
        return asyncio.run(_send(payload, target, bleak))
    except PrinterError:
        raise
    except (OSError, asyncio.TimeoutError, getattr(bleak, "BleakError", OSError)) as e:
        raise PrinterError(f"Can't print over Bluetooth ({e}). Is the printer switched on, in range and not connected to a phone?") from e
