"""Style-reference image and reference-image attachment helpers."""

from __future__ import annotations

from pathlib import Path

from ..models import BdGenScript
from .constants import STYLE_REF_NAME


def get_style_reference_path(proj_dir: Path) -> Path | None:
    """Return the style-reference PNG if it exists, else None."""
    p = proj_dir / STYLE_REF_NAME
    return p if p.exists() and p.stat().st_size > 0 else None


def save_style_reference(name: str, image_bytes: bytes, output_root: Path | None = None) -> Path:
    """Save image_bytes as the project's style reference."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    proj_dir.mkdir(parents=True, exist_ok=True)
    p = proj_dir / STYLE_REF_NAME
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(image_bytes)
    tmp.replace(p)
    return p


def attach_existing_reference_images(proj_dir: Path, bd_script: BdGenScript) -> bool:
    """Populate script reference_image fields from canonical copied PNGs.

    This matters for duplicated projects: their generated reference images may
    already be present on disk, so the references step can be skipped by state
    derivation. Without these fields, compose would only receive text prompts
    and would not pass the copied reference sheets as input images.
    """
    changed = False
    refs_dir = proj_dir / "references"
    for character in bd_script.characters:
        p = refs_dir / "characters" / f"{character.id}.png"
        if p.exists() and p.stat().st_size > 0 and character.reference_image != p:
            character.reference_image = p
            changed = True
    for location in bd_script.locations:
        p = refs_dir / "locations" / f"{location.id}.png"
        if p.exists() and p.stat().st_size > 0 and location.reference_image != p:
            location.reference_image = p
            changed = True
    for obj in bd_script.objects:
        p = refs_dir / "objects" / f"{obj.id}.png"
        if p.exists() and p.stat().st_size > 0 and obj.reference_image != p:
            obj.reference_image = p
            changed = True
    return changed
