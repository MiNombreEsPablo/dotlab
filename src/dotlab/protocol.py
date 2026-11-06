"""The TSPL payload and the printer's status codes, shared by every client.

No transport and no window toolkit in here: the CLI sends these bytes over RFCOMM (bluetooth.py), and the web build sends the
same bytes over Bluetooth, so the payload is built in exactly one place.
"""
from __future__ import annotations

from typing import Iterator

from .render import render, to_bitmap
from .spec import H, W, LabelSpec

STATUS_QUERY = b"\x1b!?"  # the printer answers with one status byte (0 = ready)
STATUS_FLAGS = {0x01: "head open", 0x02: "paper jam", 0x04: "out of paper", 0x08: "out of ribbon", 0x80: "error"}


def auto_density(data: bytes) -> int:
    """Darkness for a bitmap (1 = white): the more of it is ink, the lower the heat. Measured on a printed dithered photo,
    darkness 1 beat 3 and 7 (dots bleed together and fill the shadows), while sparse text and QR codes want ~7."""
    ink = 1 - sum(b.bit_count() for b in data) / (len(data) * 8)
    return round(7 - 6 * min(1.0, max(0.0, (ink - 0.1) / 0.25)))


def tspl(spec: LabelSpec) -> bytes:
    data = to_bitmap(render(spec)).tobytes()  # 1 = white, 0 = black, same as TSPL BITMAP mode 0
    density = auto_density(data) if spec.density < 0 else min(15, max(0, spec.density))
    head = (
        f"SIZE 72 mm,30 mm\r\nGAP 2 mm,0 mm\r\nDIRECTION 1,0\r\nDENSITY {density}\r\nCLS\r\n"
        f"BITMAP 0,0,{W // 8},{H},0,"
    ).encode()
    return head + data + f"\r\nPRINT {min(99, max(1, spec.copies))},1\r\n".encode()


def status_problems(status: int) -> list[str]:
    """The problems a status byte reports, as short phrases (empty when the printer is fine)."""
    return [msg for bit, msg in STATUS_FLAGS.items() if status & bit]


def chunks(data: bytes, size: int) -> Iterator[bytes]:
    """`data` in pieces of at most `size` bytes: every transport writes the payload in parts (Bluetooth sends small ones)."""
    for i in range(0, len(data), size):
        yield data[i : i + size]
