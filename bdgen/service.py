"""High-level project-oriented API used by the web server (and any other UI).

This module is the boundary between the generation engine (script.py,
references.py, compose.py) and any user interface. The engine modules know
nothing about projects-on-disk, zip files, or HTTP; the service module handles
all of that and dispatches to the engine with the right
reporter/interrupt/feedback wiring.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from . import compose as compose_module
from . import references as references_module
from . import script as script_module
from .feedback import FeedbackStore, feedback_path_for
from .models import BdGenInput, BdGenScript, Style
from .progress import InterruptFlag, ProgressReporter

Step = Literal["preparation", "script", "references", "compose", "done"]
Quality = Literal["low", "medium", "high"]
PROJECT_CONFIG_NAME = "bdgen.json"
QUALITY_INDEX_NAME = "bdgen-quality.json"
STALE_INDEX_NAME = "bdgen-stale.json"
STYLE_REF_NAME = "bdgen-style-ref.png"
CHARACTER_PHOTOS_DIRNAME = "character_photos"
LOCATION_PHOTOS_DIRNAME = "location_photos"
OBJECT_PHOTOS_DIRNAME = "object_photos"
CHARACTER_PHOTO_MAX_SIDE = 1024
LOCATION_PHOTO_MAX_SIDE = 1024
OBJECT_PHOTO_MAX_SIDE = 1024
STALE_STEPS = ("references", "compose")


@dataclass
class ProjectSummary:
    """Light-weight project description for listings."""
    name: str
    display_name: str | None
    title: str | None
    author: str | None
    state: Step
    page_count: int | None
    pages_written: int
    references_ready: int
    references_total: int
    pages_composed: int
    pdf_ready: bool
    updated_at: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


# --- Project discovery / lifecycle ---

def projects_root(output_root: Path | None = None) -> Path:
    return (output_root or Path("./output")).resolve()


def list_projects(output_root: Path | None = None) -> list[ProjectSummary]:
    """Scan the output root for project directories and return summaries."""
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


def get_project_dir(name: str, output_root: Path | None = None) -> Path:
    root = projects_root(output_root)
    return root / name


def project_exists(name: str, output_root: Path | None = None) -> bool:
    return get_project_dir(name, output_root).is_dir()


def load_config(name: str, output_root: Path | None = None) -> BdGenInput:
    """Load the bdgen.json for a project (raises if missing)."""
    p = get_project_dir(name, output_root) / PROJECT_CONFIG_NAME
    if not p.exists():
        raise FileNotFoundError(f"bdgen.json absent pour le projet « {name} »")
    return BdGenInput.load(p)


def save_config(config: BdGenInput, output_root: Path | None = None) -> Path:
    """Write bdgen.json into the project directory and ensure the dir exists.

    The project name comes from ``config.project``; ``output_root`` defaults to
    ``config.output_root`` then the global default.
    """
    if not config.project:
        raise ValueError("config.project doit être défini.")
    config.output_root = (output_root or config.output_root or Path("./output"))
    proj_dir = config.output_root / config.project
    proj_dir.mkdir(parents=True, exist_ok=True)
    config_path = proj_dir / PROJECT_CONFIG_NAME
    payload = config.model_dump(mode="json", exclude_none=False)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return config_path


def load_script_if_present(name: str, output_root: Path | None = None) -> BdGenScript | None:
    p = get_project_dir(name, output_root) / "bdgen-script.json"
    if not p.exists():
        return None
    try:
        return BdGenScript.load(p)
    except Exception:
        return None


def delete_project(name: str, output_root: Path | None = None) -> None:
    d = get_project_dir(name, output_root)
    if d.exists():
        shutil.rmtree(d)


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
) -> str:
    """Clone the source project's configuration into a fresh project.

    Copies ``bdgen.json`` (story, style, characters, locations, structure,
    generation_options) and the optional style-reference image. Does NOT copy
    the script, composed pages, PDF, or feedback — the duplicate starts at the
    Préparation step. Per-entity reference photos are always copied so the
    user keeps the same likeness anchors.

    When ``include_references`` is True, the cast's reference PNGs and the
    quality index are also copied. The duplicate then behaves like a Tome 2
    starting point: when the user runs script → references on the new project,
    the references step skips every entity whose PNG is already on disk.

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
    style_ref = src_dir / STYLE_REF_NAME
    dst_dir = get_project_dir(new_id, output_root)
    if style_ref.exists() and style_ref.stat().st_size > 0:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(style_ref, dst_dir / STYLE_REF_NAME)

    src_photos = src_dir / CHARACTER_PHOTOS_DIRNAME
    if src_photos.is_dir():
        dst_photos = dst_dir / CHARACTER_PHOTOS_DIRNAME
        dst_photos.mkdir(parents=True, exist_ok=True)
        for p in src_photos.iterdir():
            if p.is_file():
                shutil.copy2(p, dst_photos / p.name)

    src_obj_photos = src_dir / OBJECT_PHOTOS_DIRNAME
    if src_obj_photos.is_dir():
        dst_obj_photos = dst_dir / OBJECT_PHOTOS_DIRNAME
        dst_obj_photos.mkdir(parents=True, exist_ok=True)
        for p in src_obj_photos.iterdir():
            if p.is_file():
                shutil.copy2(p, dst_obj_photos / p.name)

    src_loc_photos = src_dir / LOCATION_PHOTOS_DIRNAME
    if src_loc_photos.is_dir():
        dst_loc_photos = dst_dir / LOCATION_PHOTOS_DIRNAME
        dst_loc_photos.mkdir(parents=True, exist_ok=True)
        for p in src_loc_photos.iterdir():
            if p.is_file():
                shutil.copy2(p, dst_loc_photos / p.name)

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
            shutil.rmtree(d)
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


