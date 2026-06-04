"""Per-entity reference photos (characters, locations, objects).

Storage (per entity):
  New format:  {kind}_photos/{entity_id}/{slot}.png  (slot = integer, 1-based)
  Legacy:      {kind}_photos/{entity_id}.png          (treated as virtual slot 1)

Both formats coexist; new photos are always written to the subdirectory.
On first addition, any existing flat file is migrated into slot 1 of the
subdirectory so the entity has a single canonical layout.
"""

from __future__ import annotations

import shutil
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


# --- Path helpers ---


def _photos_dir(proj_dir: Path, kind: PhotoKind) -> Path:
    return proj_dir / _DIRNAME_BY_KIND[kind]


def _entity_dir(proj_dir: Path, kind: PhotoKind, entity_id: str) -> Path:
    """Subdirectory holding numbered slots for one entity (new format)."""
    return proj_dir / _DIRNAME_BY_KIND[kind] / entity_id


def _entity_slot_path(proj_dir: Path, kind: PhotoKind, entity_id: str, slot: int) -> Path:
    return proj_dir / _DIRNAME_BY_KIND[kind] / entity_id / f"{slot}.png"


def _legacy_photo_path(proj_dir: Path, kind: PhotoKind, entity_id: str) -> Path:
    """Old flat-file path kept for backward compat."""
    return proj_dir / _DIRNAME_BY_KIND[kind] / f"{entity_id}.png"


# --- Internal kind-agnostic helpers ---


def _list_entity_photos(proj_dir: Path, kind: PhotoKind, entity_id: str) -> list[tuple[int, Path]]:
    """Return all photos for one entity as [(slot, path)], sorted by slot.

    Checks the new subdirectory format first, then falls back to the legacy
    flat file (which maps to virtual slot 1).
    """
    entity_dir = _entity_dir(proj_dir, kind, entity_id)
    if entity_dir.is_dir():
        results: list[tuple[int, Path]] = []
        for p in entity_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
                try:
                    slot = int(p.stem)
                    results.append((slot, p))
                except ValueError:
                    pass
        return sorted(results, key=lambda x: x[0])
    flat = _legacy_photo_path(proj_dir, kind, entity_id)
    if flat.exists() and flat.stat().st_size > 0:
        return [(1, flat)]
    return []


def _list_photos_with_slots(proj_dir: Path, kind: PhotoKind) -> dict[str, list[tuple[int, Path]]]:
    """Return {entity_id: [(slot, path), ...]} sorted by slot for all entities."""
    d = _photos_dir(proj_dir, kind)
    if not d.is_dir():
        return {}

    out: dict[str, list[tuple[int, Path]]] = {}

    for item in d.iterdir():
        if item.is_dir():
            entity_id = item.name
            for p in item.iterdir():
                if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
                    try:
                        slot = int(p.stem)
                        out.setdefault(entity_id, []).append((slot, p))
                    except ValueError:
                        pass
        elif item.is_file() and item.suffix.lower() == ".png" and item.stat().st_size > 0:
            # Legacy flat file — only if not already covered by a subdirectory
            entity_id = item.stem
            if entity_id not in out:
                out[entity_id] = [(1, item)]

    return {eid: sorted(slots, key=lambda x: x[0]) for eid, slots in out.items()}


def _list_photos(proj_dir: Path, kind: PhotoKind) -> dict[str, list[Path]]:
    """Return {entity_id: [path, ...]} ordered by slot for all entities."""
    return {eid: [p for _, p in slots] for eid, slots in _list_photos_with_slots(proj_dir, kind).items()}


def _validate_entity_id(kind: PhotoKind, entity_id: str) -> None:
    if not entity_id or "/" in entity_id or "\\" in entity_id or entity_id.startswith("."):
        raise ValueError(f"{_LABEL_BY_KIND[kind]} invalide.")


def _process_image(image_bytes: bytes, kind: PhotoKind):
    from PIL import Image

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
    return img


def _write_image(img, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    img.save(tmp, format="PNG", optimize=True)
    tmp.replace(dest)


def _mark_ref_stale(proj_dir: Path, kind: PhotoKind, entity_id: str) -> None:
    ref_png = proj_dir / "references" / _REFS_SUBDIR_BY_KIND[kind] / f"{entity_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", entity_id)


