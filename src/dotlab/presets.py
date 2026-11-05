"""Preset names. The presets themselves live in the browser's storage (web/presets/local.js); this keeps the one rule the
page and the engine share: what a preset's name may be."""
from __future__ import annotations

NAME_MAX = 60


def clean_name(name: str) -> str:
    """A preset name as it will be kept: trimmed, one line, not empty, not too long. ValueError with a sentence if not."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("Give the preset a name.")
    if len(name) > NAME_MAX:
        raise ValueError(f"A preset name can be up to {NAME_MAX} characters.")
    return name