# --- State derivation ---

def derive_state(proj_dir: Path) -> Step:
    """Best-effort guess of what step the user should land on.

    The UI may override this (e.g. user clicks a step explicitly), but when
    reopening a project this drives the default landing step.
    """
    config_path = proj_dir / PROJECT_CONFIG_NAME
    script_path = proj_dir / "bdgen-script.json"
    if not config_path.exists() and not script_path.exists():
        return "preparation"
    bd_script = None
    if script_path.exists():
        try:
            bd_script = BdGenScript.load(script_path)
        except Exception:
            bd_script = None
    if bd_script is None or not bd_script.pages:
        return "script"
    config = BdGenInput.load(config_path) if config_path.exists() else None
    target_pages = config.structure.page_count if config else len(bd_script.pages)
    if len(bd_script.pages) < target_pages:
        return "script"
    refs_total, refs_ready = _references_progress(proj_dir, bd_script)
    if refs_ready < refs_total:
        return "references"
    pages_total, pages_ready = _composed_progress(proj_dir, bd_script)
    if pages_ready < pages_total:
        return "compose"
    pdf = proj_dir / f"{proj_dir.name}.pdf"
    if pdf.exists():
        return "done"
    return "compose"


def _references_progress(proj_dir: Path, bd_script: BdGenScript) -> tuple[int, int]:
    refs_dir = proj_dir / "references"
    total = (
        len(bd_script.characters)
        + len(bd_script.locations)
        + len(bd_script.objects)
    )
    ready = 0
    for c in bd_script.characters:
        if (refs_dir / "characters" / f"{c.id}.png").exists():
            ready += 1
    for l in bd_script.locations:
        if (refs_dir / "locations" / f"{l.id}.png").exists():
            ready += 1
    for o in bd_script.objects:
        if (refs_dir / "objects" / f"{o.id}.png").exists():
            ready += 1
    return total, ready


def _composed_progress(proj_dir: Path, bd_script: BdGenScript) -> tuple[int, int]:
    pages_dir = proj_dir / "pages"
    targets = []
    if bd_script.cover is not None:
        targets.append(pages_dir / "cover.png")
    for p in bd_script.pages:
        targets.append(pages_dir / f"page_{p.page_number:02d}.png")
    if bd_script.back_cover is not None:
        targets.append(pages_dir / "back.png")
    return len(targets), sum(1 for t in targets if t.exists())