def _add_photo(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    image_bytes: bytes,
    output_root: Path | None,
) -> tuple[int, Path]:
    """Append a new photo for the entity. Returns (slot, path).

    Migrates any existing legacy flat file into slot 1 of the new subdirectory
    format on first call so the entity has a single canonical layout.
    """
    from .lifecycle import get_project_dir

    _validate_entity_id(kind, entity_id)
    img = _process_image(image_bytes, kind)
    proj_dir = get_project_dir(name, output_root)
    entity_dir = _entity_dir(proj_dir, kind, entity_id)

    # Migrate legacy flat file into subdirectory.
    flat = _legacy_photo_path(proj_dir, kind, entity_id)
    if flat.exists() and not entity_dir.is_dir():
        entity_dir.mkdir(parents=True, exist_ok=True)
        flat.rename(entity_dir / "1.png")

    entity_dir.mkdir(parents=True, exist_ok=True)

    existing_slots: list[int] = []
    for p in entity_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".png":
            try:
                existing_slots.append(int(p.stem))
            except ValueError:
                pass
    slot = max(existing_slots, default=0) + 1

    dest = entity_dir / f"{slot}.png"
    _write_image(img, dest)
    _mark_ref_stale(proj_dir, kind, entity_id)
    return slot, dest


def _save_photo(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    image_bytes: bytes,
    output_root: Path | None,
) -> Path:
    """Replace ALL photos for the entity with a single new one (slot 1).

    Used by the legacy PUT endpoint so existing clients keep working as before.
    """
    from .lifecycle import get_project_dir

    _validate_entity_id(kind, entity_id)
    img = _process_image(image_bytes, kind)
    proj_dir = get_project_dir(name, output_root)

    _remove_all_entity_photos(proj_dir, kind, entity_id)

    entity_dir = _entity_dir(proj_dir, kind, entity_id)
    entity_dir.mkdir(parents=True, exist_ok=True)
    dest = entity_dir / "1.png"
    _write_image(img, dest)
    _mark_ref_stale(proj_dir, kind, entity_id)
    return dest


def _delete_photo_slot(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    slot: int,
    output_root: Path | None,
) -> bool:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    p = _entity_slot_path(proj_dir, kind, entity_id, slot)
    if p.exists():
        p.unlink()
        _mark_ref_stale(proj_dir, kind, entity_id)
        return True
    # Legacy format: slot 1 maps to the flat file.
    if slot == 1:
        flat = _legacy_photo_path(proj_dir, kind, entity_id)
        if flat.exists():
            flat.unlink()
            _mark_ref_stale(proj_dir, kind, entity_id)
            return True
    return False


def _delete_photo(
    name: str,
    kind: PhotoKind,
    entity_id: str,
    output_root: Path | None,
) -> bool:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    removed = _remove_all_entity_photos(proj_dir, kind, entity_id)
    if removed:
        _mark_ref_stale(proj_dir, kind, entity_id)
    return removed


def _remove_all_entity_photos(proj_dir: Path, kind: PhotoKind, entity_id: str) -> bool:
    """Remove all photos for one entity from disk (both formats). Returns True if anything was removed."""
    removed = False
    entity_dir = _entity_dir(proj_dir, kind, entity_id)
    if entity_dir.is_dir():
        shutil.rmtree(entity_dir, ignore_errors=True)
        removed = True
    flat = _legacy_photo_path(proj_dir, kind, entity_id)
    if flat.exists():
        flat.unlink()
        removed = True
    return removed


# --- Per-character public wrappers ---


def character_photo_path(proj_dir: Path, character_id: str) -> Path:
    """Return the legacy flat-file path (may not exist). Use remove_all_character_photos() to delete."""
    return _legacy_photo_path(proj_dir, "character", character_id)


def get_character_photo_path(proj_dir: Path, character_id: str) -> Path | None:
    """Return the first existing photo path for a character, or None."""
    photos = _list_entity_photos(proj_dir, "character", character_id)
    return photos[0][1] if photos else None


def list_character_photos(proj_dir: Path) -> dict[str, list[Path]]:
    """Return {character_id: [path, ...]} for every existing character photo."""
    return _list_photos(proj_dir, "character")


