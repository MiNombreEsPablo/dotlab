import errno
import socket
import subprocess

import pytest

from dotlab import api, bluetooth, cli, core, protocol

ADDRESS = "57:37:EB:A7:7A:36"


class FakeSocket:
    """An RFCOMM socket: `stale` is what an earlier session left unread, `reply` is the answer to the status query."""

    def __init__(self, reply=b"\x00", stale=(), fail_write_after=None):
        self.reply, self.stale = reply, list(stale)
        self.written, self.closed, self.queried = [], False, False
        self.fail_write_after = fail_write_after

    def settimeout(self, value):
        pass

    def sendall(self, data):
        if self.fail_write_after is not None and len(self.written) >= self.fail_write_after:
            raise OSError(errno.EPIPE, "Broken pipe")
        self.written.append(data)
        if data == protocol.STATUS_QUERY:
            self.queried = True

    def recv(self, size):
        if not self.queried:
            if self.stale:
                return self.stale.pop(0)
            raise socket.timeout()
        if self.reply is None:
            raise socket.timeout()
        return self.reply

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    monkeypatch.setattr(bluetooth.time, "sleep", lambda s: None)


def send_with(sock, payload=b"x" * 1300):
    return bluetooth.send(payload, ADDRESS, connect=lambda address, channel: sock)


def test_payload_goes_out_in_chunks_then_the_status_query():
    sock = FakeSocket()
    payload = bytes(range(256)) * 5
    assert send_with(sock, payload) == []
    *parts, last = sock.written
    assert b"".join(parts) == payload and last == protocol.STATUS_QUERY
    assert all(len(part) <= bluetooth.RFCOMM_CHUNK for part in parts) and len(parts) == 3
    assert sock.closed


def test_connects_to_the_given_address_and_channel():
    seen = []
    bluetooth.send(b"x", ADDRESS, 3, connect=lambda address, channel: seen.append((address, channel)) or FakeSocket())
    assert seen == [(ADDRESS, 3)]


def test_status_flags_come_back_as_problems():
    assert send_with(FakeSocket(reply=b"\x04")) == ["out of paper"]
    assert send_with(FakeSocket(reply=b"\x01\x80")) == ["head open"]  # only the first byte is the status


def test_stale_bytes_from_an_earlier_session_are_not_read_as_the_status():
    assert send_with(FakeSocket(reply=b"\x00", stale=[b"\x00\x00", b"\x04"])) == []


def test_no_reply_is_not_an_error():
    sock = FakeSocket(reply=None)
    assert send_with(sock) == [] and sock.closed


def test_a_refused_connection_says_what_to_check():
    def refuse(address, channel):
        raise OSError(errno.ECONNREFUSED, "Connection refused")

    with pytest.raises(core.PrinterError) as e:
        bluetooth.send(b"x", ADDRESS, connect=refuse)
    assert "Connection refused" in str(e.value) and "in range" in str(e.value)


def test_a_lost_connection_while_printing_is_reported_and_closed():
    sock = FakeSocket(fail_write_after=1)
    with pytest.raises(core.PrinterError, match="lost while printing"):
        send_with(sock)
    assert sock.closed


def test_python_without_bluetooth_sockets_says_so(monkeypatch):
    monkeypatch.delattr(socket, "AF_BLUETOOTH", raising=False)
    with pytest.raises(core.PrinterError, match="no Bluetooth sockets"):
        bluetooth._connect(ADDRESS, 1)


@pytest.mark.parametrize("text, expected", [
    (ADDRESS, ADDRESS), (ADDRESS.lower(), ADDRESS), (ADDRESS.replace(":", "-"), ADDRESS), (f"  {ADDRESS}\n", ADDRESS),
    ("", None), ("auto", None), ("57:37:EB:A7:7A", None), ("57:37:EB:A7:7A:ZZ", None), ("T003-7A36", None),
])
def test_normalize_address(text, expected):
    assert bluetooth.normalize_address(text) == expected


def _devices(monkeypatch, stdout):
    result = subprocess.CompletedProcess([], 0, stdout=stdout)
    monkeypatch.setattr(bluetooth.subprocess, "run", lambda *a, **k: result)


def test_known_printers_picks_the_t003s(monkeypatch):
    _devices(monkeypatch, f"Device AA:BB:CC:DD:EE:FF JBL Flip\nDevice {ADDRESS} T003-7A36\nDevice 11:22:33:44:55:66 T003\n"
                          "Device nonsense T003-bad\nnot a device line\n")
    assert bluetooth.known_printers() == [(ADDRESS, "T003-7A36"), ("11:22:33:44:55:66", "T003")]


@pytest.mark.parametrize("error", [FileNotFoundError("no bluetoothctl"), subprocess.TimeoutExpired("bluetoothctl", 5),
                                   subprocess.CalledProcessError(1, "bluetoothctl")])
