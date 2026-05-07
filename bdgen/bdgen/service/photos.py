"""Per-entity reference photos (characters, locations, objects).

The three entity kinds share an identical workflow: validate the id, load and
normalize the input image (PNG, RGB, downscaled to a max side), atomically
write it into ``<kind>_photos/<id>.png``, and mark any pre-existing reference
PNG as stale. The kind-specific public wrappers below are thin shims around
the internal ``_save_photo`` / ``_list_photos`` / ``_delete_photo`` helpers.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from ..models import BdGenInput, BdGenScript
from .constants import (
    CHARACTER_PHOTO_MAX_SIDE,
    CHARACTER_PHOTOS_DIRNAME,
    LOCATION_PHOTO_MAX_SIDE,
    LOCATION_PHOTOS_DIRNAME,
    OBJECT_PHOTO_MAX_SIDE,
    OBJECT_PHOTOS_DIRNAME,
    UPSCALED_DIRNAME,
)
from .indices import mark_stale

PhotoKind = Literal["character", "location", "object"]

_DIRNAME_BY_KIND: dict[PhotoKind, str] = {
    "character": CHARACTER_PHOTOS_DIRNAME,
    "location": LOCATION_PHOTOS_DIRNAME,
    "object": OBJECT_PHOTOS_DIRNAME,
}

_MAX_SIDE_BY_KIND: dict[PhotoKind, int] = {
    "character": CHARACTER_PHOTO_MAX_SIDE,
    "location": LOCATION_PHOTO_MAX_SIDE,
    "object": OBJECT_PHOTO_MAX_SIDE,
}

_REFS_SUBDIR_BY_KIND: dict[PhotoKind, str] = {
    "character": "characters",
    "location": "locations",
    "object": "objects",
}

_LABEL_BY_KIND: dict[PhotoKind, str] = {
    "character": "character_id",
    "location": "location_id",
    "object": "object_id",
}


# --- Internal kind-agnostic helpers ---


def _photo_path(proj_dir: Path, kind: PhotoKind, entity_id: str) -> Path:
    return proj_dir / _DIRNAME_BY_KIND[kind] / f"{entity_id}.png"


def _get_photo_path(proj_dir: Path, kind: PhotoKind, entity_id: str) -> Path | None:
    p = _photo_path(proj_dir, kind, entity_id)
    return p if p.exists() and p.stat().st_size > 0 else None


def _list_photos(proj_dir: Path, kind: PhotoKind) -> dict[str, Path]:
    d = proj_dir / _DIRNAME_BY_KIND[kind]
    if not d.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
            out[p.stem] = p
    return out


def _save_photo(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    image_bytes: bytes,
    output_root: Path | None,
) -> Path:
    from PIL import Image

    from .lifecycle import get_project_dir

    label = _LABEL_BY_KIND[kind]
    if not entity_id or "/" in entity_id or "\\" in entity_id:
        raise ValueError(f"{label} invalide.")
    if not image_bytes:
        raise ValueError("Image vide.")

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Image illisible : {e}")

    if img.mode != "RGB":
        img = img.convert("RGB")

    max_side = _MAX_SIDE_BY_KIND[kind]
    longest = max(img.size)
    if longest > max_side:
        scale = max_side / longest
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    proj_dir = get_project_dir(name, output_root)
    photos_dir = proj_dir / _DIRNAME_BY_KIND[kind]
    photos_dir.mkdir(parents=True, exist_ok=True)
    p = photos_dir / f"{entity_id}.png"
    tmp = p.with_suffix(p.suffix + ".tmp")
    img.save(tmp, format="PNG", optimize=True)
    tmp.replace(p)

    # The on-disk reference PNG (if any) was generated without this photo and
    # no longer reflects the new constraint; flag it so the UI can offer a
    # one-click regeneration.
    ref_png = proj_dir / "references" / _REFS_SUBDIR_BY_KIND[kind] / f"{entity_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", entity_id)
    return p


def _delete_photo(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    output_root: Path | None,
) -> bool:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    p = _photo_path(proj_dir, kind, entity_id)
    if p.exists():
        p.unlink()
        ref_png = proj_dir / "references" / _REFS_SUBDIR_BY_KIND[kind] / f"{entity_id}.png"
        if ref_png.exists():
            mark_stale(proj_dir, "references", entity_id)
        return True
    return False


# --- Per-character public wrappers ---


def character_photo_path(proj_dir: Path, character_id: str) -> Path:
    """Return the canonical PNG path for a character photo (file may not exist)."""
    return _photo_path(proj_dir, "character", character_id)


def get_character_photo_path(proj_dir: Path, character_id: str) -> Path | None:
    return _get_photo_path(proj_dir, "character", character_id)


def list_character_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{character_id: path}`` for every existing character photo."""
    return _list_photos(proj_dir, "character")