def list_character_photos_with_slots(proj_dir: Path) -> dict[str, list[tuple[int, Path]]]:
    """Return {character_id: [(slot, path), ...]} for every existing character photo."""
    return _list_photos_with_slots(proj_dir, "character")


def save_character_photo(
    name: str,
    character_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Replace all photos for this character with a single new one (legacy PUT behavior)."""
    return _save_photo(name, "character", character_id, image_bytes, output_root)


def add_character_photo(
    name: str,
    character_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> tuple[int, Path]:
    """Append a new photo to the character's photo list. Returns (slot, path)."""
    return _add_photo(name, "character", character_id, image_bytes, output_root)


def delete_character_photo(name: str, character_id: str, output_root: Path | None = None) -> bool:
    """Remove all photos for this character."""
    return _delete_photo(name, "character", character_id, output_root)


def delete_character_photo_slot(name: str, character_id: str, slot: int, output_root: Path | None = None) -> bool:
    """Remove the character photo at the given slot. Returns True if deleted."""
    return _delete_photo_slot(name, "character", character_id, slot, output_root)


def remove_all_character_photos(proj_dir: Path, character_id: str) -> bool:
    """Remove all character photos from disk. Used by cascades on entity deletion."""
    return _remove_all_entity_photos(proj_dir, "character", character_id)


# --- Per-location public wrappers ---


def location_photo_path(proj_dir: Path, location_id: str) -> Path:
    return _legacy_photo_path(proj_dir, "location", location_id)


def get_location_photo_path(proj_dir: Path, location_id: str) -> Path | None:
    photos = _list_entity_photos(proj_dir, "location", location_id)
    return photos[0][1] if photos else None


def list_location_photos(proj_dir: Path) -> dict[str, list[Path]]:
    return _list_photos(proj_dir, "location")


def list_location_photos_with_slots(proj_dir: Path) -> dict[str, list[tuple[int, Path]]]:
    return _list_photos_with_slots(proj_dir, "location")


def save_location_photo(
    name: str,
    location_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    return _save_photo(name, "location", location_id, image_bytes, output_root)


def add_location_photo(
    name: str,
    location_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> tuple[int, Path]:
    return _add_photo(name, "location", location_id, image_bytes, output_root)


def delete_location_photo(name: str, location_id: str, output_root: Path | None = None) -> bool:
    return _delete_photo(name, "location", location_id, output_root)


def delete_location_photo_slot(name: str, location_id: str, slot: int, output_root: Path | None = None) -> bool:
    return _delete_photo_slot(name, "location", location_id, slot, output_root)


def remove_all_location_photos(proj_dir: Path, location_id: str) -> bool:
    return _remove_all_entity_photos(proj_dir, "location", location_id)


# --- Per-object public wrappers ---


def object_photo_path(proj_dir: Path, object_id: str) -> Path:
    return _legacy_photo_path(proj_dir, "object", object_id)


def get_object_photo_path(proj_dir: Path, object_id: str) -> Path | None:
    photos = _list_entity_photos(proj_dir, "object", object_id)
    return photos[0][1] if photos else None


def list_object_photos(proj_dir: Path) -> dict[str, list[Path]]:
    return _list_photos(proj_dir, "object")


def list_object_photos_with_slots(proj_dir: Path) -> dict[str, list[tuple[int, Path]]]:
    return _list_photos_with_slots(proj_dir, "object")


def save_object_photo(
    name: str,
    object_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    return _save_photo(name, "object", object_id, image_bytes, output_root)


def add_object_photo(
    name: str,
    object_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> tuple[int, Path]:
    return _add_photo(name, "object", object_id, image_bytes, output_root)


def delete_object_photo(name: str, object_id: str, output_root: Path | None = None) -> bool:
    return _delete_photo(name, "object", object_id, output_root)


def delete_object_photo_slot(name: str, object_id: str, slot: int, output_root: Path | None = None) -> bool:
    return _delete_photo_slot(name, "object", object_id, slot, output_root)


def remove_all_object_photos(proj_dir: Path, object_id: str) -> bool:
    return _remove_all_entity_photos(proj_dir, "object", object_id)


# --- Reference images on disk (independent of bd_script) ---


def list_reference_images(proj_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {kind: {id: path}} for every existing reference PNG on disk."""
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