def test_known_printers_never_raises(monkeypatch, error):
    def boom(*a, **k):
        raise error

    monkeypatch.setattr(bluetooth.subprocess, "run", boom)
    assert bluetooth.known_printers() == []


def test_resolve(monkeypatch):
    monkeypatch.setattr(bluetooth, "known_printers", lambda: [(ADDRESS, "T003-7A36")])
    assert bluetooth.resolve(ADDRESS.lower()) == ADDRESS
    assert bluetooth.resolve("") == bluetooth.resolve("auto") == bluetooth.resolve(" AUTO ") == ADDRESS
    with pytest.raises(core.PrinterError, match="not a Bluetooth address"):
        bluetooth.resolve("T003-7A36")
    monkeypatch.setattr(bluetooth, "known_printers", lambda: [])
    with pytest.raises(core.PrinterError, match="No T003 found"):
        bluetooth.resolve("auto")


def test_auto_scans_once_when_no_printer_is_known_yet(monkeypatch):
    known, scans = [[], [(ADDRESS, "T003-7A36")]], []
    monkeypatch.setattr(bluetooth, "known_printers", lambda: known.pop(0))
    monkeypatch.setattr(bluetooth, "scan", lambda *a: scans.append(1))
    assert bluetooth.resolve("auto") == ADDRESS and scans == [1]


def test_auto_does_not_scan_when_a_printer_is_already_known(monkeypatch):
    monkeypatch.setattr(bluetooth, "known_printers", lambda: [(ADDRESS, "T003-7A36")])
    monkeypatch.setattr(bluetooth, "scan", lambda *a: (_ for _ in ()).throw(AssertionError("must not scan")))
    assert bluetooth.resolve("") == ADDRESS


def test_an_explicit_address_never_scans(monkeypatch):
    monkeypatch.setattr(bluetooth, "scan", lambda *a: (_ for _ in ()).throw(AssertionError("must not scan")))
    assert bluetooth.resolve(ADDRESS) == ADDRESS


def test_scan_runs_bluetoothctl_with_a_timeout_and_never_raises(monkeypatch):
    seen = []
    monkeypatch.setattr(bluetooth.subprocess, "run", lambda cmd, **kw: seen.append((cmd, kw["timeout"])))
    bluetooth.scan(4)
    assert seen == [(["bluetoothctl", "--timeout", "4", "scan", "on"], 9)]
    monkeypatch.setattr(bluetooth.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    bluetooth.scan()  # no bluetoothctl: silently nothing


def test_print_label_goes_to_the_given_address_or_the_first_known_printer(monkeypatch):
    monkeypatch.setattr(bluetooth.sys, "platform", "linux")  # RFCOMM; Windows and macOS print over BLE (test_ble.py)
    calls = []
    monkeypatch.setattr(core.bt, "send", lambda payload, address: calls.append((payload, address)) or ["head open"])
    monkeypatch.setattr(bluetooth, "known_printers", lambda: [(ADDRESS, "T003-7A36")])
    spec = core.LabelSpec(text="x")
    assert core.print_label(spec, ADDRESS.lower()) == ["head open"]
    assert core.print_label(spec, "") == ["head open"]  # "" = the first known T003
    assert core.print_label(spec) == ["head open"]  # the default is the same
    assert [c[1] for c in calls] == [ADDRESS] * 3
    assert all(c[0] == core.tspl(spec) for c in calls)


def test_cli_bluetooth_flag(monkeypatch):
    seen = []
    monkeypatch.setattr(core, "print_label", lambda spec, address="auto": seen.append(address) or [])
    cli.main(["hello"])
    cli.main(["hello", "--address", ADDRESS])
    assert seen == ["auto", ADDRESS]


def test_cli_reports_a_bluetooth_failure_as_an_error(monkeypatch):
    def refuse(spec, address="auto"):
        raise core.PrinterError("Can't reach the printer over Bluetooth")

    monkeypatch.setattr(core, "print_label", refuse)
    with pytest.raises(SystemExit) as e:
        cli.main(["hello", "--address", ADDRESS])
    assert "Can't reach the printer" in str(e.value)


def test_chunks():
    assert list(protocol.chunks(b"abcdefg", 3)) == [b"abc", b"def", b"g"]
    assert list(protocol.chunks(b"", 3)) == []


def test_the_web_client_gets_the_ble_constants_from_the_api():
    options = api.options()
    import json

    ble = json.loads(options)["bluetooth"]
    assert ble["ble"] == bluetooth.BLE and ble["name_prefix"] == "T003"
    assert ble["status_query"] == list(protocol.STATUS_QUERY)
    assert api.status_problems(0x08) == ["out of ribbon"]
