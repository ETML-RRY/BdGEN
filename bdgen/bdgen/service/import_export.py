""".bdgen project archives and .bdrefs reference bundles."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..models import BdGenInput, BdGenScript
from .config import _force_writable_and_retry, load_config, save_config
from .constants import (
    CHARACTER_PHOTOS_DIRNAME,
    LOCATION_PHOTOS_DIRNAME,
    OBJECT_PHOTOS_DIRNAME,
    PROJECT_CONFIG_NAME,
)

BDGEN_EXTENSION = ".bdgen"
BDREFS_EXTENSION = ".bdrefs"
BDREFS_MANIFEST_NAME = "manifest.json"
BDREFS_MANIFEST_VERSION = 1


# --- .bdgen project import / export ---


def export_zip(name: str, output_root: Path | None = None) -> bytes:
    """Pack the project directory into a .bdgen (zip) blob."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in proj_dir.rglob("*"):
            if p.is_dir():
                continue
            arcname = p.relative_to(proj_dir.parent).as_posix()
            zf.write(p, arcname)
    return buf.getvalue()


def import_zip(
    blob: bytes,
    output_root: Path | None = None,
    overwrite: bool = False,
    new_project_id: str | None = None,
    new_title: str | None = None,
) -> str:
    """Extract a .bdgen blob into the output root. Returns the project name.

    The zip is expected to contain exactly one top-level folder which becomes
    the project name. If a project with the same name exists and ``overwrite``
    is False, a numeric suffix is appended.

    ``new_project_id`` and ``new_title`` let the caller override the slug and
    display name of the imported project respectively.
    """
    from .lifecycle import projects_root, _slugify, _next_available_name

    root = projects_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        if not names:
            raise ValueError("Archive vide.")
        top_levels = {n.split("/", 1)[0] for n in names if n.strip()}
        if len(top_levels) != 1:
            raise ValueError("Archive invalide : un unique dossier racine est attendu.")
        zip_folder = top_levels.pop()

        # Determine desired slug (user override > title-derived > zip folder)
        if new_project_id and new_project_id.strip():
            desired = _slugify(new_project_id) or "projet"
        elif new_title and new_title.strip():
            desired = _slugify(new_title) or "projet"
        else:
            desired = zip_folder

        project_name = _next_available_name(desired, root) if not overwrite else desired
        target_dir = root / project_name

        if target_dir.exists() and overwrite:
            shutil.rmtree(target_dir, onerror=_force_writable_and_retry)

        if project_name == zip_folder:
            # No rename needed — simple extractall
            target_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(root)
        else:
            # Extract with folder rename
            for member in zf.infolist():
                rel = member.filename.split("/", 1)[1] if "/" in member.filename else ""
                if not rel:
                    continue
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not member.is_dir():
                    dest.write_bytes(zf.read(member))

    # Normalize config so it is portable and reflects the user's choices.
    cfg_path = root / project_name / PROJECT_CONFIG_NAME
    if cfg_path.exists():
        try:
            config = BdGenInput.load(cfg_path)
            config.project = project_name
            if new_title and new_title.strip():
                config.display_name = new_title.strip()
            save_config(config, root)
        except Exception:
            pass
    script_path = root / project_name / "bdgen-script.json"
    if script_path.exists():
        try:
            bd_script = BdGenScript.load(script_path)
            bd_script.project = project_name
            bd_script.save(script_path)
        except Exception:
            pass
    return project_name


# --- .bdrefs references bundle (share a cast across projects) ---


def _entity_kinds_map(config: BdGenInput) -> dict[str, dict[str, dict]]:
    """Index config entities by kind → id → entry dict.

    Each entry is the full pydantic dump (id, name, description, ...) so it
    can be re-validated by the destination project on import.
    """
    return {
        "characters": {c.id: c.model_dump(mode="json") for c in config.characters},
        "locations": {l.id: l.model_dump(mode="json") for l in config.locations},
        "objects": {o.id: o.model_dump(mode="json") for o in config.objects},
    }


def _entities_for_kind(config: BdGenInput, kind: str) -> list[dict]:
    if kind == "characters":
        return [c.model_dump(mode="json") for c in config.characters]
    if kind == "locations":
        return [l.model_dump(mode="json") for l in config.locations]
    if kind == "objects":
        return [o.model_dump(mode="json") for o in config.objects]
    return []


def list_exportable_references(name: str, output_root: Path | None = None) -> dict[str, list[dict]]:
    """Return entities that have a reference PNG on disk, keyed by kind.

    Used by the export UI to populate its picker. Entries the user can pick
    must have BOTH a config row and a non-empty PNG under ``references/``.
    """
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")
    config = load_config(name, output_root)
    out: dict[str, list[dict]] = {"characters": [], "locations": [], "objects": []}
    for kind, dirname in (
        ("characters", "characters"),
        ("locations", "locations"),
        ("objects", "objects"),
    ):
        ref_dir = proj_dir / "references" / dirname
        for entity in _entities_for_kind(config, kind):
            png = ref_dir / f"{entity['id']}.png"
            if png.exists() and png.stat().st_size > 0:
                out[kind].append({"id": entity["id"], "name": entity.get("name", entity["id"])})
    return out


