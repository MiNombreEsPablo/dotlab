import json

from dotlab import api, bluetooth, protocol


def test_the_web_client_gets_the_ble_constants_from_the_api():
    ble = json.loads(api.options())["bluetooth"]
    assert ble["ble"] == bluetooth.BLE and ble["name_prefix"] == "T003"
    assert ble["status_query"] == list(protocol.STATUS_QUERY)
    assert ble["serial"] == bluetooth.SERIAL and ble["serial"]["service"] == "00001101-0000-1000-8000-00805f9b34fb"
    assert ble["serial"]["chunk"] == bluetooth.RFCOMM_CHUNK and ble["serial"]["gap_ms"] == 20
    assert api.status_problems(0x08) == ["out of ribbon"]


def test_chunks():
    assert list(protocol.chunks(b"abcdefg", 3)) == [b"abc", b"def", b"g"]
    assert list(protocol.chunks(b"", 3)) == []
