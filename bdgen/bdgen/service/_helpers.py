"""Shared private helpers used by multiple service submodules."""

from __future__ import annotations

from pathlib import Path

from ..models import BdGenScript
from .constants import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_PROVIDER


def _coerce_openai_image_model(image_model) -> None:
    """Images are OpenAI-only; xAI remains available for script generation."""
    if image_model.provider == DEFAULT_IMAGE_PROVIDER:
        return
    image_model.provider = DEFAULT_IMAGE_PROVIDER
    image_model.model = DEFAULT_IMAGE_MODEL


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
