"""Manual script edits made through the UI.

Each function validates the payload via Pydantic, persists the change to
``bdgen-script.json``, marks the coherence index dirty, and flags any
downstream PNG (reference or composed page) as stale so the UI can offer a
one-click regeneration.
"""

from __future__ import annotations

from pathlib import Path

from ..models import (
    BackCover,
    BdGenScript,
    Cover,
    Page,
    ScriptCharacter,
    ScriptLocation,
    ScriptObject,
)
from .indices import mark_script_coherence_dirty, mark_stale


def update_script_page_manual(
    name: str,
    page_number: int,
    page_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited script page and mark its composed image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    idx = next(
        (i for i, page in enumerate(bd_script.pages) if page.page_number == page_number),
        None,
    )
    if idx is None:
        raise RuntimeError(f"Planche inconnue : {page_number}")
    page = Page.model_validate(page_payload)
    if page.page_number != page_number:
        raise RuntimeError("Le numero de planche ne peut pas etre modifie.")
    bd_script.pages[idx] = page
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    composed = proj_dir / "pages" / f"page_{page_number:02d}.png"
    if composed.exists():
        mark_stale(proj_dir, "compose", f"page_{page_number}")
    return bd_script


def _validate_new_script_item_id(item_id: str, existing_ids: set[str], label: str) -> None:
    clean_id = item_id.strip()
    if not clean_id:
        raise RuntimeError(f"L'id du {label} est obligatoire.")
    if clean_id != item_id:
        raise RuntimeError(f"L'id du {label} ne doit pas commencer ou finir par un espace.")
    if any(sep in item_id for sep in ("/", "\\")):
        raise RuntimeError(f"L'id du {label} ne doit pas contenir de separateur de chemin.")
    if item_id in existing_ids:
        raise RuntimeError(f"Un {label} utilise deja l'id : {item_id}")


def add_script_character_manual(
    name: str,
    character_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Append a manually created character to the script."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    character = ScriptCharacter.model_validate(character_payload)
    _validate_new_script_item_id(character.id, {item.id for item in bd_script.characters}, "personnage")
    bd_script.characters.append(character)
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    return bd_script


def update_script_character_manual(
    name: str,
    character_id: str,
    character_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited character and mark its reference image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    idx = next((i for i, character in enumerate(bd_script.characters) if character.id == character_id), None)
    if idx is None:
        raise RuntimeError(f"Personnage inconnu : {character_id}")
    character = ScriptCharacter.model_validate(character_payload)
    if character.id != character_id:
        raise RuntimeError("L'id du personnage ne peut pas etre modifie.")
    bd_script.characters[idx] = character
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    if (proj_dir / "references" / "characters" / f"{character_id}.png").exists():
        mark_stale(proj_dir, "references", character_id)
    return bd_script


def add_script_location_manual(
    name: str,
    location_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Append a manually created location to the script."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    location = ScriptLocation.model_validate(location_payload)
    _validate_new_script_item_id(location.id, {item.id for item in bd_script.locations}, "decor")
    bd_script.locations.append(location)
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    return bd_script


def update_script_location_manual(
    name: str,
    location_id: str,
    location_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited location and mark its reference image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    idx = next((i for i, location in enumerate(bd_script.locations) if location.id == location_id), None)
    if idx is None:
        raise RuntimeError(f"Decor inconnu : {location_id}")
    location = ScriptLocation.model_validate(location_payload)
    if location.id != location_id:
        raise RuntimeError("L'id du decor ne peut pas etre modifie.")
    bd_script.locations[idx] = location
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    if (proj_dir / "references" / "locations" / f"{location_id}.png").exists():
        mark_stale(proj_dir, "references", location_id)
    return bd_script


def add_script_object_manual(
    name: str,
    object_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Append a manually created object to the script."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    obj = ScriptObject.model_validate(object_payload)
    _validate_new_script_item_id(obj.id, {item.id for item in bd_script.objects}, "objet")
    bd_script.objects.append(obj)
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    return bd_script


def update_script_object_manual(
    name: str,
    object_id: str,
    object_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited object and mark its reference image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    idx = next((i for i, obj in enumerate(bd_script.objects) if obj.id == object_id), None)
    if idx is None:
        raise RuntimeError(f"Objet inconnu : {object_id}")
    obj = ScriptObject.model_validate(object_payload)
    if obj.id != object_id:
        raise RuntimeError("L'id de l'objet ne peut pas etre modifie.")
    bd_script.objects[idx] = obj
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    if (proj_dir / "references" / "objects" / f"{object_id}.png").exists():
        mark_stale(proj_dir, "references", object_id)
    return bd_script


def update_script_cover_manual(
    name: str,
    cover_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited cover and mark its composed image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    if bd_script.cover is None:
        raise RuntimeError("Couverture inconnue.")
    bd_script.cover = Cover.model_validate(cover_payload)
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    if (proj_dir / "pages" / "cover.png").exists():
        mark_stale(proj_dir, "compose", "cover")
    return bd_script


def update_script_back_cover_manual(
    name: str,
    back_cover_payload: dict,
    output_root: Path | None = None,
) -> BdGenScript:
    """Persist a manually edited back cover and mark its composed image stale."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    if bd_script.back_cover is None:
        raise RuntimeError("4e de couverture inconnue.")
    bd_script.back_cover = BackCover.model_validate(back_cover_payload)
    bd_script.save(script_path)
    mark_script_coherence_dirty(proj_dir)
    if (proj_dir / "pages" / "back.png").exists():
        mark_stale(proj_dir, "compose", "back")
    return bd_script
