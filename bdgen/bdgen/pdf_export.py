"""Lossless assembly of page images into a single PDF.

Pillow's PDF writer re-encodes ``L``/``RGB``/``CMYK`` pages as JPEG (default
quality 75), which visibly degrades the generated and upscaled artwork. We use
``img2pdf`` instead: it embeds the original PNG/JPEG bytes verbatim, so the PDF
keeps the exact quality of the source images.
"""
from __future__ import annotations

import io
from pathlib import Path

import img2pdf
from PIL import Image


def assemble_pdf(page_images: list[Path], output_path: Path) -> None:
    """Embed page images into a single PDF without recompression.

    img2pdf copies the source image data verbatim, preserving full quality.
    Images carrying an alpha channel are flattened onto white and re-encoded
    losslessly as PNG first, because img2pdf refuses transparency.
    """
    if not page_images:
        raise RuntimeError("No pages to assemble.")

    payloads = [_embeddable_bytes(path) for path in page_images]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(img2pdf.convert(payloads))


def _embeddable_bytes(path: Path) -> bytes:
    """Return image bytes ready for embedding, flattening transparency if any."""
    with Image.open(path) as img:
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (
            img.mode == "P" and "transparency" in img.info
        )
        if not has_alpha:
            # No re-encoding: embed the original file bytes as-is (lossless).
            return path.read_bytes()

        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")  # PNG is lossless
        return buffer.getvalue()