def save_character_photo(
    name: str,
    character_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Save a per-character reference photo, normalized to PNG.

    Pillow handles the format/size normalization: the image is converted to
    RGB and downscaled so its longest side is at most ``CHARACTER_PHOTO_MAX_SIDE``
    pixels. This keeps the file small enough to be embedded in image-edit
    requests without affecting recognizability.
    """
    return _save_photo(name, "character", character_id, image_bytes, output_root)


def delete_character_photo(name: str, character_id: str, output_root: Path | None = None) -> bool:
    return _delete_photo(name, "character", character_id, output_root)


# --- Per-location public wrappers ---


def location_photo_path(proj_dir: Path, location_id: str) -> Path:
    """Return the canonical PNG path for a location photo (file may not exist)."""
    return _photo_path(proj_dir, "location", location_id)


def get_location_photo_path(proj_dir: Path, location_id: str) -> Path | None:
    return _get_photo_path(proj_dir, "location", location_id)


def list_location_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{location_id: path}`` for every existing location photo."""
    return _list_photos(proj_dir, "location")


def save_location_photo(
    name: str,
    location_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Save a per-location reference photo, normalized to PNG."""
    return _save_photo(name, "location", location_id, image_bytes, output_root)


def delete_location_photo(name: str, location_id: str, output_root: Path | None = None) -> bool:
    return _delete_photo(name, "location", location_id, output_root)


# --- Per-object public wrappers ---


def object_photo_path(proj_dir: Path, object_id: str) -> Path:
    """Return the canonical PNG path for an object photo (file may not exist)."""
    return _photo_path(proj_dir, "object", object_id)


def get_object_photo_path(proj_dir: Path, object_id: str) -> Path | None:
    return _get_photo_path(proj_dir, "object", object_id)


def list_object_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{object_id: path}`` for every existing object photo."""
    return _list_photos(proj_dir, "object")


def save_object_photo(
    name: str,
    object_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Save a per-object reference photo, normalized to PNG."""
    return _save_photo(name, "object", object_id, image_bytes, output_root)


def delete_object_photo(name: str, object_id: str, output_root: Path | None = None) -> bool:
    return _delete_photo(name, "object", object_id, output_root)


# --- Reference images on disk (independent of bd_script) ---


def list_reference_images(proj_dir: Path) -> dict[str, dict[str, Path]]:
    """Return ``{kind: {id: path}}`` for every existing reference PNG on disk.

    Independent of the bd_script: scans ``references/{kind}/*.png`` directly.
    Used by the project form so imported .bdrefs references show up even
    before the script step has run.
    """
    out: dict[str, dict[str, Path]] = {
        "characters": {},
        "locations": {},
        "objects": {},
    }
    base = proj_dir / "references"
    if not base.is_dir():
        return out
    for kind in out.keys():
        d = base / kind
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
                out[kind][p.stem] = p
    return out


# --- Upscale output dir ---


def get_upscale_output_dir(
    proj_dir: Path,
    bd_script: BdGenScript | None = None,
    config: BdGenInput | None = None,
) -> Path:
    if bd_script is not None and bd_script.generation_options is not None:
        out = bd_script.generation_options.upscale.output_dir
        if out is not None:
            return out
    if config is not None:
        out = config.generation_options.upscale.output_dir
        if out is not None:
            return out
    return proj_dir / UPSCALED_DIRNAME


def is_upscaled_stale(source_path: Path, upscaled_path: Path) -> bool:
    if not source_path.exists() or not upscaled_path.exists():
        return False
    return source_path.stat().st_mtime > upscaled_path.stat().st_mtime
