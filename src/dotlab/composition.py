"""Label files: a whole label design saved to / loaded from one self-contained PNG. Window-free.

The file is the label as it prints (a normal 1-bit PNG any viewer or editor opens), with the design stored inside it in
a compressed text chunk (`KEY`), so Dotlab can open it again and keep editing. If another program re-saves the PNG and
drops the chunk, what is left is still a good picture of the label. The design is JSON (unknown fields are ignored, a
newer format is refused) and embeds its image, so the file still works on another machine. Unlike a preset (which lives in
the app's config and only stores a path), nothing in it points at the author's disk.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from PIL import Image, PngImagePlugin

from . import doodle, stickers
from .render import PrinterError, label_bitmap
from .spec import IMAGE_SUFFIXES, LabelSpec

FORMAT = "dotlab-label"
KEY = "dotlab"  # the name of the PNG text chunk
VERSION = 1
SUFFIX = ".png"
# Pillow refuses text chunks over 1 MB by default; a design with a photo in it is bigger. The file is the user's own.
PngImagePlugin.MAX_TEXT_CHUNK = 64 * 1024 * 1024
PngImagePlugin.MAX_TEXT_MEMORY = 128 * 1024 * 1024


def dumps(spec: LabelSpec) -> bytes:
    """The PNG file's bytes: the printed sticker, with the design inside."""
    spec = replace(spec, doodle=doodle.canonical(spec.doodle), stickers=stickers.canonical(spec.stickers))  # compact, whichever client drew it
    try:
        picture = label_bitmap(spec)  # rendered with the real image path, before it is replaced by the embedded bytes
    except PrinterError:  # the picture is gone from disk: still save the design, with a preview that lacks it
        picture = label_bitmap(replace(spec, image_path=""))
    data = {"format": FORMAT, "version": VERSION, "spec": asdict(spec)}
    source = Path(spec.image_path) if spec.image_path else None
    if source and source.is_file():
        data["image"] = {"name": source.name, "data": base64.b64encode(source.read_bytes()).decode("ascii")}
        data["spec"]["image_path"] = ""  # a path on this machine means nothing in the file; the bytes travel instead
    info = PngImagePlugin.PngInfo()
    info.add_text(KEY, json.dumps(data, separators=(",", ":")), zip=True)
    out = io.BytesIO()
    picture.save(out, format="PNG", pnginfo=info)
    return out.getvalue()


def loads(blob: bytes, image_dir: Path | None = None) -> LabelSpec:
    """Read a label file. An embedded image is written under `image_dir` (default: a temp folder)."""
    try:
        picture = Image.open(io.BytesIO(blob))
        picture.load()  # text chunks that come after the pixels are only read now
    except (OSError, ValueError, SyntaxError) as e:  # Pillow's "cannot identify image file" is an OSError
        raise ValueError("not a label file (it isn't a PNG picture)") from e
    text = getattr(picture, "text", {}).get(KEY) if picture.format == "PNG" else None
    if not text:
        raise ValueError("this picture has no Dotlab label inside it (it is only an image)")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"the label inside this picture is damaged ({e.msg})") from e
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("spec"), dict):
        raise ValueError("not a Dotlab label file")
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        raise ValueError("this file was made by a newer version of Dotlab")
    spec = LabelSpec.from_dict(data["spec"])
    image = data.get("image")
    if isinstance(image, dict):
        try:
            embedded = base64.b64decode(image.get("data", ""), validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("the embedded image is damaged") from e
        spec.image_path = str(_store_image(str(image.get("name", "")), embedded, image_dir))
    return spec


def _store_image(name: str, blob: bytes, folder: Path | None) -> Path:
    folder = folder or Path(tempfile.gettempdir()) / "dotlab" / "compositions"
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:40] or "image"
    # The content hash in the name keeps it unique and stable, and nothing from the file picks the directory.
    path = folder / f"{hashlib.sha256(blob).hexdigest()[:12]}-{stem}{suffix if suffix in IMAGE_SUFFIXES else '.png'}"
    if not path.exists():
        path.write_bytes(blob)
    return path


def save(path: Path | str, spec: LabelSpec) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(dumps(spec))
    tmp.replace(path)


def load(path: Path | str, image_dir: Path | None = None) -> LabelSpec:
    return loads(Path(path).read_bytes(), image_dir)
