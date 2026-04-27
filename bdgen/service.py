"""High-level project-oriented API used by the web server (and any other UI).

This module is the boundary between the generation engine (script.py,
references.py, wireframes.py, compose.py) and any user interface. The engine
modules know nothing about projects-on-disk, zip files, or HTTP; the service
module handles all of that and dispatches to the engine with the right
reporter/interrupt/feedback wiring.
"""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from . import compose as compose_module
from . import references as references_module
from . import script as script_module
from . import wireframes as wireframes_module
from .feedback import FeedbackStore, feedback_path_for
from .models import BdGenInput, BdGenScript
from .progress import InterruptFlag, ProgressReporter

Step = Literal["preparation", "script", "references", "wireframes", "compose", "done"]
Quality = Literal["low", "medium", "high"]
PROJECT_CONFIG_NAME = "bdgen.json"
QUALITY_INDEX_NAME = "bdgen-quality.json"
STYLE_REF_NAME = "bdgen-style-ref.png"


@dataclass
class ProjectSummary:
    """Light-weight project description for listings."""
    name: str
    title: str | None
    author: str | None
    state: Step
    page_count: int | None
    pages_written: int
    references_ready: int
    references_total: int
    wireframes_ready: int
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


# --- State derivation ---

def derive_state(proj_dir: Path) -> Step:
    """Best-effort guess of what step the user should land on.

    The UI may override this (e.g. user clicks "Esquisses" explicitly), but
    when reopening a project this drives the default landing step.
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
    total = len(bd_script.characters) + len(bd_script.locations)
    ready = 0
    for c in bd_script.characters:
        if (refs_dir / "characters" / f"{c.id}.png").exists():
            ready += 1
    for l in bd_script.locations:
        if (refs_dir / "locations" / f"{l.id}.png").exists():
            ready += 1
    return total, ready


def _wireframes_progress(proj_dir: Path, bd_script: BdGenScript) -> tuple[int, int]:
    wf_dir = proj_dir / "wireframes"
    targets = []
    if bd_script.cover is not None:
        targets.append(wf_dir / "cover.png")
    for p in bd_script.pages:
        targets.append(wf_dir / f"page_{p.page_number:02d}.png")
    if bd_script.back_cover is not None:
        targets.append(wf_dir / "back.png")
    return len(targets), sum(1 for t in targets if t.exists())


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
    title: str | None = None
    author: str | None = None
    target_pages: int | None = None
    if config_path.exists():
        try:
            cfg = BdGenInput.load(config_path)
            title = cfg.metadata.title
            author = cfg.metadata.author
            target_pages = cfg.structure.page_count
        except Exception:
            pass
    bd_script: BdGenScript | None = None
    if script_path.exists():
        try:
            bd_script = BdGenScript.load(script_path)
            if title is None:
                title = bd_script.metadata.title
            if author is None:
                author = bd_script.metadata.author
        except Exception:
            pass
    pages_written = len(bd_script.pages) if bd_script else 0
    refs_total = refs_ready = wf_ready = pages_composed = 0
    if bd_script is not None:
        refs_total, refs_ready = _references_progress(proj_dir, bd_script)
        _, wf_ready = _wireframes_progress(proj_dir, bd_script)
        _, pages_composed = _composed_progress(proj_dir, bd_script)
    pdf = proj_dir / f"{proj_dir.name}.pdf"
    state = derive_state(proj_dir)
    updated = max(
        (p.stat().st_mtime for p in proj_dir.iterdir()),
        default=proj_dir.stat().st_mtime,
    )
    return ProjectSummary(
        name=proj_dir.name,
        title=title,
        author=author,
        state=state,
        page_count=target_pages,
        pages_written=pages_written,
        references_ready=refs_ready,
        references_total=refs_total,
        wireframes_ready=wf_ready,
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
            for kind in ("characters", "locations"):
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
    pre_existing = {tid for tid, p in target_paths.items() if p.exists()}

    style_ref = get_style_reference_path(proj_dir)
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(script_path))
    try:
        references_module.generate_references(
            bd_script, opts.references, opts.image_model,
            script_path=script_path, feedback_store=feedback_store,
            reporter=reporter, interrupt=interrupt,
            style_ref=style_ref,
        )
    finally:
        # Even on partial completion (interruption), record what landed.
        _record_qualities(proj_dir, "references", target_paths, pre_existing, quality_used)
    bd_script.save(script_path)
    return bd_script


def run_step_wireframes(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    force_ids: list[str] | None = None,
) -> None:
    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    opts = _resolve_options(bd_script, name, output_root)
    wf_dir = proj_dir / "wireframes"
    if force_ids:
        for fid in force_ids:
            p = _wireframe_path(wf_dir, fid)
            if p and p.exists():
                p.unlink()
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(script_path))
    wireframes_module.generate_wireframes(
        bd_script, opts, wf_dir,
        feedback_store=feedback_store,
        reporter=reporter, interrupt=interrupt,
    )


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
    wf_dir = proj_dir / "wireframes"
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
            wf_dir if wf_dir.exists() else None,
            feedback_store=feedback_store,
            reporter=reporter, interrupt=interrupt,
            style_ref=style_ref,
        )
    finally:
        _record_qualities(proj_dir, "compose", target_paths, pre_existing, quality_used)
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
    qidx = read_quality_index(proj_dir)
    if character_id in qidx.get("references", {}):
        qidx["references"].pop(character_id, None)
        write_quality_index(proj_dir, qidx)

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
    qidx = read_quality_index(proj_dir)
    if location_id in qidx.get("references", {}):
        qidx["references"].pop(location_id, None)
        write_quality_index(proj_dir, qidx)

    return {
        "deleted": True,
        "location_id": location_id,
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
    return bd_script


def record_image_feedback(
    name: str,
    step: Literal["references", "wireframes", "compose"],
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


# --- Helpers ---

def _resolve_options(bd_script: BdGenScript, name: str, output_root: Path | None):
    if bd_script.generation_options is not None:
        return bd_script.generation_options
    cfg = load_config(name, output_root)
    return cfg.generation_options


def _wireframe_path(wf_dir: Path, target: str) -> Path | None:
    if target == "cover":
        return wf_dir / "cover.png"
    if target == "back":
        return wf_dir / "back.png"
    if target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except ValueError:
            return None
        return wf_dir / f"page_{n:02d}.png"
    return None


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
