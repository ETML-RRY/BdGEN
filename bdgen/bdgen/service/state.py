"""Project state derivation, structure statistics, and listing summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import stats as stats_module
from ..models import BdGenInput, BdGenScript
from . import ProjectSummary
from .config import load_script_if_present
from .constants import (
    PROJECT_CONFIG_NAME,
    THUMB_MAX_H,
    THUMB_MAX_W,
    THUMBNAIL_NAME,
    UPSCALED_DIRNAME,
    Step,
)


def project_statistics(name: str, output_root: Path | None = None) -> dict:
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Projet inconnu : {name}")

    script = load_script_if_present(name, output_root)
    stats_payload = stats_module.load_stats(proj_dir)
    events = list(stats_payload.get("events") or [])
    aggregate = stats_module.aggregate_events(events)
    structure = _structure_statistics(script, proj_dir)
    return {
        "project": name,
        "updated_at": stats_payload.get("updated_at"),
        "structure": structure,
        "generation": aggregate,
        "events": events,
        "pricing_note": (
            "Coûts approximatifs en USD, calculés avec une table locale de prix "
            "par million de tokens. Les appels sans usage token exposé gardent "
            "la durée mais pas de coût estimé."
        ),
    }


def _structure_statistics(script: BdGenScript | None, proj_dir: Path) -> dict:
    if script is None:
        return {
            "pages": 0,
            "panels": 0,
            "bubbles": 0,
            "generated_words": 0,
            "characters": 0,
            "locations": 0,
            "objects": 0,
            "references_expected": 0,
            "references_generated": 0,
            "references_used_unique": 0,
            "references_used_total": 0,
            "composed_images": _count_files(proj_dir / "pages", "*.png"),
            "upscaled_images": _count_files(proj_dir / UPSCALED_DIRNAME, "*.*"),
        }

    pages = len(script.pages)
    panels = sum(len(p.panels) for p in script.pages)
    bubbles = sum(len(panel.dialogs) for p in script.pages for panel in p.panels)
    generated_text_parts: list[str] = [
        script.metadata.title,
        script.metadata.author,
        script.style.art_style,
    ]
    for c in script.characters:
        generated_text_parts.extend([c.name, c.physical_description, c.outfit or "", c.reference_prompt])
    for l in script.locations:
        generated_text_parts.extend([l.name, l.description, l.reference_prompt])
    for o in script.objects:
        generated_text_parts.extend([o.name, o.description, o.reference_prompt])
    if script.cover is not None:
        generated_text_parts.extend(
            [
                script.cover.scene_description,
                script.cover.title_placement or "",
                script.cover.subtitle or "",
                script.cover.tagline or "",
            ]
        )
    if script.back_cover is not None:
        generated_text_parts.extend(
            [
                script.back_cover.synopsis_blurb,
                script.back_cover.scene_description or "",
                script.back_cover.tagline or "",
                script.back_cover.layout_notes or "",
            ]
        )
    used_refs: list[str] = []
    for p in script.pages:
        generated_text_parts.append(p.layout or "")
        for panel in p.panels:
            generated_text_parts.extend(
                [
                    panel.location,
                    panel.shot or "",
                    panel.scene_description,
                    panel.narration or "",
                    " ".join(panel.sound_effects),
                ]
            )
            used_refs.extend(panel.characters)
            used_refs.append(panel.location)
            used_refs.extend(panel.objects)
            for dialog in panel.dialogs:
                generated_text_parts.extend([dialog.speaker, dialog.type, dialog.text])

    reference_paths = []
    for c in script.characters:
        reference_paths.append(proj_dir / "references" / "characters" / f"{c.id}.png")
    for l in script.locations:
        reference_paths.append(proj_dir / "references" / "locations" / f"{l.id}.png")
    for o in script.objects:
        reference_paths.append(proj_dir / "references" / "objects" / f"{o.id}.png")

    return {
        "pages": pages,
        "panels": panels,
        "bubbles": bubbles,
        "generated_words": stats_module.word_count("\n".join(generated_text_parts)),
        "characters": len(script.characters),
        "locations": len(script.locations),
        "objects": len(script.objects),
        "cover": script.cover is not None,
        "back_cover": script.back_cover is not None,
        "references_expected": len(reference_paths),
        "references_generated": sum(1 for p in reference_paths if p.exists() and p.stat().st_size > 0),
        "references_used_unique": len(set(used_refs)),
        "references_used_total": len(used_refs),
        "composed_images": _count_files(proj_dir / "pages", "*.png"),
        "upscaled_images": _count_files(proj_dir / UPSCALED_DIRNAME, "*.*"),
    }


def _count_files(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for p in directory.glob(pattern) if p.is_file())


def derive_state(proj_dir: Path) -> Step:
    """Best-effort guess of what step the user should land on.

    The UI may override this (e.g. user clicks a step explicitly), but when
    reopening a project this drives the default landing step.
    """
    config_path = proj_dir / PROJECT_CONFIG_NAME
    script_path = proj_dir / "bdgen-script.json"
    # No script yet means the project hasn't moved past its initial setup:
    # land on "preparation" so a freshly created project (config saved, no
    # script) opens on step 1 rather than skipping ahead to "script".
    if not script_path.exists():
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
    total = len(bd_script.characters) + len(bd_script.locations) + len(bd_script.objects)
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
        thumbnail_rel=_ensure_thumbnail(proj_dir),
    )


def _ensure_thumbnail(proj_dir: Path) -> str | None:
    """Generate thumbnail.jpg from the cover/first page when needed.

    Returns the relative path "thumbnail.jpg" if a thumbnail exists (or was
    just created), None if no source image is available yet.
    """
    from PIL import Image  # lazy import — Pillow is a project dependency

    pages_dir = proj_dir / "pages"
    if not pages_dir.is_dir():
        return None
    cover = pages_dir / "cover.png"
    if cover.exists():
        source = cover
    else:
        candidates = sorted(pages_dir.glob("page_*.png"))
        if not candidates:
            return None
        source = candidates[0]

    thumb_path = proj_dir / THUMBNAIL_NAME
    if not thumb_path.exists() or source.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            img = Image.open(source)
            img.thumbnail((THUMB_MAX_W, THUMB_MAX_H), Image.LANCZOS)
            img.convert("RGB").save(thumb_path, "JPEG", quality=85)
        except Exception:
            return None

    return THUMBNAIL_NAME
