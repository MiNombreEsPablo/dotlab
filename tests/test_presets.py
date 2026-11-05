import json

import pytest
from PIL import Image

from dotlab import api, core, doodle, presets


def test_a_preset_name_is_cleaned_or_refused_with_a_sentence():
    assert presets.clean_name("  Neon   Nights \n") == "Neon Nights"
    for bad, why in (("", "name"), ("   ", "name"), ("x" * 61, "60 characters")):
        with pytest.raises(ValueError, match=why):
            presets.clean_name(bad)


def test_a_web_preset_is_a_style_without_its_picture():
    ink = Image.new("L", (core.W, core.SH), 0)
    ink.paste(255, (10, 10, 80, 30))
    label = json.dumps({"text": "Fragile", "effect": "neon", "border": True, "border_style": "chamfer",
                        "image_path": "/tmp/somewhere/picture.png", "doodle": doodle.encode(ink)})
    entry = json.loads(api.preset_entry("  Fragile  stuff ", label))
    assert entry["name"] == "Fragile stuff"
    kept = entry["spec"]
    assert (kept["text"], kept["effect"], kept["border_style"]) == ("Fragile", "neon", "chamfer")
    assert kept["image_path"] == "" and kept["doodle"]  # a preset is a style: no picture; the doodle stays
