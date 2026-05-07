"""Cascading deletes — remove an entity and drop the pages that referenced it.

Each ``delete_*_and_cascade`` removes the entity from the script, truncates
the script from the earliest page that referenced it, deletes the entity's
on-disk reference PNG and photo, and clears its quality/stale entries. The
caller is then expected to relaunch ``run_step_script`` to regenerate the
dropped pages without that entity.
"""

from __future__ import annotations

from pathlib import Path

from .. import script as script_module
from ..models import BdGenScript
from .indices import (
    clear_stale,
    mark_script_coherence_dirty,
    read_quality_index,
    write_quality_index,
)
from .photos import character_photo_path, location_photo_path, object_photo_path


def _earliest_page_using_character(bd_script: BdGenScript, character_id: str) -> int | None:
    for p in sorted(bd_script.pages, key=lambda x: x.page_number):
        for panel in p.panels:
            if character_id in panel.characters:
                return p.page_number
            if any(d.speaker == character_id for d in panel.dialogs):
                return p.page_number
    return None


def _earliest_page_using_location(bd_script: BdGenScript, location_id: str) -> int | None:
    for p in sorted(bd_script.pages, key=lambda x: x.page_number):
        for panel in p.panels:
            if panel.location == location_id:
                return p.page_number
    return None


def _earliest_page_using_object(bd_script: BdGenScript, object_id: str) -> int | None:
    for p in sorted(bd_script.pages, key=lambda x: x.page_number):
        for panel in p.panels:
            if object_id in panel.objects:
                return p.page_number
    return None


def delete_character_and_cascade(name: str, character_id: str, output_root: Path | None = None) -> dict:
    """Remove a character from the script and drop all pages from the
    earliest one that referenced them. Pages 1..(earliest-1) stay intact.

    The caller is expected to relaunch ``run_step_script`` afterwards so the
    pipeline regenerates the dropped pages without that character.

    Returns ``{deleted, character_id, earliest_affected, pages_dropped}``.
    The reference-sheet PNG (if any) is also removed so a future references
    run won't surface a stale image.
    """
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    target = bd_script.character_by_id(character_id)
    if target is None:
        raise ValueError(f"Personnage inconnu : {character_id}")

    earliest = _earliest_page_using_character(bd_script, character_id)
    pages_dropped = 0
    if earliest is not None:
        pages_dropped = script_module.truncate_pages_from(bd_script, earliest)

    bd_script.characters = [c for c in bd_script.characters if c.id != character_id]
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)

    # Tidy: drop the character's reference image and quality-index entry
    # so the references step doesn't show an orphan asset.
    ref_png = proj_dir / "references" / "characters" / f"{character_id}.png"
    if ref_png.exists():
        ref_png.unlink()
    photo_png = character_photo_path(proj_dir, character_id)
    if photo_png.exists():
        photo_png.unlink()
    qidx = read_quality_index(proj_dir)
    if character_id in qidx.get("references", {}):
        qidx["references"].pop(character_id, None)
        write_quality_index(proj_dir, qidx)
    clear_stale(proj_dir, "references", character_id)

    return {
        "deleted": True,
        "character_id": character_id,
        "earliest_affected": earliest,
        "pages_dropped": pages_dropped,
    }


def delete_location_and_cascade(name: str, location_id: str, output_root: Path | None = None) -> dict:
    """Symmetric of ``delete_character_and_cascade`` for locations."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    target = bd_script.location_by_id(location_id)
    if target is None:
        raise ValueError(f"Décor inconnu : {location_id}")

    earliest = _earliest_page_using_location(bd_script, location_id)
    pages_dropped = 0
    if earliest is not None:
        pages_dropped = script_module.truncate_pages_from(bd_script, earliest)

    bd_script.locations = [l for l in bd_script.locations if l.id != location_id]
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)

    ref_png = proj_dir / "references" / "locations" / f"{location_id}.png"
    if ref_png.exists():
        ref_png.unlink()
    photo_png = location_photo_path(proj_dir, location_id)
    if photo_png.exists():
        photo_png.unlink()
    qidx = read_quality_index(proj_dir)
    if location_id in qidx.get("references", {}):
        qidx["references"].pop(location_id, None)
        write_quality_index(proj_dir, qidx)
    clear_stale(proj_dir, "references", location_id)

    return {
        "deleted": True,
        "location_id": location_id,
        "earliest_affected": earliest,
        "pages_dropped": pages_dropped,
    }


def delete_object_and_cascade(name: str, object_id: str, output_root: Path | None = None) -> dict:
    """Symmetric of ``delete_character_and_cascade`` for objects."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    target = bd_script.object_by_id(object_id)
    if target is None:
        raise ValueError(f"Objet inconnu : {object_id}")

    earliest = _earliest_page_using_object(bd_script, object_id)
    pages_dropped = 0
    if earliest is not None:
        pages_dropped = script_module.truncate_pages_from(bd_script, earliest)

    bd_script.objects = [o for o in bd_script.objects if o.id != object_id]
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)

    ref_png = proj_dir / "references" / "objects" / f"{object_id}.png"
    if ref_png.exists():
        ref_png.unlink()
    photo_png = object_photo_path(proj_dir, object_id)
    if photo_png.exists():
        photo_png.unlink()
    qidx = read_quality_index(proj_dir)
    if object_id in qidx.get("references", {}):
        qidx["references"].pop(object_id, None)
        write_quality_index(proj_dir, qidx)
    clear_stale(proj_dir, "references", object_id)

    return {
        "deleted": True,
        "object_id": object_id,
        "earliest_affected": earliest,
        "pages_dropped": pages_dropped,
    }


def preview_delete_character(name: str, character_id: str, output_root: Path | None = None) -> dict:
    """Return what would happen on delete, without performing it."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.character_by_id(character_id) is None:
        raise ValueError(f"Personnage inconnu : {character_id}")
    earliest = _earliest_page_using_character(bd_script, character_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}


def preview_delete_location(name: str, location_id: str, output_root: Path | None = None) -> dict:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.location_by_id(location_id) is None:
        raise ValueError(f"Décor inconnu : {location_id}")
    earliest = _earliest_page_using_location(bd_script, location_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}


def preview_delete_object(name: str, object_id: str, output_root: Path | None = None) -> dict:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.object_by_id(object_id) is None:
        raise ValueError(f"Objet inconnu : {object_id}")
    earliest = _earliest_page_using_object(bd_script, object_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}
