"""Project config (``bdgen.json``) and script load/save."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from ..models import BdGenInput, BdGenScript
from ._helpers import _coerce_openai_image_model
from .constants import PROJECT_CONFIG_NAME


def load_config(name: str, output_root: Path | None = None) -> BdGenInput:
    """Load the bdgen.json for a project (raises if missing)."""
    from .lifecycle import get_project_dir

    p = get_project_dir(name, output_root) / PROJECT_CONFIG_NAME
    if not p.exists():
        raise FileNotFoundError(f"bdgen.json absent pour le projet « {name} »")
    config = BdGenInput.load(p)
    _coerce_openai_image_model(config.generation_options.image_model)
    return config


def save_config(config: BdGenInput, output_root: Path | None = None) -> Path:
    """Write bdgen.json into the project directory and ensure the dir exists.

    The project name comes from ``config.project``; ``output_root`` defaults to
    ``config.output_root`` then the global default.
    """
    if not config.project:
        raise ValueError("config.project doit être défini.")
    _coerce_openai_image_model(config.generation_options.image_model)
    config.output_root = output_root or config.output_root or Path("./output")
    proj_dir = config.output_root / config.project
    proj_dir.mkdir(parents=True, exist_ok=True)
    config_path = proj_dir / PROJECT_CONFIG_NAME
    payload = config.to_portable_dict(config_path)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def load_script_if_present(name: str, output_root: Path | None = None) -> BdGenScript | None:
    from .lifecycle import get_project_dir
    from .style_refs import attach_existing_reference_images

    p = get_project_dir(name, output_root) / "bdgen-script.json"
    if not p.exists():
        return None
    try:
        bd_script = BdGenScript.load(p)
        if attach_existing_reference_images(p.parent, bd_script):
            bd_script.save(p)
        return bd_script
    except Exception:
        return None


def _force_writable_and_retry(func, target, _exc_info):
    # rmtree handler: clear the read-only bit (Windows often sets it on cached
    # files inside OneDrive) and retry the failing op.
    try:
        os.chmod(target, stat.S_IWRITE)
    except OSError:
        pass
    func(target)