def _summary(proj_dir: Path) -> ProjectSummary:
    config_path = proj_dir / PROJECT_CONFIG_NAME
    script_path = proj_dir / "bdgen-script.json"
    display_name: str | None = None
    title: str | None = None
    author: str | None = None
    target_pages: int | None = None
    if config_path.exists():
        try:
            cfg = BdGenInput.load(config_path)
            display_name = cfg.display_name
            title = cfg.metadata.title
            author = cfg.metadata.author
            target_pages = cfg.structure.page_count
        except Exception:
            pass
    bd_script: BdGenScript | None = None
    if script_path.exists():
        try:
            bd_script = BdGenScript.load(script_path)
            if display_name is None:
                display_name = bd_script.display_name
            if title is None:
                title = bd_script.metadata.title
            if author is None:
                author = bd_script.metadata.author
        except Exception:
            pass
    pages_written = len(bd_script.pages) if bd_script else 0
    refs_total = refs_ready = pages_composed = 0
    if bd_script is not None:
        refs_total, refs_ready = _references_progress(proj_dir, bd_script)
        _, pages_composed = _composed_progress(proj_dir, bd_script)
    pdf = proj_dir / f"{proj_dir.name}.pdf"
    state = derive_state(proj_dir)
    updated = max(
        (p.stat().st_mtime for p in proj_dir.iterdir()),
        default=proj_dir.stat().st_mtime,
    )
    return ProjectSummary(
        name=proj_dir.name,
        display_name=display_name,
        title=title,
        author=author,
        state=state,
        page_count=target_pages,
        pages_written=pages_written,
        references_ready=refs_ready,
        references_total=refs_total,
        pages_composed=pages_composed,
        pdf_ready=pdf.exists(),
        updated_at=datetime.fromtimestamp(updated, tz=timezone.utc).isoformat(),
    )


# --- Style reference image ---

def get_style_reference_path(proj_dir: Path) -> Path | None:
    """Return the style-reference PNG if it exists, else None."""
    p = proj_dir / STYLE_REF_NAME
    return p if p.exists() and p.stat().st_size > 0 else None


def save_style_reference(name: str, image_bytes: bytes, output_root: Path | None = None) -> Path:
    """Save image_bytes as the project's style reference."""
    proj_dir = get_project_dir(name, output_root)
    proj_dir.mkdir(parents=True, exist_ok=True)
    p = proj_dir / STYLE_REF_NAME
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(image_bytes)
    tmp.replace(p)
    return p


# --- Per-character reference photos ---

def character_photo_path(proj_dir: Path, character_id: str) -> Path:
    """Return the canonical PNG path for a character photo (file may not exist)."""
    return proj_dir / CHARACTER_PHOTOS_DIRNAME / f"{character_id}.png"


def get_character_photo_path(proj_dir: Path, character_id: str) -> Path | None:
    p = character_photo_path(proj_dir, character_id)
    return p if p.exists() and p.stat().st_size > 0 else None


def list_character_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{character_id: path}`` for every existing character photo."""
    d = proj_dir / CHARACTER_PHOTOS_DIRNAME
    if not d.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
            out[p.stem] = p
    return out


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
    if not character_id or "/" in character_id or "\\" in character_id:
        raise ValueError("character_id invalide.")
    if not image_bytes:
        raise ValueError("Image vide.")

    from io import BytesIO
    from PIL import Image

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Image illisible : {e}")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        img = img.convert("RGB")

    longest = max(img.size)
    if longest > CHARACTER_PHOTO_MAX_SIDE:
        scale = CHARACTER_PHOTO_MAX_SIDE / longest
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    proj_dir = get_project_dir(name, output_root)
    photos_dir = proj_dir / CHARACTER_PHOTOS_DIRNAME
    photos_dir.mkdir(parents=True, exist_ok=True)
    p = photos_dir / f"{character_id}.png"
    tmp = p.with_suffix(p.suffix + ".tmp")
    img.save(tmp, format="PNG", optimize=True)
    tmp.replace(p)

    # The on-disk reference PNG (if any) was generated without this photo and
    # no longer reflects the new constraint; flag it so the UI can offer a
    # one-click regeneration.
    ref_png = proj_dir / "references" / "characters" / f"{character_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", character_id)
    return p


def delete_character_photo(
    name: str, character_id: str, output_root: Path | None = None
) -> bool:
    proj_dir = get_project_dir(name, output_root)
    p = character_photo_path(proj_dir, character_id)
    if p.exists():
        p.unlink()
        ref_png = proj_dir / "references" / "characters" / f"{character_id}.png"
        if ref_png.exists():
            mark_stale(proj_dir, "references", character_id)
        return True
    return False


# --- Per-location reference photos ---

def location_photo_path(proj_dir: Path, location_id: str) -> Path:
    """Return the canonical PNG path for a location photo (file may not exist)."""
    return proj_dir / LOCATION_PHOTOS_DIRNAME / f"{location_id}.png"


def get_location_photo_path(proj_dir: Path, location_id: str) -> Path | None:
    p = location_photo_path(proj_dir, location_id)
    return p if p.exists() and p.stat().st_size > 0 else None


def list_location_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{location_id: path}`` for every existing location photo."""
    d = proj_dir / LOCATION_PHOTOS_DIRNAME
    if not d.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
            out[p.stem] = p
    return out


