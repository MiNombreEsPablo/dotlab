"""Named label presets, stored as JSON under the XDG config dir. Qt-free."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .spec import LabelSpec


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "dotlab" / "presets.json"


NAME_MAX = 60


def clean_name(name: str) -> str:
    """A preset name as it will be kept: trimmed, one line, not empty, not too long. ValueError with a sentence if not."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("Give the preset a name.")
    if len(name) > NAME_MAX:
        raise ValueError(f"A preset name can be up to {NAME_MAX} characters.")
    return name


class PresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def _read(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def names(self) -> list[str]:
        return sorted(self._read(), key=str.casefold)

    def get(self, name: str) -> LabelSpec | None:
        raw = self._read().get(name)
        if raw is None:
            return None
        return LabelSpec.from_dict(raw) if isinstance(raw, dict) else None

    def save(self, name: str, spec: LabelSpec) -> None:
        data = self._read()
        data[name] = asdict(spec)
        self._write(data)

    def delete(self, name: str) -> None:
        data = self._read()
        if data.pop(name, None) is not None:
            self._write(data)
