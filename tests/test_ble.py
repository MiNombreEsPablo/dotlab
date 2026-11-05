"""Printing over BLE from Python (Windows, macOS): the exchange is the web client's, checked against a fake `bleak`."""
import asyncio
import types

import pytest

from dotlab import ble, bluetooth, core, protocol

PAYLOAD = bytes(range(256)) * 3  # 768 bytes: five 180-byte chunks


class FakeDevice:
    def __init__(self, name, address="AA:BB:CC:DD:EE:FF"):
        self.name, self.address = name, address


def make_bleak(devices=(FakeDevice("T003-7A36"),), reply=0x00, properties=("write-without-response", "write"), fail=None):
    """What `bleak` offers `ble.send`; `log` records what the printer would have seen."""
    log = types.SimpleNamespace(writes=[], notify=None, response_modes=[], scans=[])

    class Scanner:
        @staticmethod
        async def find_device_by_filter(match, timeout):
            log.scans.append(("name", timeout))
            return next((d for d in devices if match(d, types.SimpleNamespace(local_name=d.name))), None)

        @staticmethod
        async def find_device_by_address(address, timeout):
            log.scans.append(("address", address))
            return next((d for d in devices if d.address == address), None)

    class Client:
        def __init__(self, device):
            self.device = device
            self.services = types.SimpleNamespace(
                get_characteristic=lambda uuid: types.SimpleNamespace(properties=list(properties)))

        async def __aenter__(self):
            if fail:
                raise fail
            return self

        async def __aexit__(self, *exc):
            return False

        async def start_notify(self, uuid, handler):
            assert uuid == bluetooth.BLE["notify"]
            log.notify = handler

        async def write_gatt_char(self, uuid, data, response):
            assert uuid == bluetooth.BLE["write"]
            log.writes.append(bytes(data))
            log.response_modes.append(response)
            if bytes(data) == protocol.STATUS_QUERY and reply is not None:
                log.notify(None, bytearray([reply]))

    return types.SimpleNamespace(BleakScanner=Scanner, BleakClient=Client, BleakError=RuntimeError), log


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(ble, "SETTLE", 0)
    monkeypatch.setitem(bluetooth.BLE, "gap_ms", 0)


def test_the_label_goes_in_chunks_then_the_status_query():
    bleak, log = make_bleak()
    assert ble.send(PAYLOAD, "auto", bleak=bleak) == []
    *label, query = log.writes
    assert query == protocol.STATUS_QUERY
    assert b"".join(label) == PAYLOAD and len(label) == 5
    assert all(len(part) <= bluetooth.BLE["chunk"] for part in label)
    assert set(log.response_modes) == {False}  # write without response, as the browser does when the printer allows it


def test_it_writes_with_response_when_the_printer_only_offers_that():
    bleak, log = make_bleak(properties=("write",))
    ble.send(b"x", "", bleak=bleak)
    assert set(log.response_modes) == {True}


def test_auto_finds_a_t003_by_name_and_an_address_by_address():
    other = FakeDevice("Headphones", "11:11:11:11:11:11")
    bleak, log = make_bleak(devices=(other, FakeDevice("T003-7A36")))
    ble.send(b"x", "auto", bleak=bleak)
    ble.send(b"x", "AA:BB:CC:DD:EE:FF", bleak=bleak)
    assert [kind for kind, _ in log.scans] == ["name", "address"]


def test_no_printer_in_range_says_so():
    bleak, _ = make_bleak(devices=(FakeDevice("Headphones"),))
    with pytest.raises(core.PrinterError, match="No T003 found over Bluetooth"):
        ble.send(b"x", "auto", bleak=bleak)


def test_the_printers_status_byte_becomes_problems():
    bleak, _ = make_bleak(reply=0x04)  # paper out
    assert ble.send(b"x", "auto", bleak=bleak) == protocol.status_problems(0x04)


def test_no_answer_to_the_status_query_is_not_an_error(monkeypatch):
    monkeypatch.setattr(ble, "STATUS_WAIT", 0.01)
    bleak, _ = make_bleak(reply=None)
    assert ble.send(b"x", "auto", bleak=bleak) == []


@pytest.mark.parametrize("error", [RuntimeError("device disconnected"), OSError("radio off"), asyncio.TimeoutError()])
def test_connection_failures_become_printer_errors(error):
    bleak, _ = make_bleak(fail=error)
    with pytest.raises(core.PrinterError, match="Can't print over Bluetooth"):
        ble.send(b"x", "auto", bleak=bleak)


def test_a_missing_bleak_says_what_to_install(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "bleak", None)
    with pytest.raises(core.PrinterError, match="pip install bleak"):
        ble.send(b"x", "auto")


@pytest.mark.parametrize("platform, expected", [("linux", False), ("win32", True), ("darwin", True)])
def test_windows_and_macos_print_over_ble_and_linux_over_rfcomm(monkeypatch, platform, expected):
    monkeypatch.setattr(bluetooth.sys, "platform", platform)
    assert bluetooth.uses_ble() is expected
    sent = []
    monkeypatch.setattr(ble, "send", lambda payload, target, **kw: sent.append(("ble", target)) or [])
    monkeypatch.setattr(bluetooth, "send", lambda payload, address, *a, **kw: sent.append(("rfcomm", address)) or [])
    monkeypatch.setattr(bluetooth, "resolve", lambda target: "AA:BB:CC:DD:EE:FF")
    bluetooth.print_to(b"x", "auto")
    assert sent == [("ble" if expected else "rfcomm", "auto" if expected else "AA:BB:CC:DD:EE:FF")]
