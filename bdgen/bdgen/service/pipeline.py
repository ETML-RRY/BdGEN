"""Pipeline step runners executed by the JobManager (worker thread)."""

from __future__ import annotations

from pathlib import Path

from .. import compose as compose_module
from .. import references as references_module
from .. import script as script_module
from .. import upscale as upscale_module
from ..feedback import FeedbackStore, feedback_path_for
from ..models import BdGenScript
from ..progress import InterruptFlag, ProgressReporter
from ._helpers import _resolve_options
from ._paths import _composed_path
from .config import load_config
from .constants import PROJECT_CONFIG_NAME
from .indices import (
    clear_stale,
    read_quality_index,
    write_quality_index,
)
from .photos import list_character_photos, list_location_photos, list_object_photos
from .style_refs import attach_existing_reference_images, get_style_reference_path


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


def run_step_script(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    preview_pages: int | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    config = load_config(name, output_root)
    feedback_store = FeedbackStore.load_or_empty(feedback_path_for(config.generation_options.script_path))
    feedback = feedback_store.get_for("script")
    bd_script = script_module.generate_script(
        config,
        input_path=get_project_dir(name, output_root) / PROJECT_CONFIG_NAME,
        feedback=feedback,
        preview_pages=preview_pages,
        script_path=config.generation_options.script_path,
        reporter=reporter,
        interrupt=interrupt,
        stats_project_dir=get_project_dir(name, output_root),
    )
    attach_existing_reference_images(get_project_dir(name, output_root), bd_script)
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
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    if attach_existing_reference_images(proj_dir, bd_script):
        bd_script.save(script_path)
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
            bd_script,
            opts.references,
            opts.image_model,
            script_path=script_path,
            feedback_store=feedback_store,
            reporter=reporter,
            interrupt=interrupt,
            style_ref=style_ref,
            character_photos=character_photos,
            location_photos=location_photos,
            object_photos=object_photos,
            stats_project_dir=proj_dir,
            allow_style_copy=bool(getattr(bd_script, "allow_style_copy", False)),
        )
    finally:
        # Even on partial completion (interruption), record what landed.
        _record_qualities(proj_dir, "references", target_paths, pre_existing, quality_used)
        _clear_stale_for_regenerated(proj_dir, "references", target_paths, pre_existing, force_ids)
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
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    if attach_existing_reference_images(proj_dir, bd_script):
        bd_script.save(script_path)
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
            bd_script,
            opts,
            pages_dir,
            feedback_store=feedback_store,
            reporter=reporter,
            interrupt=interrupt,
            style_ref=style_ref,
            stats_project_dir=proj_dir,
        )
    finally:
        _record_qualities(proj_dir, "compose", target_paths, pre_existing, quality_used)
        _clear_stale_for_regenerated(proj_dir, "compose", target_paths, pre_existing, force_ids)
    return out


def run_step_upscale(
    name: str,
    reporter: ProgressReporter,
    interrupt: InterruptFlag,
    output_root: Path | None = None,
    force_ids: list[str] | None = None,
) -> Path:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    if attach_existing_reference_images(proj_dir, bd_script):
        bd_script.save(script_path)
    opts = _resolve_options(bd_script, name, output_root)
    return upscale_module.upscale_pages(
        bd_script,
        project_dir=proj_dir,
        options=opts.upscale,
        reporter=reporter,
        interrupt=interrupt,
        force_ids=force_ids,
        stats_project_dir=proj_dir,
    )
