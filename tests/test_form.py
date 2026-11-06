import json
from dataclasses import fields as dataclass_fields

import pytest

from dotlab import api, form, layers, spec

SPEC = spec.LabelSpec()


def _check_rules_and_ranges(group, defaults, owner):
    for field in group:
        if field.kind == "choice":
            assert field.choices and all(len(c) == 3 for c in field.choices)
        if field.kind == "number":
            assert field.minimum <= getattr(defaults, field.name) <= field.maximum, field.name
        if field.kind == "slider":
            default = getattr(defaults, field.name)
            assert field.minimum <= (field.default if default is None else default) <= field.maximum, field.name
            if field.scale == "log":
                assert field.minimum < field.neutral < field.maximum
        for rule in (field.show_when, field.enable_when):
            if rule:  # the field a rule watches exists, is a choice, and the values are among its choices
                watched = next(f for f in group if f.name == rule[0] and f.tab == field.tab)
                assert watched.kind == "choice" and set(rule[1]) <= {c[0] for c in watched.choices}, field.name
        if field.gate:  # the gate's value is a choice and the field it sends is a slider
            assert field.gate in {c[0] for c in field.choices}
            assert next(f for f in group if f.name == field.gate and f.tab == field.tab).kind == "slider"


def test_every_field_is_a_real_spec_field_with_valid_choices():
    names = {f for f in spec.LabelSpec.__dataclass_fields__}
    for field in form.FIELDS:
        assert field.name in names, field.name
        assert field.tab in {form.OUTPUT, form.PAPER} | {t.id for t in form.TABS}, field.name
        if field.toggle:
            assert isinstance(getattr(SPEC, field.toggle), bool)
    _check_rules_and_ranges([f for f in form.FIELDS if f.kind != "layers"], SPEC, "spec")


def test_every_layer_field_is_a_property_of_a_layer_type_with_valid_choices():
    names = {f.name for f in dataclass_fields(layers.Layer)}
    for field in form.LAYER_FIELDS:
        assert field.name in names, field.name
        assert field.tab in set(layers.TYPES) | {form.BOX}, field.name
    for kind in layers.TYPES:
        _check_rules_and_ranges([f for f in form.LAYER_FIELDS if f.tab in (kind, form.BOX)], layers.Layer(kind), kind)


def test_every_spec_field_has_a_control_or_is_legacy_or_pending():
    """The drift guard: a new LabelSpec field must be described in form.py (or admitted in PENDING) before it ships,
    so no client can quietly lack a control for it."""
    names = set(spec.LabelSpec.__dataclass_fields__)
    assert not (form.covered() & (form.PENDING | form.LEGACY)), "described and pending at once"
    assert names == form.covered() | form.PENDING | form.LEGACY, sorted(names ^ (form.covered() | form.PENDING | form.LEGACY))


def test_every_layer_property_is_edited_by_the_inspector_except_the_bookkeeping_ones():
    shown = {f.name for f in form.LAYER_FIELDS} | {f.gate for f in form.LAYER_FIELDS if f.gate}
    assert {f.name for f in dataclass_fields(layers.Layer)} - shown == {"t", "hidden"}


def test_choices_follow_spec_so_a_new_effect_needs_no_ui_change():
    by_name = {f.name: f for f in form.LAYER_FIELDS}
    assert [c[0] for c in by_name["effect"].choices] == list(spec.EFFECTS)
    assert [c[0] for c in by_name["align"].choices] == list(spec.ALIGNMENTS)
    paper = {f.name: f for f in form.FIELDS}
    assert [c[0] for c in paper["background"].choices] == list(spec.BACKGROUNDS)
    assert [c[0] for c in paper["border_style"].choices] == list(spec.BORDER_STYLES)
    assert by_name["font"].choices[0][2]  # fonts come grouped by category


def test_the_form_is_in_the_options_and_is_plain_json():
    options = json.loads(api.options())
    assert options["form"] == json.loads(json.dumps(form.describe()))
    assert [t["id"] for t in options["form"]["tabs"]] == ["layers", "doodle"]
    assert options["layers"]["defaults"]["text"]["font"] == spec.DEFAULT_FONT and options["layers"]["max"] == layers.MAX_LAYERS


def test_the_layer_list_and_the_doodle_are_placed_by_the_schema_and_drawn_by_the_client():
    assert next(f for f in form.FIELDS if f.kind == "layers").tab == "layers"
    assert next(f for f in form.FIELDS if f.kind == "doodle").tab == "doodle"
    assert next(f for f in form.LAYER_FIELDS if f.kind == "image").name == "path"


@pytest.mark.parametrize("field, value", [("text", "hi"), ("qr", "https://x"), ("image_path", "/tmp/p.png"), ("doodle", "AAAA")])
def test_each_kind_of_content_counts_as_something_to_print(field, value):
    assert spec.has_content(spec.LabelSpec(**{field: value}))


def test_nothing_to_print_means_none_of_them_and_blank_text_does_not_count():
    assert not spec.has_content(spec.LabelSpec())
    assert not spec.has_content(spec.LabelSpec(text="  \n", qr=" "))
    assert not spec.has_content(spec.LabelSpec(border=True, background="stars", bars=True))  # decoration alone is not content


def test_the_web_page_reads_the_content_fields_from_the_engine():
    assert json.loads(api.options())["content_fields"] == list(spec.CONTENT_FIELDS)
    assert set(spec.CONTENT_FIELDS) <= set(spec.LabelSpec.__dataclass_fields__)


def test_hints_say_when_image_only_drops_the_text():  # (only an old, unmigrated label can have this layout)
    assert api.hints({"text": "hi"}) == []
    hint = api.hints({"text": "hi", "image_path": "x.png"})
    assert len(hint) == 1 and "text isn't printed" in hint[0]
    assert api.hints({"text": "hi", "image_path": "x.png", "image_layout": "left"}) == []


def test_migrate_turns_an_old_label_into_layers_that_draw_the_same():
    old = {"text": "Hi", "qr": "https://example.com", "stickers": '[["star",100,60,2]]', "background": "dots", "border": True}
    moved = json.loads(api.migrate(old))
    assert moved["text"] == "" and moved["qr"] == "" and moved["stickers"] == ""  # the old fields are emptied
    assert moved["background"] == "dots" and moved["border"] is True  # the paper stays
    assert [layer.t for layer in layers.parse(moved["layers"])] == ["qr", "text", "sticker"]
    assert api.preview_pixels(old) == api.preview_pixels(moved)
    assert api.migrate(moved) == json.dumps(moved)  # idempotent
