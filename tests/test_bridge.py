import base64
import json

from t003gui import api, bluetooth, core
from t003gui.bridge import Bridge

SPEC = json.dumps({"text": "Hello", "border": True})


def test_options_are_the_apis():
    assert Bridge().options() == api.options()


def test_preview_is_the_api_pixels_in_base64_with_the_hints():
    result = Bridge().preview(SPEC)
    assert base64.b64decode(result["pixels"]) == api.preview_pixels(SPEC) and result["hints"] == []


def test_settings_are_remembered_and_a_write_failure_is_data(tmp_path):
    from t003gui.settings import Settings

    bridge = Bridge(Settings(tmp_path / "s.json"))
    assert bridge.get_setting("printer") is None and bridge.get_setting("printer", "usb") == "usb"
    assert bridge.set_setting("printer", {"mode": "Bluetooth", "address": "AA:BB"}) == {"error": None}
    assert Bridge(Settings(tmp_path / "s.json")).get_setting("printer") == {"mode": "Bluetooth", "address": "AA:BB"}
    blocked = tmp_path / "file"
    blocked.write_text("x")
    assert Bridge(Settings(blocked / "s.json")).set_setting("a", 1)["error"]  # the folder can't be created


def test_print_goes_over_usb_without_a_target(monkeypatch):
    calls = []
    monkeypatch.setattr(core, "print_label", lambda spec: calls.append(spec) or ["out of paper"])
    result = Bridge().print_label(SPEC)
    assert result == {"problems": ["out of paper"], "error": None}
    assert calls[0].text == "Hello" and calls[0].border is True


def test_print_goes_over_bluetooth_with_a_target(monkeypatch):
    calls = []
    monkeypatch.setattr(core, "print_label", lambda spec, bluetooth=None: calls.append(bluetooth) or [])
    assert Bridge().print_label(SPEC, "AA:BB:CC:DD:EE:FF")["error"] is None
    assert Bridge().print_label(SPEC, "")["error"] is None  # "" = the first known T003
    assert calls == ["AA:BB:CC:DD:EE:FF", ""]


def test_failures_come_back_as_data_not_exceptions(monkeypatch):
    def fail(spec, bluetooth=None):
        raise core.PrinterError("T003 not found on USB")

    monkeypatch.setattr(core, "print_label", fail)
    assert Bridge().print_label(SPEC) == {"problems": [], "error": "T003 not found on USB"}
    monkeypatch.setattr(core, "print_label", lambda spec, bluetooth=None: (_ for _ in ()).throw(OSError("gone")))
    assert Bridge().print_label(SPEC)["error"] == "gone"
    broken = Bridge().print_label("{nope")  # bad JSON is a ValueError too
    assert broken["problems"] == [] and broken["error"]


def test_known_printers_are_plain_dicts(monkeypatch):
    monkeypatch.setattr(bluetooth, "known_printers", lambda: [("57:37:EB:A7:7A:36", "T003-7A36")])
    assert Bridge().known_printers() == [{"address": "57:37:EB:A7:7A:36", "name": "T003-7A36"}]


def test_the_bridge_needs_no_pywebview():
    import subprocess
    import sys
    from pathlib import Path

    code = ("import sys; sys.modules['webview'] = None\n"
            "from t003gui.bridge import Bridge; print(len(Bridge().preview('{}')['pixels']) > 0)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parent.parent, timeout=60)
    assert result.returncode == 0 and "True" in result.stdout, result.stderr


def test_a_picture_from_the_page_becomes_a_path_the_label_can_use():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (30, 20), (200, 30, 30)).save(buffer, format="PNG")
    result = Bridge().upload_image(base64.b64encode(buffer.getvalue()).decode(), "red.png")
    assert result["error"] is None and result["path"].endswith(".png")
    pixels = api.preview_pixels({"image_path": result["path"]})
    assert 0 in pixels and len(pixels) == core.W * core.H


def test_a_bad_upload_is_an_error_sentence_not_an_exception():
    bridge = Bridge()
    not_a_picture = bridge.upload_image(base64.b64encode(b"hello").decode(), "notes.png")
    assert not_a_picture["path"] is None and "notes.png isn't a picture" in not_a_picture["error"]
    broken = bridge.upload_image("***not base64***", "x.png")
    assert broken["path"] is None and broken["error"]


# --- exporting and saving the label as an image -------------------------------------------------------------------

class FakeDialogs:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def save(self, name, kind):
        self.asked.append((name, kind))
        return self.answer


def test_export_png_returns_the_image_and_a_name():
    import io

    from PIL import Image

    result = Bridge().export_png(json.dumps({"text": "Neon Nights\nsecond"}), 4)
    assert result["error"] is None and result["name"] == "Neon Nights.png"
    image = Image.open(io.BytesIO(base64.b64decode(result["data"])))
    assert image.size == (core.W * 4, core.SH * 4)


def test_a_bad_label_cannot_be_exported_but_says_why():
    result = Bridge().export_png(json.dumps({"text": "x", "image_path": "/no/such/picture.png"}))
    assert result["data"] is None and result["error"]


