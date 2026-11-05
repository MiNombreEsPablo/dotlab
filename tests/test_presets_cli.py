import json

import pytest
from PIL import Image

from t003gui import cli, core
from t003gui.spec import LabelSpec
from t003gui.presets import PresetStore


def test_preset_roundtrip_and_delete(tmp_path):
    store = PresetStore(tmp_path / "sub" / "presets.json")
    assert store.names() == []
    spec = core.LabelSpec(text="shelf", qr="x", threshold=120, border=True, copies=2, density=9)
    store.save("Shelf", spec)
    store.save("alpha", core.LabelSpec(text="a"))
    assert store.names() == ["alpha", "Shelf"]
    assert store.get("Shelf") == spec
    store.delete("Shelf")
    assert store.get("Shelf") is None


def test_preset_ignores_unknown_fields_and_bad_json(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"old": {"text": "t", "removed_field": 1}}))
    assert PresetStore(path).get("old") == core.LabelSpec(text="t")
    path.write_text("not json")
    assert PresetStore(path).names() == []


def test_cli_preview_with_preset_override(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    PresetStore().save("p", core.LabelSpec(text="from preset", border=True))
    out = tmp_path / "out.png"
    cli.main(["--preset", "p", "--copies", "4", "--preview", str(out)])
    assert Image.open(out).size == (core.W, core.H)


def test_cli_requires_content():
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_reports_an_oversized_qr_instead_of_a_traceback(tmp_path):
    with pytest.raises(SystemExit) as e:
        cli.main(["x", "--qr", "x" * 5000, "--preview", str(tmp_path / "o.png")])
    assert "error:" in str(e.value)


def test_a_saved_label_that_is_only_a_doodle_prints(tmp_path, monkeypatch):
    from t003gui import composition, doodle

    ink = Image.new("L", (core.W, core.SH), 0)
    ink.paste(255, (10, 10, 100, 30))
    path = tmp_path / "scribble.t003label"
    composition.save(path, core.LabelSpec(doodle=doodle.encode(ink)))
    sent = []
    monkeypatch.setattr(core, "print_label", lambda spec, address='auto': sent.append(spec) or [])
    cli.main(["--file", str(path)])
    assert len(sent) == 1 and sent[0].doodle


def test_an_empty_label_still_asks_for_something_to_print(monkeypatch):
    monkeypatch.setattr(core, "print_label", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not print")))
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2


# --- presets saved by the web UI -----------------------------------------------------------------------------------------

def test_a_preset_name_is_cleaned_or_refused_with_a_sentence():
    from t003gui import presets

    assert presets.clean_name("  Neon   Nights \n") == "Neon Nights"
    for bad, why in (("", "name"), ("   ", "name"), ("x" * 61, "60 characters")):
        with pytest.raises(ValueError, match=why):
            presets.clean_name(bad)


def test_a_web_preset_is_a_plain_entry_the_cli_can_read(tmp_path, monkeypatch):
    import json

    from t003gui import api, doodle

    ink = Image.new("L", (core.W, core.SH), 0)
    ink.paste(255, (10, 10, 80, 30))
    store = PresetStore(tmp_path / "presets.json")
    label = json.dumps({"text": "Fragile", "effect": "neon", "border": True, "border_style": "chamfer",
                        "image_path": "/tmp/somewhere/picture.png", "doodle": doodle.encode(ink)})
    entry = json.loads(api.preset_entry("  Fragile  stuff ", label))
    store.save(entry["name"], LabelSpec(**entry["spec"]))
    kept = store.get("Fragile stuff")
    assert (kept.text, kept.effect, kept.border_style) == ("Fragile", "neon", "chamfer")
    assert kept.image_path == "" and kept.doodle  # a preset is a style: no picture; the doodle stays
    out = tmp_path / "p.png"
    monkeypatch.setattr(PresetStore, "__init__", lambda self, path=None: setattr(self, "path", tmp_path / "presets.json"))
    cli.main(["--preset", "Fragile stuff", "--preview", str(out)])  # t003-print reads what the web UI saved
    assert out.exists()
    assert json.loads(api.preset_entry("x", label))["spec"]["image_path"] == ""
