"""Targeted refinement: append feedback and regenerate a single script entity.

These functions are synchronous (called outside the JobManager). They write to
the feedback store, ask the script engine to regenerate the targeted entity,
save the script, and flag any stale downstream PNG so the UI can offer a
one-click regeneration.
"""

from __future__ import annotations

from pathlib import Path

from .. import script as script_module
from ..feedback import FeedbackStore, feedback_path_for
from ..models import BdGenScript
from ..progress import ProgressReporter
from .indices import mark_stale, read_coherence_index, write_coherence_index


def add_feedback_and_regenerate_character(
    name: str,
    character_id: str,
    feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", character_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_character(bd_script, character_id, feedback_text, reporter, stats_project_dir=proj_dir)
    bd_script.save(script_path)
    # The on-disk reference PNG (if any) was generated against the previous
    # text and no longer matches; flag it so the UI can offer a one-click
    # regeneration without asking the user to re-state the change.
    ref_png = proj_dir / "references" / "characters" / f"{character_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", character_id)
    return bd_script


def add_feedback_and_regenerate_location(
    name: str,
    location_id: str,
    feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", location_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_location(bd_script, location_id, feedback_text, reporter, stats_project_dir=proj_dir)
    bd_script.save(script_path)
    ref_png = proj_dir / "references" / "locations" / f"{location_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", location_id)
    return bd_script


def add_feedback_and_regenerate_object(
    name: str,
    object_id: str,
    feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", object_id, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_object(bd_script, object_id, feedback_text, reporter, stats_project_dir=proj_dir)
    bd_script.save(script_path)
    ref_png = proj_dir / "references" / "objects" / f"{object_id}.png"
    if ref_png.exists():
        mark_stale(proj_dir, "references", object_id)
    return bd_script


def add_feedback_and_regenerate_cover(
    name: str,
    feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", "cover", feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_cover(bd_script, feedback_text, reporter, stats_project_dir=proj_dir)
    bd_script.save(script_path)
    if (proj_dir / "pages" / "cover.png").exists():
        mark_stale(proj_dir, "compose", "cover")
    return bd_script


def add_feedback_and_regenerate_back_cover(
    name: str,
    feedback_text: str,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add("script", "back", feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_back_cover(bd_script, feedback_text, reporter, stats_project_dir=proj_dir)
    bd_script.save(script_path)
    if (proj_dir / "pages" / "back.png").exists():
        mark_stale(proj_dir, "compose", "back")
    return bd_script


def add_feedback_and_regenerate_page(
    name: str,
    page_number: int,
    feedback_text: str,
    cascade: bool = False,
    output_root: Path | None = None,
    reporter: ProgressReporter | None = None,
) -> BdGenScript:
    """Rewrite one page. If ``cascade`` is True, drop all subsequent pages so
    the next ``run_step_script`` call regenerates them with the new context.
    """
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    target = f"page_{page_number}"
    fb_store.add("script", target, feedback_text)
    fb_store.save(fb_path)
    script_module.regenerate_page(bd_script, page_number, feedback_text, reporter, stats_project_dir=proj_dir)
    if cascade:
        script_module.truncate_pages_from(bd_script, page_number + 1)
    bd_script.save(script_path)
    coh_idx = read_coherence_index(proj_dir)
    coh_idx["issues"] = [i for i in coh_idx.get("issues", []) if i.get("page_number") != page_number]
    coh_idx["suggestions"] = [s for s in coh_idx.get("suggestions", []) if s.get("page_number") != page_number]
    coh_idx["flagged_pages"] = [p for p in coh_idx.get("flagged_pages", []) if p != page_number]
    write_coherence_index(proj_dir, coh_idx)
    cm = proj_dir / "pages" / f"page_{page_number:02d}.png"
    if cm.exists():
        mark_stale(proj_dir, "compose", target)
    return bd_script
