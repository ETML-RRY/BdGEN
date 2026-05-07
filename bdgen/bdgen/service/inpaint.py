"""Masked image inpainting and image-feedback recording."""

from __future__ import annotations

import base64
import io as _io
from pathlib import Path
from typing import Literal

from .. import secret_store
from .. import stats as stats_module
from ..feedback import FeedbackStore, feedback_path_for
from ..models import BdGenScript
from ._helpers import _resolve_options
from ._paths import _composed_path


def inpaint_image(
    name: str,
    step: str,
    target_id: str,
    mask_bytes: bytes,
    prompt: str,
    output_root: Path | None = None,
) -> Path:
    """Apply masked inpainting to an existing generated image.

    Loads the current PNG from disk, resizes the user-supplied mask to match,
    then calls ``images.edit`` with the mask so only the painted region is
    regenerated. The result replaces the original file atomically.
    """
    from PIL import Image as _Image

    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    if not script_path.exists():
        raise FileNotFoundError("Script introuvable. Lancez d'abord l'étape Scénario.")

    bd_script = BdGenScript.load(script_path)
    opts = _resolve_options(bd_script, name, output_root)

    if step == "compose":
        pages_dir = proj_dir / "pages"
        image_path = _composed_path(pages_dir, target_id)
        size = "1024x1536"
    elif step == "references":
        image_path = _reference_path_for_id(proj_dir, bd_script, target_id)
        size = "1024x1024"
    else:
        raise ValueError(f"Étape invalide : {step}")

    if image_path is None or not image_path.exists():
        raise FileNotFoundError(f"Image source introuvable pour « {target_id} ».")

    img = _Image.open(image_path).convert("RGBA")
    w, h = img.size

    mask_img = _Image.open(_io.BytesIO(mask_bytes)).convert("RGBA")
    if mask_img.size != (w, h):
        mask_img = mask_img.resize((w, h), _Image.NEAREST)
    # Binarize after resize to keep the mask strictly transparent/opaque
    pixels = mask_img.load()
    for py in range(mask_img.height):
        for px in range(mask_img.width):
            r, g, b, a = pixels[px, py]
            pixels[px, py] = (r, g, b, 0 if a < 128 else 255)

    img_buf = _io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    mask_buf = _io.BytesIO()
    mask_img.save(mask_buf, format="PNG")
    mask_data = mask_buf.getvalue()

    if opts.image_model.provider != "openai":
        raise NotImplementedError(f"L'inpainting n'est pas supporté pour le provider « {opts.image_model.provider} ».")
    client = secret_store.openai_client()

    # gpt-image-2 inpainting is prompt-based: explicitly instruct the model to
    # preserve the rest of the image so it doesn't regenerate everything.
    guided_prompt = (
        f"{prompt}. Keep all other parts of the image exactly as they are, only modify the area indicated by the mask."
    )

    started_at, started = stats_module.start_timer()
    result = client.images.edit(
        model=opts.image_model.model,
        image=("image.png", img_bytes, "image/png"),
        mask=("mask.png", mask_data, "image/png"),
        prompt=guided_prompt,
        size=size,
        quality=opts.image_model.quality,
    )
    if step == "compose":
        _inpaint_kind = "cover" if target_id == "cover" else "back_cover" if target_id == "back" else "page"
    else:
        _kind_map = {"characters": "character", "locations": "location", "objects": "object"}
        _inpaint_kind = _kind_map.get(image_path.parent.name, "reference")
    stats_module.record_event(
        proj_dir,
        step=step,
        target_id=target_id,
        target_kind=_inpaint_kind,
        operation="inpaint",
        provider=opts.image_model.provider,
        model=opts.image_model.model,
        timer=stats_module.stop_timer(started_at, started),
        usage=stats_module.normalise_usage(getattr(result, "usage", None)),
        prompt=guided_prompt,
        input_images=2,
        artifact=image_path,
        extra={"retouch": True, "quality": opts.image_model.quality},
    )

    result_bytes = base64.b64decode(result.data[0].b64_json)
    tmp = image_path.with_suffix(image_path.suffix + ".tmp")
    tmp.write_bytes(result_bytes)
    tmp.replace(image_path)
    return image_path


def _reference_path_for_id(proj_dir: Path, bd_script: BdGenScript, target_id: str) -> Path | None:
    """Return the on-disk PNG path for a reference target id."""
    for kind in ("characters", "locations", "objects"):
        p = proj_dir / "references" / kind / f"{target_id}.png"
        if p.exists():
            return p
    return None


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
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    fb_path = feedback_path_for(script_path)
    fb_store = FeedbackStore.load_or_empty(fb_path)
    fb_store.add(step, target, feedback_text)
    fb_store.save(fb_path)
