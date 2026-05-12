"""Detect upstream changes (style, image model, entity text) and mark
downstream PNG artefacts as stale before the next save."""

from __future__ import annotations

from pathlib import Path

from ..models import BdGenInput, BdGenScript
from ._helpers import _coerce_generation_image_models, update_reference_prompts_for_style_change
from .constants import PROJECT_CONFIG_NAME
from .indices import mark_stale


def detect_and_mark_stale(
    name: str,
    new_config: BdGenInput,
    output_root: Path | None = None,
) -> None:
    """Compare *new_config* against the on-disk config + script and mark
    any existing reference or compose images as stale when their upstream
    data changed.

    Must be called BEFORE ``save_config`` so we can diff old vs. new.
    """
    from .lifecycle import get_project_dir

    _coerce_generation_image_models(new_config.generation_options)
    proj_dir = get_project_dir(name, output_root)
    old_path = proj_dir / PROJECT_CONFIG_NAME
    if not old_path.exists():
        return
    try:
        old_cfg = BdGenInput.load(old_path)
    except Exception:
        return
    _coerce_generation_image_models(old_cfg.generation_options)

    script_path = proj_dir / "bdgen-script.json"
    if not script_path.exists():
        return
    try:
        bd_script = BdGenScript.load(script_path)
    except Exception:
        return

    script_changed = False
    old_style = old_cfg.style.model_dump()
    new_style = new_config.style.model_dump()
    style_changed = old_style != new_style
    old_compose_model = old_cfg.generation_options.image_model.model_dump()
    new_compose_model = new_config.generation_options.image_model.model_dump()
    compose_model_changed = old_compose_model != new_compose_model
    old_reference_model = old_cfg.generation_options.reference_image_model().model_dump()
    new_reference_model = new_config.generation_options.reference_image_model().model_dump()
    reference_model_changed = old_reference_model != new_reference_model

    if style_changed:
        ref_ids: list[str] = []
        for c in bd_script.characters:
            ref_png = proj_dir / "references" / "characters" / f"{c.id}.png"
            if ref_png.exists():
                ref_ids.append(c.id)
        for l in bd_script.locations:
            ref_png = proj_dir / "references" / "locations" / f"{l.id}.png"
            if ref_png.exists():
                ref_ids.append(l.id)
        for o in bd_script.objects:
            ref_png = proj_dir / "references" / "objects" / f"{o.id}.png"
            if ref_png.exists():
                ref_ids.append(o.id)
        if ref_ids:
            mark_stale(proj_dir, "references", ref_ids)

        compose_ids: list[str] = []
        if bd_script.cover is not None:
            cover_png = proj_dir / "pages" / "cover.png"
            if cover_png.exists():
                compose_ids.append("cover")
        for p in bd_script.pages:
            page_png = proj_dir / "pages" / f"page_{p.page_number:02d}.png"
            if page_png.exists():
                compose_ids.append(f"page_{p.page_number}")
        if bd_script.back_cover is not None:
            back_png = proj_dir / "pages" / "back.png"
            if back_png.exists():
                compose_ids.append("back")
        if compose_ids:
            mark_stale(proj_dir, "compose", compose_ids)

        update_reference_prompts_for_style_change(bd_script, old_cfg.style, new_config.style)
        bd_script.style = new_config.style
        bd_script.generation_options = new_config.generation_options
        bd_script.save(script_path)
        return

    if reference_model_changed:
        ref_ids: list[str] = []
        for c in bd_script.characters:
            ref_png = proj_dir / "references" / "characters" / f"{c.id}.png"
            if ref_png.exists():
                ref_ids.append(c.id)
        for l in bd_script.locations:
            ref_png = proj_dir / "references" / "locations" / f"{l.id}.png"
            if ref_png.exists():
                ref_ids.append(l.id)
        for o in bd_script.objects:
            ref_png = proj_dir / "references" / "objects" / f"{o.id}.png"
            if ref_png.exists():
                ref_ids.append(o.id)
        if ref_ids:
            mark_stale(proj_dir, "references", ref_ids)

    if compose_model_changed:
        compose_ids: list[str] = []
        if bd_script.cover is not None:
            cover_png = proj_dir / "pages" / "cover.png"
            if cover_png.exists():
                compose_ids.append("cover")
        for p in bd_script.pages:
            page_png = proj_dir / "pages" / f"page_{p.page_number:02d}.png"
            if page_png.exists():
                compose_ids.append(f"page_{p.page_number}")
        if bd_script.back_cover is not None:
            back_png = proj_dir / "pages" / "back.png"
            if back_png.exists():
                compose_ids.append("back")
        if compose_ids:
            mark_stale(proj_dir, "compose", compose_ids)

    old_chars = {c.id: c for c in old_cfg.characters}
    for nc in new_config.characters:
        oc = old_chars.get(nc.id)
        if not oc:
            continue
        fields_changed = (
            nc.physical_description != oc.physical_description or nc.outfit != oc.outfit or nc.name != oc.name
        )
        if fields_changed:
            ref_png = proj_dir / "references" / "characters" / f"{nc.id}.png"
            if ref_png.exists():
                mark_stale(proj_dir, "references", nc.id)

    old_locs = {l.id: l for l in old_cfg.locations}
    for nl in new_config.locations:
        ol = old_locs.get(nl.id)
        if not ol:
            continue
        if nl.description != ol.description or nl.name != ol.name:
            ref_png = proj_dir / "references" / "locations" / f"{nl.id}.png"
            if ref_png.exists():
                mark_stale(proj_dir, "references", nl.id)

    old_objs = {o.id: o for o in old_cfg.objects}
    for no in new_config.objects:
        oo = old_objs.get(no.id)
        if not oo:
            continue
        if no.description != oo.description or no.name != oo.name:
            ref_png = proj_dir / "references" / "objects" / f"{no.id}.png"
            if ref_png.exists():
                mark_stale(proj_dir, "references", no.id)

    if bd_script.generation_options != new_config.generation_options:
        bd_script.generation_options = new_config.generation_options
        script_changed = True
    if script_changed:
        bd_script.save(script_path)
