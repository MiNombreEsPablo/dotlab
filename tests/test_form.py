import json

import pytest

from dotlab import api, form, spec


def test_every_field_is_a_real_spec_field_with_valid_choices():
    names = {f for f in spec.LabelSpec.__dataclass_fields__}
    for field in form.FIELDS:
        assert field.name in names, field.name
        assert field.tab == form.OUTPUT or field.tab in {t.id for t in form.TABS}, field.name
        if field.toggle:
            assert isinstance(getattr(spec.LabelSpec(), field.toggle), bool)
        if field.kind == "choice":
            assert field.choices and all(len(c) == 3 for c in field.choices)
        if field.kind == "number":
            assert field.minimum <= getattr(spec.LabelSpec(), field.name) <= field.maximum
        if field.kind == "slider":
            default = getattr(spec.LabelSpec(), field.name)
            assert field.minimum <= (field.default if default is None else default) <= field.maximum, field.name
            if field.scale == "log":
                assert field.minimum < field.neutral < field.maximum
        for rule in (field.show_when, field.enable_when):
            if rule:  # the field a rule watches exists, is a choice, and the values are among its choices
                watched = next(f for f in form.FIELDS if f.name == rule[0])
                assert watched.kind == "choice" and set(rule[1]) <= {c[0] for c in watched.choices}, field.name
        if field.gate:  # the gate's value is a choice and the field it sends is a slider
            assert field.gate in {c[0] for c in field.choices}
            assert next(f for f in form.FIELDS if f.name == field.gate).kind == "slider"


def test_every_spec_field_has_a_control_or_is_listed_as_pending():
    """The drift guard: a new LabelSpec field must be described in form.py (or admitted in PENDING) before it ships,
    so no client can quietly lack a control for it."""
    names = set(spec.LabelSpec.__dataclass_fields__)
    assert not (form.covered() & form.PENDING), "described and pending at once"
    assert names == form.covered() | form.PENDING, sorted(names ^ (form.covered() | form.PENDING))


def test_choices_follow_spec_so_a_new_effect_needs_no_ui_change():
    by_name = {f.name: f for f in form.FIELDS}
    assert [c[0] for c in by_name["effect"].choices] == list(spec.EFFECTS)
    assert [c[0] for c in by_name["background"].choices] == list(spec.BACKGROUNDS)
    assert [c[0] for c in by_name["border_style"].choices] == list(spec.BORDER_STYLES)
    assert by_name["font"].choices[0][2]  # fonts come grouped by category


def test_the_form_is_in_the_options_and_is_plain_json():
    options = json.loads(api.options())
    assert options["form"] == json.loads(json.dumps(form.describe()))
    assert [t["id"] for t in options["form"]["tabs"]] == ["content", "text", "image", "decoration", "doodle"]


def test_hints_say_when_image_only_drops_the_text():
    assert api.hints({"text": "hi"}) == []
    hint = api.hints({"text": "hi", "image_path": "x.png"})
    assert len(hint) == 1 and "text isn't printed" in hint[0] and "Image tab" in hint[0]
    assert api.hints({"text": "hi", "image_path": "x.png", "image_layout": "left"}) == []


def test_the_image_tab_waits_for_a_picture_and_resets_only_its_own_fields():
    tabs = {t.id: t for t in form.TABS}
    image = tabs["image"]
    assert image.needs == "image_path" and "Content tab" in image.needs_hint
    by_tab = {f.name for f in form.FIELDS if f.tab == "image"}
    assert set(image.reset) == by_tab  # Reset puts back everything on the tab, and nothing else
    assert "image_path" not in image.reset


def test_the_picture_chooser_is_placed_by_the_schema_and_drawn_by_the_client():
    chooser = next(f for f in form.FIELDS if f.kind == "image")
    assert chooser.name == "image_path" and chooser.tab == "content"


def test_the_doodle_is_the_last_control_to_get_a_place_in_the_schema():
    assert form.PENDING == frozenset({"layers"})  # until the layer list and inspector exist
    assert next(f for f in form.FIELDS if f.kind == "doodle").tab == "doodle"


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