def save_location_photo(
    name: str,
    location_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Save a per-location reference photo, normalized to PNG."""
    if not location_id or "/" in location_id or "\\" in location_id:
        raise ValueError("location_id invalide.")
    if not image_bytes:
        raise ValueError("Image vide.")

    from io import BytesIO
    from PIL import Image

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Image illisible : {e}")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        img = img.convert("RGB")

    longest = max(img.size)
    if longest > LOCATION_PHOTO_MAX_SIDE:
        scale = LOCATION_PHOTO_MAX_SIDE / longest
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    proj_dir = get_project_dir(name, output_root)
    photos_dir = proj_dir / LOCATION_PHOTOS_DIRNAME
    photos_dir.mkdir(parents=True, exist_ok=True)
    p = photos_dir / f"{location_id}.png"
    tmp = p.with_suffix(p.suffix + ".tmp")
    img.save(tmp, format="PNG", optimize=True)
    tmp.replace(p)

    ref_png = proj_dir / "references" / "locations" / f"{location_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", location_id)
    return p


def delete_location_photo(
    name: str, location_id: str, output_root: Path | None = None
) -> bool:
    proj_dir = get_project_dir(name, output_root)
    p = location_photo_path(proj_dir, location_id)
    if p.exists():
        p.unlink()
        ref_png = proj_dir / "references" / "locations" / f"{location_id}.png"
        if ref_png.exists():
            mark_stale(proj_dir, "references", location_id)
        return True
    return False


# --- Per-object reference photos ---

def object_photo_path(proj_dir: Path, object_id: str) -> Path:
    """Return the canonical PNG path for an object photo (file may not exist)."""
    return proj_dir / OBJECT_PHOTOS_DIRNAME / f"{object_id}.png"


def get_object_photo_path(proj_dir: Path, object_id: str) -> Path | None:
    p = object_photo_path(proj_dir, object_id)
    return p if p.exists() and p.stat().st_size > 0 else None


def list_object_photos(proj_dir: Path) -> dict[str, Path]:
    """Return ``{object_id: path}`` for every existing object photo."""
    d = proj_dir / OBJECT_PHOTOS_DIRNAME
    if not d.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
            out[p.stem] = p
    return out


def save_object_photo(
    name: str,
    object_id: str,
    image_bytes: bytes,
    output_root: Path | None = None,
) -> Path:
    """Save a per-object reference photo, normalized to PNG."""
    if not object_id or "/" in object_id or "\\" in object_id:
        raise ValueError("object_id invalide.")
    if not image_bytes:
        raise ValueError("Image vide.")

    from io import BytesIO
    from PIL import Image

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as e:
        raise ValueError(f"Image illisible : {e}")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        img = img.convert("RGB")

    longest = max(img.size)
    if longest > OBJECT_PHOTO_MAX_SIDE:
        scale = OBJECT_PHOTO_MAX_SIDE / longest
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    proj_dir = get_project_dir(name, output_root)
    photos_dir = proj_dir / OBJECT_PHOTOS_DIRNAME
    photos_dir.mkdir(parents=True, exist_ok=True)
    p = photos_dir / f"{object_id}.png"
    tmp = p.with_suffix(p.suffix + ".tmp")
    img.save(tmp, format="PNG", optimize=True)
    tmp.replace(p)

    ref_png = proj_dir / "references" / "objects" / f"{object_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", object_id)
    return p


def delete_object_photo(
    name: str, object_id: str, output_root: Path | None = None
) -> bool:
    proj_dir = get_project_dir(name, output_root)
    p = object_photo_path(proj_dir, object_id)
    if p.exists():
        p.unlink()
        ref_png = proj_dir / "references" / "objects" / f"{object_id}.png"
        if ref_png.exists():
            mark_stale(proj_dir, "references", object_id)
        return True
    return False


# --- Per-target quality index ---

def _quality_index_path(proj_dir: Path) -> Path:
    return proj_dir / QUALITY_INDEX_NAME


def read_quality_index(proj_dir: Path) -> dict[str, dict[str, str]]:
    """Return {step: {target_id: quality}} for references and compose.

    A missing entry means the target was never explicitly recorded (typically
    because it was generated before this index existed). The caller treats
    missing entries as the project's configured default quality.
    """
    p = _quality_index_path(proj_dir)
    base = {"references": {}, "compose": {}}
    if not p.exists():
        return base
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return base
        for k in ("references", "compose"):
            if isinstance(data.get(k), dict):
                base[k] = {
                    str(tid): str(q)
                    for tid, q in data[k].items()
                    if isinstance(q, str)
                }
        return base
    except Exception:
        return base


def write_quality_index(proj_dir: Path, idx: dict[str, dict[str, str]]) -> None:
    p = _quality_index_path(proj_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Staleness index (per-target "text modified after image was generated") ---

def _stale_index_path(proj_dir: Path) -> Path:
    return proj_dir / STALE_INDEX_NAME


def read_stale_index(proj_dir: Path) -> dict[str, list[str]]:
    """Return {step: [target_id, ...]} for references / compose.

    A target appears here when its underlying script text was rewritten after
    the image was generated, so the on-disk PNG no longer matches.
    """
    p = _stale_index_path(proj_dir)
    base: dict[str, list[str]] = {s: [] for s in STALE_STEPS}
    if not p.exists():
        return base
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return base
        for s in STALE_STEPS:
            v = data.get(s)
            if isinstance(v, list):
                # de-dup, preserve order
                seen: set[str] = set()
                out: list[str] = []
                for tid in v:
                    if isinstance(tid, str) and tid not in seen:
                        seen.add(tid)
                        out.append(tid)
                base[s] = out
        return base
    except Exception:
        return base


def write_stale_index(proj_dir: Path, idx: dict[str, list[str]]) -> None:
    p = _stale_index_path(proj_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Drop empty buckets to keep the file tidy.
    cleaned = {k: v for k, v in idx.items() if v}
    if not cleaned:
        if p.exists():
            p.unlink()
        return
    p.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def mark_stale(proj_dir: Path, step: str, target_ids: str | list[str]) -> None:
    """Flag one or more targets as obsolete for a given image step."""
    if step not in STALE_STEPS:
        return
    ids = [target_ids] if isinstance(target_ids, str) else list(target_ids)
    if not ids:
        return
    idx = read_stale_index(proj_dir)
    bucket = idx.setdefault(step, [])
    seen = set(bucket)
    for tid in ids:
        if tid and tid not in seen:
            bucket.append(tid)
            seen.add(tid)
    write_stale_index(proj_dir, idx)


def clear_stale(proj_dir: Path, step: str, target_ids: str | list[str]) -> None:
    if step not in STALE_STEPS:
        return
    ids = {target_ids} if isinstance(target_ids, str) else set(target_ids)
    if not ids:
        return
    idx = read_stale_index(proj_dir)
    bucket = idx.get(step, [])
    new_bucket = [tid for tid in bucket if tid not in ids]
    if len(new_bucket) != len(bucket):
        idx[step] = new_bucket
        write_stale_index(proj_dir, idx)


def _record_qualities(
    proj_dir: Path,
    step: str,
    target_to_path: dict[str, Path],
    pre_existing: set[str],
    quality: str,
) -> None:
    """Update the quality index for targets that were just (re)generated.

    A target is considered "newly generated" if its file exists now AND it
    wasn't in ``pre_existing`` (the snapshot taken before the engine ran).
    """
    idx = read_quality_index(proj_dir)
    bucket = idx.setdefault(step, {})
    changed = False
    for tid, p in target_to_path.items():
        if not p.exists():
            continue
        if tid in pre_existing:
            continue
        if bucket.get(tid) != quality:
            bucket[tid] = quality
            changed = True
    if changed:
        write_quality_index(proj_dir, idx)


def _clear_stale_for_regenerated(
    proj_dir: Path,
    step: str,
    target_to_path: dict[str, Path],
    pre_existing: set[str],
    force_ids: list[str] | None,
) -> None:
    """Drop the staleness flag for any target that was just regenerated.

    A target counts as freshly produced if it was force-regenerated and its
    file exists at the end of the run, or if it was newly created (didn't
    exist before, exists now). Untouched/skipped targets keep their flag.
    """
    forced = set(force_ids or [])
    cleared: list[str] = []
    for tid, p in target_to_path.items():
        if not p.exists():
            continue
        if tid in forced or tid not in pre_existing:
            cleared.append(tid)
    if cleared:
        clear_stale(proj_dir, step, cleared)


# --- Step runners (called from the JobManager in a worker thread) ---

def run_step_script(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    preview_pages: int | None = None,
) -> BdGenScript:
    config = load_config(name, output_root)
    feedback_store = FeedbackStore.load_or_empty(
        feedback_path_for(config.generation_options.script_path)
    )
    feedback = feedback_store.get_for("script")
    bd_script = script_module.generate_script(
        config,
        input_path=get_project_dir(name, output_root) / PROJECT_CONFIG_NAME,
        feedback=feedback,
        preview_pages=preview_pages,
        script_path=config.generation_options.script_path,
        reporter=reporter,
        interrupt=interrupt,
    )
    bd_script.save(config.generation_options.script_path)
    return bd_script


def run_step_references(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    force_ids: list[str] | None = None,
    quality_override: str | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    opts = _resolve_options(bd_script, name, output_root)
    if force_ids:
        for fid in force_ids:
            for kind in ("characters", "locations", "objects"):
                p = opts.references.output_dir / kind / f"{fid}.png"
                if p.exists():
                    p.unlink()
    if quality_override:
        opts.image_model.quality = quality_override
    quality_used = opts.image_model.quality

    target_paths: dict[str, Path] = {}
    for c in bd_script.characters:
        target_paths[c.id] = opts.references.output_dir / "characters" / f"{c.id}.png"
    for l in bd_script.locations:
        target_paths[l.id] = opts.references.output_dir / "locations" / f"{l.id}.png"
    for o in bd_script.objects:
        target_paths[o.id] = opts.references.output_dir / "objects" / f"{o.id}.png"
    pre_existing = {tid for tid, p in target_paths.items() if p.exists()}

    style_ref = get_style_reference_path(proj_dir)
    character_photos = list_character_photos(proj_dir)
    location_photos = list_location_photos(proj_dir)
    object_photos = list_object_photos(proj_dir)
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(script_path))
    try:
        references_module.generate_references(
            bd_script, opts.references, opts.image_model,
            script_path=script_path, feedback_store=feedback_store,
            reporter=reporter, interrupt=interrupt,
            style_ref=style_ref,
            character_photos=character_photos,
            location_photos=location_photos,
            object_photos=object_photos,
        )
    finally:
        # Even on partial completion (interruption), record what landed.
        _record_qualities(proj_dir, "references", target_paths, pre_existing, quality_used)
        _clear_stale_for_regenerated(
            proj_dir, "references", target_paths, pre_existing, force_ids
        )
    bd_script.save(script_path)
    return bd_script


def run_step_compose(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    force_ids: list[str] | None = None,
    quality_override: str | None = None,
) -> Path:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    opts = _resolve_options(bd_script, name, output_root)
    pages_dir = proj_dir / "pages"
    if force_ids:
        for fid in force_ids:
            p = _composed_path(pages_dir, fid)
            if p and p.exists():
                p.unlink()
    if quality_override:
        opts.image_model.quality = quality_override
    quality_used = opts.image_model.quality

    target_paths: dict[str, Path] = {}
    if bd_script.cover is not None:
        target_paths["cover"] = pages_dir / "cover.png"
    for p in bd_script.pages:
        target_paths[f"page_{p.page_number}"] = pages_dir / f"page_{p.page_number:02d}.png"
    if bd_script.back_cover is not None:
        target_paths["back"] = pages_dir / "back.png"
    pre_existing = {tid for tid, pp in target_paths.items() if pp.exists()}

    style_ref = get_style_reference_path(proj_dir)
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(script_path))
    try:
        out = compose_module.compose_output(
            bd_script, opts, pages_dir,
            feedback_store=feedback_store,
            reporter=reporter, interrupt=interrupt,
            style_ref=style_ref,
        )
    finally:
        _record_qualities(proj_dir, "compose", target_paths, pre_existing, quality_used)
        _clear_stale_for_regenerated(
            proj_dir, "compose", target_paths, pre_existing, force_ids
        )
    return out


# --- Targeted refinement (synchronous; called outside the JobManager) ---

def add_feedback_and_regenerate_character(
    name: str, character_id: str, feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", character_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_character(bd_script, character_id, feedback_text, reporter)
    bd_script.save(script_path)
    # The on-disk reference PNG (if any) was generated against the previous
    # text and no longer matches; flag it so the UI can offer a one-click
    # regeneration without asking the user to re-state the change.
    ref_png = proj_dir / "references" / "characters" / f"{character_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", character_id)
    return bd_script


def add_feedback_and_regenerate_location(
    name: str, location_id: str, feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", location_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_location(bd_script, location_id, feedback_text, reporter)
    bd_script.save(script_path)
    ref_png = proj_dir / "references" / "locations" / f"{location_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", location_id)
    return bd_script


def add_feedback_and_regenerate_object(
    name: str, object_id: str, feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", object_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_object(bd_script, object_id, feedback_text, reporter)
    bd_script.save(script_path)
    ref_png = proj_dir / "references" / "objects" / f"{object_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", object_id)
    return bd_script


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


def delete_character_and_cascade(
    name: str, character_id: str, output_root: Path | None = None
) -> dict:
    """Remove a character from the script and drop all pages from the
    earliest one that referenced them. Pages 1..(earliest-1) stay intact.

    The caller is expected to relaunch ``run_step_script`` afterwards so the
    pipeline regenerates the dropped pages without that character.

    Returns ``{deleted, character_id, earliest_affected, pages_dropped}``.
    The reference-sheet PNG (if any) is also removed so a future references
    run won't surface a stale image.
    """
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


def delete_location_and_cascade(
    name: str, location_id: str, output_root: Path | None = None
) -> dict:
    """Symmetric of ``delete_character_and_cascade`` for locations."""
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


def delete_object_and_cascade(
    name: str, object_id: str, output_root: Path | None = None
) -> dict:
    """Symmetric of ``delete_character_and_cascade`` for objects."""
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


def preview_delete_character(
    name: str, character_id: str, output_root: Path | None = None
) -> dict:
    """Return what would happen on delete, without performing it."""
    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.character_by_id(character_id) is None:
        raise ValueError(f"Personnage inconnu : {character_id}")
    earliest = _earliest_page_using_character(bd_script, character_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}


def preview_delete_location(
    name: str, location_id: str, output_root: Path | None = None
) -> dict:
    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.location_by_id(location_id) is None:
        raise ValueError(f"Décor inconnu : {location_id}")
    earliest = _earliest_page_using_location(bd_script, location_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}


def preview_delete_object(
    name: str, object_id: str, output_root: Path | None = None
) -> dict:
    proj_dir = get_project_dir(name, output_root)
    bd_script = BdGenScript.load(proj_dir / "bdgen-script.json")
    if bd_script.object_by_id(object_id) is None:
        raise ValueError(f"Objet inconnu : {object_id}")
    earliest = _earliest_page_using_object(bd_script, object_id)
    total = len(bd_script.pages)
    dropped = 0 if earliest is None else max(0, total - (earliest - 1))
    return {"earliest_affected": earliest, "pages_dropped": dropped}


def add_feedback_and_regenerate_cover(
    name: str, feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", "cover", feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_cover(bd_script, feedback_text, reporter)
    bd_script.save(script_path)
    if (proj_dir / "pages" / "cover.png").exists():
        mark_stale(proj_dir, "compose", "cover")
    return bd_script


def add_feedback_and_regenerate_back_cover(
    name: str, feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", "back", feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_back_cover(bd_script, feedback_text, reporter)
    bd_script.save(script_path)
    if (proj_dir / "pages" / "back.png").exists():
        mark_stale(proj_dir, "compose", "back")
    return bd_script


def add_feedback_and_regenerate_page(
    name: str, page_number: int, feedback_text: str,
    cascade: bool = False,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    """Rewrite one page. If ``cascade`` is True, drop all subsequent pages so
    the next ``run_step_script`` call regenerates them with the new context.
    """
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    target = f"page_{page_number}"
    fb_store.add("script", target, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_page(bd_script, page_number, feedback_text, reporter)
    if cascade:
        script_module.truncate_pages_from(bd_script, page_number + 1)
    bd_script.save(script_path)
    cm = proj_dir / "pages" / f"page_{page_number:02d}.png"
    if cm.exists():
        mark_stale(proj_dir, "compose", target)
    return bd_script


def record_image_feedback(
    name: str,
    step: Literal["references", "compose"],
    target: str,
    feedback_text: str,
    output_root: Path | None = None,
) -> None:
    """Append a feedback line for an image target (character/location/page).

    Does NOT trigger regeneration — the caller starts the corresponding step
    afterwards (typically via ``run_step_*`` with ``force_ids=[target]``).
    """
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add(step, target, feedback_text)
    fb_store.save(fb_path)


# --- .bdgen import / export ---

BDGEN_EXTENSION = ".bdgen"


def export_zip(name: str, output_root: Path | None = None) -> bytes:
    """Pack the project directory into a .bdgen (zip) blob."""
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
) -> str:
    """Extract a .bdgen blob into the output root. Returns the project name.

    The zip is expected to contain exactly one top-level folder which becomes
    the project name. If a project with the same name exists and ``overwrite``
    is False, a numeric suffix is appended.
    """
    root = projects_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        if not names:
            raise ValueError("Archive vide.")
        top_levels = {n.split("/", 1)[0] for n in names if n.strip()}
        if len(top_levels) != 1:
            raise ValueError(
                "Archive invalide : un unique dossier racine est attendu."
            )
        project_name = top_levels.pop()
        target_dir = root / project_name
        if target_dir.exists() and not overwrite:
            i = 2
            while (root / f"{project_name}_{i}").exists():
                i += 1
            new_name = f"{project_name}_{i}"
            target_dir = root / new_name
            project_name = new_name
            # Rewrite arcnames on extraction
            for member in zf.infolist():
                rel = member.filename.split("/", 1)[1] if "/" in member.filename else ""
                if not rel:
                    continue
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not member.is_dir():
                    dest.write_bytes(zf.read(member))
        else:
            if target_dir.exists() and overwrite:
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(root)
    # If config carries a different ``project`` name, normalize it to the dir name.
    cfg_path = (output_root or Path("./output")).resolve() / project_name / PROJECT_CONFIG_NAME
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if data.get("project") != project_name:
                data["project"] = project_name
                cfg_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except Exception:
            pass
    return project_name


# --- References bundle (.bdrefs) — share a cast across projects ---

BDREFS_EXTENSION = ".bdrefs"
BDREFS_MANIFEST_NAME = "manifest.json"
BDREFS_MANIFEST_VERSION = 1


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


def list_exportable_references(
    name: str, output_root: Path | None = None
) -> dict[str, list[dict]]:
    """Return entities that have a reference PNG on disk, keyed by kind.

    Used by the export UI to populate its picker. Entries the user can pick
    must have BOTH a config row and a non-empty PNG under ``references/``.
    """
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


def _entities_for_kind(config: BdGenInput, kind: str) -> list[dict]:
    if kind == "characters":
        return [c.model_dump(mode="json") for c in config.characters]
    if kind == "locations":
        return [l.model_dump(mode="json") for l in config.locations]
    if kind == "objects":
        return [o.model_dump(mode="json") for o in config.objects]
    return []


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
                raise ValueError(
                    f"Identifiant inconnu dans la configuration : {kind}/{tid}"
                )
            png = proj_dir / "references" / kind / f"{tid}.png"
            if not png.exists() or png.stat().st_size == 0:
                raise ValueError(
                    f"Référence absente sur disque : {kind}/{tid}.png. "
                    f"Lancez l'étape Références avant d'exporter."
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
            raise ValueError(
                f"Bundle invalide : {BDREFS_MANIFEST_NAME} introuvable."
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Manifest illisible : {e}")
        if manifest.get("version") != BDREFS_MANIFEST_VERSION:
            raise ValueError(
                f"Version de bundle non supportée : {manifest.get('version')}."
            )

        photos_dirname = {
            "characters": CHARACTER_PHOTOS_DIRNAME,
            "locations": LOCATION_PHOTOS_DIRNAME,
            "objects": OBJECT_PHOTOS_DIRNAME,
        }
        from .models import CharacterInput, LocationInput, ObjectInput
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
                    raise ValueError(
                        f"Entrée invalide dans le bundle ({kind}/{old_id}) : {e}"
                    )
                getattr(config, kind).append(model)

                ref_arc = f"references/{kind}/{old_id}.png"
                try:
                    ref_bytes = zf.read(ref_arc)
                except KeyError:
                    raise ValueError(
                        f"PNG manquant dans le bundle : {ref_arc}"
                    )
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


# --- Helpers ---

def _resolve_options(bd_script: BdGenScript, name: str, output_root: Path | None):
    if bd_script.generation_options is not None:
        return bd_script.generation_options
    cfg = load_config(name, output_root)
    return cfg.generation_options


def _composed_path(pages_dir: Path, target: str) -> Path | None:
    if target == "cover":
        return pages_dir / "cover.png"
    if target == "back":
        return pages_dir / "back.png"
    if target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except ValueError:
            return None
        return pages_dir / f"page_{n:02d}.png"
    return None
