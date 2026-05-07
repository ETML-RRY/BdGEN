"""Project discovery and lifecycle: list, create, delete, duplicate, restyle."""

from __future__ import annotations

import re
import shutil
import time
import unicodedata
from pathlib import Path

from ..models import BdGenScript, Style
from . import ProjectSummary
from .config import _force_writable_and_retry, load_config, save_config
from .constants import (
    CHARACTER_PHOTOS_DIRNAME,
    LOCATION_PHOTOS_DIRNAME,
    OBJECT_PHOTOS_DIRNAME,
    PROJECT_CONFIG_NAME,
    QUALITY_INDEX_NAME,
    STALE_INDEX_NAME,
    STYLE_REF_NAME,
)


def projects_root(output_root: Path | None = None) -> Path:
    return (output_root or Path("./output")).resolve()


def get_project_dir(name: str, output_root: Path | None = None) -> Path:
    root = projects_root(output_root)
    return root / name


def project_exists(name: str, output_root: Path | None = None) -> bool:
    return get_project_dir(name, output_root).is_dir()


def list_projects(output_root: Path | None = None) -> list[ProjectSummary]:
    """Scan the output root for project directories and return summaries."""
    from .state import _summary

    root = projects_root(output_root)
    if not root.exists():
        return []
    out: list[ProjectSummary] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if not (entry / PROJECT_CONFIG_NAME).exists():
            # Tolerate legacy projects with only a script: still surface them.
            if not (entry / "bdgen-script.json").exists():
                continue
        try:
            out.append(_summary(entry))
        except Exception:
            continue
    return out


def delete_project(name: str, output_root: Path | None = None) -> None:
    d = get_project_dir(name, output_root)
    if not d.exists():
        return
    # OneDrive / antivirus / file explorer can briefly hold handles on freshly
    # closed files on Windows, making rmtree fail with WinError 5. Retry a few
    # times with a small backoff before giving up.
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            shutil.rmtree(d, onerror=_force_writable_and_retry)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _slugify(text: str) -> str:
    norm = unicodedata.normalize("NFD", text)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return norm[:60]


def _next_available_name(base: str, root: Path) -> str:
    """Pick a project slug not already present under ``root``."""
    candidate = base
    if not (root / candidate).exists():
        return candidate
    i = 2
    while (root / f"{base}_{i}").exists():
        i += 1
    return f"{base}_{i}"


def duplicate_project(
    source_name: str,
    new_project_id: str | None = None,
    output_root: Path | None = None,
    include_references: bool = False,
    include_photos: bool = True,
    include_style_reference: bool = True,
) -> str:
    """Clone the source project's configuration into a fresh project.

    Copies ``bdgen.json`` (story, style, characters, locations, structure,
    generation_options). Does NOT copy the script, composed pages, PDF, or
    feedback — the duplicate starts at the Préparation step.

    Optional carry-overs (default behavior preserves the previous defaults):
      - ``include_style_reference`` (default True): copy the style reference
        image when present.
      - ``include_photos`` (default True): copy the per-entity reference
        photos (characters, objects, locations) — the user's likeness anchors.
      - ``include_references`` (default False): copy the AI-generated
        reference PNGs and the quality index. The duplicate then behaves like
        a Tome 2 starting point: when the user runs script → references, the
        references step skips every entity whose PNG is already on disk.

    Returns the slug of the freshly created project.
    """
    root = projects_root(output_root)
    src_cfg = load_config(source_name, output_root)

    base = _slugify(new_project_id or f"{source_name}_copie") or "projet_copie"
    new_id = _next_available_name(base, root)

    new_cfg = src_cfg.model_copy(deep=True)
    new_cfg.project = new_id
    if not (new_project_id and new_project_id.strip()):
        # User didn't pass an explicit name → tag the display name (or fall
        # back to the title) so the duplicate is easy to spot in listings
        # until the user renames it. The BD title itself is preserved when a
        # display name exists so the generated content stays unaffected.
        base_label = new_cfg.display_name or new_cfg.metadata.title
        if base_label:
            new_cfg.display_name = f"{base_label} (copie)"

    save_config(new_cfg, output_root)

    src_dir = get_project_dir(source_name, output_root)
    dst_dir = get_project_dir(new_id, output_root)

    if include_style_reference:
        style_ref = src_dir / STYLE_REF_NAME
        if style_ref.exists() and style_ref.stat().st_size > 0:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(style_ref, dst_dir / STYLE_REF_NAME)

    if include_photos:
        for photos_dirname in (
            CHARACTER_PHOTOS_DIRNAME,
            OBJECT_PHOTOS_DIRNAME,
            LOCATION_PHOTOS_DIRNAME,
        ):
            src_photos = src_dir / photos_dirname
            if src_photos.is_dir():
                dst_photos = dst_dir / photos_dirname
                dst_photos.mkdir(parents=True, exist_ok=True)
                for p in src_photos.iterdir():
                    if p.is_file():
                        shutil.copy2(p, dst_photos / p.name)

    if include_references:
        src_refs = src_dir / "references"
        if src_refs.is_dir():
            dst_refs = dst_dir / "references"
            shutil.copytree(src_refs, dst_refs, dirs_exist_ok=True)
        src_qidx = src_dir / QUALITY_INDEX_NAME
        if src_qidx.exists():
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_qidx, dst_dir / QUALITY_INDEX_NAME)

    return new_id


def restyle_project(
    name: str,
    new_style: dict,
    output_root: Path | None = None,
) -> dict:
    """Apply a new visual style without rewriting the script.

    Updates ``style`` on both ``bdgen.json`` and ``bdgen-script.json``, then
    wipes the downstream image artefacts (references, composed pages, PDF,
    quality index) so the user can rerun those steps under the new style.
    Script text, characters, locations, panels and dialogs are preserved
    verbatim.

    Returns a summary describing what was deleted.
    """
    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")

    config = load_config(name, output_root)
    # Re-validate the incoming style by routing it through the Pydantic model.
    merged = config.style.model_dump()
    merged.update({k: v for k, v in new_style.items() if v is not None})
    config.style = Style.model_validate(merged)
    save_config(config, output_root)

    deleted: dict[str, int | bool] = {
        "references": 0,
        "pages": 0,
        "pdf": False,
        "quality_index": False,
    }

    script_path = proj_dir / "bdgen-script.json"
    if script_path.exists():
        bd_script = BdGenScript.load(script_path)
        bd_script.style = config.style
        for c in bd_script.characters:
            c.reference_image = None
        for l in bd_script.locations:
            l.reference_image = None
        for o in bd_script.objects:
            o.reference_image = None
        bd_script.save(script_path)

    for sub in ("references", "pages"):
        d = proj_dir / sub
        if d.is_dir():
            count = sum(1 for p in d.rglob("*.png") if p.is_file())
            shutil.rmtree(d, onerror=_force_writable_and_retry)
            deleted[sub] = count

    pdf = proj_dir / f"{name}.pdf"
    if pdf.exists():
        pdf.unlink()
        deleted["pdf"] = True

    qidx = proj_dir / QUALITY_INDEX_NAME
    if qidx.exists():
        qidx.unlink()
        deleted["quality_index"] = True

    sidx = proj_dir / STALE_INDEX_NAME
    if sidx.exists():
        sidx.unlink()

    return deleted
