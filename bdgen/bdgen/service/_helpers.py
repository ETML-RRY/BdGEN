"""Shared private helpers used by multiple service submodules."""

from __future__ import annotations

from pathlib import Path

from ..models import BdGenScript, Style
from .constants import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_PROVIDER


def _coerce_openai_image_model(image_model) -> None:
    """Images are OpenAI-only; xAI remains available for script generation."""
    if image_model.provider == DEFAULT_IMAGE_PROVIDER:
        return
    image_model.provider = DEFAULT_IMAGE_PROVIDER
    image_model.model = DEFAULT_IMAGE_MODEL


def update_reference_prompts_for_style_change(
    bd_script: BdGenScript, old_style: Style, new_style: Style
) -> bool:
    """Replace old style values with new ones in every reference_prompt.

    The setup LLM is instructed to quote each style field verbatim inside
    reference_prompts. When the project style changes we can therefore do a
    reliable string replacement so the image model doesn't receive conflicting
    instructions (old style baked into the prompt body vs. new style in the
    enforcement block at the end).

    Returns True if any prompt was modified.
    """
    style_fields = (
        "art_style",
        "color_palette",
        "line_work",
        "character_rendering",
        "stylization_level",
        "negative_constraints",
    )

    replacements: list[tuple[str, str]] = []
    for field in style_fields:
        old_val = getattr(old_style, field)
        new_val = getattr(new_style, field)
        if old_val and old_val != new_val:
            replacements.append((old_val, new_val or ""))

    if not replacements:
        return False

    def _patch(prompt: str) -> str:
        for old_val, new_val in replacements:
            if old_val in prompt:
                prompt = prompt.replace(old_val, new_val)
        return prompt

    changed = False
    for c in bd_script.characters:
        patched = _patch(c.reference_prompt)
        if patched != c.reference_prompt:
            c.reference_prompt = patched
            changed = True
    for loc in bd_script.locations:
        patched = _patch(loc.reference_prompt)
        if patched != loc.reference_prompt:
            loc.reference_prompt = patched
            changed = True
    for obj in bd_script.objects:
        patched = _patch(obj.reference_prompt)
        if patched != obj.reference_prompt:
            obj.reference_prompt = patched
            changed = True
    return changed


def _resolve_options(bd_script: BdGenScript, name: str, output_root: Path | None):
    from .config import load_config  # local import to avoid cycle

    try:
        opts = load_config(name, output_root).generation_options
    except FileNotFoundError:
        if bd_script.generation_options is not None:
            opts = bd_script.generation_options
        else:
            raise
    _coerce_openai_image_model(opts.image_model)
    return opts
