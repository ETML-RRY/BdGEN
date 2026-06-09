"""Image upscaling via Pruna P-Image-Upscale on Replicate.

Calls the ``prunaai/p-image-upscale`` model through the Replicate API.
Requires a ``REPLICATE_API_TOKEN`` from the BdGEN vault or environment.
"""
from __future__ import annotations

import base64
from pathlib import Path

from . import secret_store
from .models import BdGenScript, UpscaleOptions
from .pdf_export import assemble_pdf
from .progress import InterruptFlag, ProgressEvent, ProgressReporter
from .stats import record_event, start_timer, stop_timer

UPSCALED_DIRNAME = "pages_upscaled"
REPLICATE_MODEL = "prunaai/p-image-upscale"


def is_available() -> bool:
    return bool(secret_store.get_secret("REPLICATE_API_TOKEN"))


def upscale_pages(
    bd_script: BdGenScript,
    project_dir: Path,
    options: UpscaleOptions,
    reporter: ProgressReporter,
    interrupt: InterruptFlag | None = None,
    force: bool = False,
    force_ids: list[str] | None = None,
    stats_project_dir: Path | None = None,
) -> Path:
    """Upscale every composed page via Replicate."""
    _ensure_replicate()

    pages_dir = project_dir / "pages"
    output_dir = options.output_dir or project_dir / UPSCALED_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, Path, Path]] = []
    if bd_script.cover is not None:
        targets.append(("cover", pages_dir / "cover.png", output_dir / f"cover.{options.output_format}"))
    for page in bd_script.pages:
        targets.append(
            (
                f"page_{page.page_number}",
                pages_dir / f"page_{page.page_number:02d}.png",
                output_dir / f"page_{page.page_number:02d}.{options.output_format}",
            )
        )
    if bd_script.back_cover is not None:
        targets.append(("back", pages_dir / "back.png", output_dir / f"back.{options.output_format}"))

    forced = set(force_ids or [])
    total = len(targets)
    processed = 0
    local_interrupt = interrupt or InterruptFlag()

    for target_id, src, dst in targets:
        local_interrupt.check()
        processed += 1
        should_force = force or target_id in forced
        if not src.exists():
            reporter.emit(
                ProgressEvent(
                    step="upscale",
                    phase=f"{target_id}_missing_source",
                    message=f"Source absente pour {target_id}, étape ignorée.",
                    current=processed,
                    total=total,
                    extra={
                        "id": target_id,
                        "i18n_key": "progressEvents.upscale.missingSource",
                    },
                )
            )
            continue
        if dst.exists() and not should_force:
            reporter.emit(
                ProgressEvent(
                    step="upscale",
                    phase=f"{target_id}_skipped",
                    message=f"Upscale déjà présent pour {target_id}, on conserve.",
                    current=processed,
                    total=total,
                    artifact=str(dst),
                    extra={
                        "id": target_id,
                        "i18n_key": "progressEvents.upscale.skipped",
                    },
                )
            )
            continue

        reporter.emit(
            ProgressEvent(
                step="upscale",
                phase=target_id,
                message=f"Upscale de {target_id} via Replicate…",
                current=processed,
                total=total,
                extra={
                    "id": target_id,
                    "i18n_key": "progressEvents.upscale.generating",
                },
            )
        )
        started_at, started = start_timer()
        _upscale_one(src, dst, options)
        record_event(
            stats_project_dir or project_dir,
            step="upscale",
            target_id=target_id,
            target_kind="page_asset",
            operation="upscale_image",
            provider="replicate",
            model=REPLICATE_MODEL,
            timer=stop_timer(started_at, started),
            artifact=dst,
            extra={
                "mode": options.mode,
                "target_megapixels": options.target_megapixels,
                "scale_factor": options.scale_factor,
                "output_format": options.output_format,
            },
        )
        reporter.emit(
            ProgressEvent(
                step="upscale",
                phase=f"{target_id}_done",
                message=f"Upscale terminé pour {target_id}.",
                current=processed,
                total=total,
                artifact=str(dst),
                extra={
                    "id": target_id,
                    "i18n_key": "progressEvents.upscale.done",
                },
            )
        )

    upscaled_sequence = [dst for _, _, dst in targets if dst.exists()]
    if upscaled_sequence:
        pdf_path = project_dir / f"{project_dir.name}.pdf"
        reporter.emit(
            ProgressEvent(
                step="upscale",
                phase="assembling_pdf",
                message=f"Assemblage de {len(upscaled_sequence)} images upscalées en PDF…",
                current=total,
                total=total,
                extra={
                    "count": len(upscaled_sequence),
                    "i18n_key": "progressEvents.upscale.assemblingPdf",
                },
            )
        )
        _assemble_pdf(upscaled_sequence, pdf_path)
        reporter.emit(
            ProgressEvent(
                step="upscale",
                phase="pdf_done",
                message="PDF assemblé à partir des images upscalées.",
                current=total,
                total=total,
                artifact=str(pdf_path),
                extra={"i18n_key": "progressEvents.upscale.pdfDone"},
            )
        )

    reporter.emit(
        ProgressEvent(
            step="upscale",
            phase="done",
            message="Upscale terminé.",
            current=total,
            total=total,
            artifact=str(output_dir),
            extra={"i18n_key": "progressEvents.upscale.allDone"},
        )
    )
    return output_dir


def _upscale_one(src: Path, dst: Path, options: UpscaleOptions) -> None:
    import replicate

    image_b64 = _encode_b64(src)

    input_params: dict = {
        "image": image_b64,
        "output_format": options.output_format,
        "output_quality": options.output_quality,
    }
    if options.mode == "target":
        input_params["upscale_mode"] = "target"
        input_params["target"] = options.target_megapixels
    else:
        input_params["upscale_mode"] = "scale"
        input_params["scale"] = options.scale_factor

    output = replicate.run(REPLICATE_MODEL, input=input_params)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(output.read())


def _encode_b64(path: Path) -> str:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    suffix = path.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(suffix, "image/png")
    return f"data:{mime};base64,{encoded}"


def _assemble_pdf(page_images: list[Path], output_path: Path) -> None:
    if not page_images:
        return
    assemble_pdf(page_images, output_path)


def _ensure_replicate() -> None:
    if not secret_store.get_secret("REPLICATE_API_TOKEN"):
        raise RuntimeError(
            "REPLICATE_API_TOKEN non défini. "
            "Ajoutez votre clé API Replicate dans le fichier .env."
        )
    secret_store.ensure_replicate_env()
    try:
        import replicate  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Le package `replicate` est requis pour l'upscale. "
            "Installez-le avec : pip install replicate"
        ) from exc