def export_references_bundle(
    name: str,
    character_ids: list[str] | None = None,
    location_ids: list[str] | None = None,
    object_ids: list[str] | None = None,
    output_root: Path | None = None,
) -> bytes:
    """Pack the picked entities + their reference PNGs into a .bdrefs zip.

    Each picked id MUST exist in the project's config AND have a non-empty
    reference PNG on disk; otherwise a ``ValueError`` is raised so the caller
    can surface a precise error rather than silently skip. Per-entity photos
    are bundled when present (optional). Returns the zip bytes.
    """
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")
    config = load_config(name, output_root)
    by_kind = _entity_kinds_map(config)
    ids_per_kind = {
        "characters": list(character_ids or []),
        "locations": list(location_ids or []),
        "objects": list(object_ids or []),
    }
    if not any(ids_per_kind.values()):
        raise ValueError("Aucune référence sélectionnée pour l'export.")

    photos_dirname = {
        "characters": CHARACTER_PHOTOS_DIRNAME,
        "locations": LOCATION_PHOTOS_DIRNAME,
        "objects": OBJECT_PHOTOS_DIRNAME,
    }

    manifest: dict = {
        "version": BDREFS_MANIFEST_VERSION,
        "exported_from": name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "characters": [],
        "locations": [],
        "objects": [],
    }
    files: list[tuple[str, Path]] = []

    for kind, ids in ids_per_kind.items():
        for tid in ids:
            entry = by_kind[kind].get(tid)
            if entry is None:
                raise ValueError(f"Identifiant inconnu dans la configuration : {kind}/{tid}")
            png = proj_dir / "references" / kind / f"{tid}.png"
            if not png.exists() or png.stat().st_size == 0:
                raise ValueError(
                    f"Référence absente sur disque : {kind}/{tid}.png. Lancez l'étape Références avant d'exporter."
                )
            manifest[kind].append(entry)
            files.append((f"references/{kind}/{tid}.png", png))
            photo = proj_dir / photos_dirname[kind] / f"{tid}.png"
            if photo.exists() and photo.stat().st_size > 0:
                files.append((f"{photos_dirname[kind]}/{tid}.png", photo))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            BDREFS_MANIFEST_NAME,
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        for arcname, src in files:
            zf.write(src, arcname)
    return buf.getvalue()


def import_references_bundle(
    name: str,
    blob: bytes,
    output_root: Path | None = None,
) -> dict:
    """Merge a .bdrefs bundle into an existing project.

    Each entity is appended to ``bdgen.json`` (so it surfaces in the
    Préparation form and in the next script generation). Id collisions with
    existing entries get a ``_2``, ``_3`` … suffix so nothing is overwritten.
    The reference PNG is dropped under ``references/{kind}/{newId}.png`` so
    the next references run skips it. Per-entity photos are restored when
    present in the bundle.

    Returns a summary: ``{imported: {kind: [...]}, renamed: {old: new}}``.
    """
    from ..models import CharacterInput, LocationInput, ObjectInput
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")
    config = load_config(name, output_root)

    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise ValueError(f"Archive invalide : {e}")

    with zf:
        try:
            manifest = json.loads(zf.read(BDREFS_MANIFEST_NAME).decode("utf-8"))
        except KeyError:
            raise ValueError(f"Bundle invalide : {BDREFS_MANIFEST_NAME} introuvable.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Manifest illisible : {e}")
        if manifest.get("version") != BDREFS_MANIFEST_VERSION:
            raise ValueError(f"Version de bundle non supportée : {manifest.get('version')}.")

        photos_dirname = {
            "characters": CHARACTER_PHOTOS_DIRNAME,
            "locations": LOCATION_PHOTOS_DIRNAME,
            "objects": OBJECT_PHOTOS_DIRNAME,
        }

        constructors = {
            "characters": CharacterInput,
            "locations": LocationInput,
            "objects": ObjectInput,
        }
        used_ids = {
            "characters": {c.id for c in config.characters},
            "locations": {l.id for l in config.locations},
            "objects": {o.id for o in config.objects},
        }

        imported: dict[str, list[str]] = {"characters": [], "locations": [], "objects": []}
        renamed: dict[str, str] = {}

        for kind in ("characters", "locations", "objects"):
            for entry in manifest.get(kind, []):
                old_id = entry.get("id")
                if not old_id:
                    continue
                new_id = old_id
                if new_id in used_ids[kind]:
                    i = 2
                    while f"{old_id}_{i}" in used_ids[kind]:
                        i += 1
                    new_id = f"{old_id}_{i}"
                    renamed[f"{kind}/{old_id}"] = new_id
                used_ids[kind].add(new_id)

                entry_renamed = {**entry, "id": new_id}
                try:
                    model = constructors[kind].model_validate(entry_renamed)
                except Exception as e:
                    raise ValueError(f"Entrée invalide dans le bundle ({kind}/{old_id}) : {e}")
                getattr(config, kind).append(model)

                ref_arc = f"references/{kind}/{old_id}.png"
                try:
                    ref_bytes = zf.read(ref_arc)
                except KeyError:
                    raise ValueError(f"PNG manquant dans le bundle : {ref_arc}")
                ref_dst = proj_dir / "references" / kind / f"{new_id}.png"
                ref_dst.parent.mkdir(parents=True, exist_ok=True)
                ref_dst.write_bytes(ref_bytes)

                photo_arc = f"{photos_dirname[kind]}/{old_id}.png"
                if photo_arc in zf.namelist():
                    photo_dst = proj_dir / photos_dirname[kind] / f"{new_id}.png"
                    photo_dst.parent.mkdir(parents=True, exist_ok=True)
                    photo_dst.write_bytes(zf.read(photo_arc))

                imported[kind].append(new_id)

    save_config(config, output_root)
    return {"imported": imported, "renamed": renamed}