def test_save_file_writes_where_the_dialog_says(tmp_path):
    target = tmp_path / "out.png"
    dialogs = FakeDialogs(str(target))
    result = Bridge(dialogs=dialogs).save_file(base64.b64encode(b"PNGDATA").decode(), "Neon.png", "PNG image")
    assert result == {"saved": "out.png", "cancelled": False, "error": None}
    assert target.read_bytes() == b"PNGDATA" and dialogs.asked == [("Neon.png", "PNG image")]


def test_cancelling_the_dialog_is_not_an_error(tmp_path):
    result = Bridge(dialogs=FakeDialogs(None)).save_file(base64.b64encode(b"x").decode(), "a.png")
    assert result == {"saved": None, "cancelled": True, "error": None}
    assert not list(tmp_path.iterdir())


def test_save_file_failures_are_data(tmp_path):
    assert "can't save" in Bridge().save_file("eA==", "a.png")["error"]  # a window without dialogs
    blocked = tmp_path / "file"
    blocked.write_text("x")
    assert Bridge(dialogs=FakeDialogs(str(blocked / "a.png"))).save_file("eA==", "a.png")["error"]  # can't write there
    assert Bridge(dialogs=FakeDialogs(str(tmp_path / "b.png"))).save_file("***", "b.png")["error"]  # not base64


# --- label files --------------------------------------------------------------------------------------------------------

def test_a_label_file_goes_out_and_comes_back_through_the_bridge():
    out = Bridge().composition_dumps(json.dumps({"text": "Neon Nights\nx", "effect": "neon"}))
    assert out["error"] is None and out["name"] == "Neon Nights.t003label"
    text = base64.b64decode(out["data"]).decode("utf-8")
    back = Bridge().composition_loads(text)
    assert back["error"] is None and json.loads(back["spec"])["effect"] == "neon"


def test_a_bad_label_file_is_an_error_sentence():
    result = Bridge().composition_loads("this is not a label")
    assert result["spec"] is None and "not a label file" in result["error"]
    assert Bridge().composition_loads('{"format": "t003-label", "version": 7, "spec": {}}')["error"].startswith("this file was made")


# --- presets ------------------------------------------------------------------------------------------------------------

def _presets_bridge(tmp_path):
    from t003gui.presets import PresetStore

    return Bridge(presets=PresetStore(tmp_path / "presets.json"))


def test_presets_are_listed_saved_loaded_and_deleted(tmp_path):
    bridge = _presets_bridge(tmp_path)
    assert bridge.presets_list() == {"names": []}
    for name in ("banana", "Apple", "cherry"):
        assert bridge.preset_save(name, json.dumps({"text": name, "effect": "neon"}))["error"] is None
    assert bridge.presets_list()["names"] == ["Apple", "banana", "cherry"]  # sorted without regard to case
    loaded = bridge.preset_get("Apple")
    assert loaded["error"] is None and json.loads(loaded["spec"])["text"] == "Apple" and json.loads(loaded["spec"])["effect"] == "neon"
    assert bridge.preset_delete("banana") == {"error": None}
    assert bridge.presets_list()["names"] == ["Apple", "cherry"]
    assert bridge.preset_delete("never existed") == {"error": None}  # nothing to delete is fine


def test_saving_over_a_preset_replaces_it_and_a_bad_name_is_a_sentence(tmp_path):
    bridge = _presets_bridge(tmp_path)
    bridge.preset_save("one", json.dumps({"text": "first"}))
    bridge.preset_save("one", json.dumps({"text": "second"}))
    assert json.loads(bridge.preset_get("one")["spec"])["text"] == "second" and len(bridge.presets_list()["names"]) == 1
    result = bridge.preset_save("   ", json.dumps({"text": "x"}))
    assert result["saved"] is None and "name" in result["error"]
    assert bridge.preset_get("nope")["spec"] is None and "no preset" in bridge.preset_get("nope")["error"]


# --- the Help menu's links ------------------------------------------------------------------------------------------------

def test_the_shell_opens_the_projects_own_pages_and_nothing_else(monkeypatch):
    from t003gui import about

    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    bridge = Bridge()
    assert bridge.open_url(about.ISSUES_URL) == {"error": None} and bridge.open_url(about.REPO_URL) == {"error": None}
    for refused in ("https://example.com/", "file:///etc/passwd", "javascript:alert(1)", about.REPO_URL + "evil.example/x",
                    "http://localhost:1/", ""):
        assert "project's pages" in bridge.open_url(refused)["error"], refused
    assert opened == [about.ISSUES_URL, about.REPO_URL]


def test_the_about_box_facts_come_from_the_engine():
    from t003gui import __version__, about, fonts

    app = json.loads(api.options())["app"]
    assert app == {"name": "T003 Label Studio", "version": __version__, "repo_url": about.REPO_URL,
                   "issues_url": about.ISSUES_URL, "fonts": len(fonts.BUNDLED)}
