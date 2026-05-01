"""xAI Imagine image helpers.

xAI's generation endpoint is OpenAI-compatible, but its edit endpoint expects
JSON data URLs instead of the multipart payload used by OpenAI images.edit().
Keeping that adapter here lets the OpenAI path stay untouched.
"""
from __future__ import annotations

import base64
import json
import math
import urllib.error
import urllib.request

from . import secret_store

XAI_IMAGES_BASE_URL = "https://api.x.ai/v1"


def generate_image(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
) -> tuple[bytes, dict]:
    payload = _base_payload(model, prompt, size, quality)
    return _post_image("/images/generations", payload)


def edit_image(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    inputs: list[tuple[str, bytes, str]],
) -> tuple[bytes, dict]:
    payload = _base_payload(model, prompt, size, quality)
    payload["images"] = [
        {
            "type": "image_url",
            "url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
        }
        for _name, data, mime in inputs
    ]
    return _post_image("/images/edits", payload)


def _base_payload(model: str, prompt: str, size: str, quality: str) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
        "aspect_ratio": _aspect_ratio(size),
        "resolution": "2k" if quality == "high" else "1k",
    }


def _aspect_ratio(size: str) -> str:
    try:
        width_s, height_s = size.lower().split("x", 1)
        width = int(width_s)
        height = int(height_s)
    except Exception:
        return "1:1"
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _post_image(path: str, payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{XAI_IMAGES_BASE_URL}{path}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {secret_store.require_secret('XAI_API_KEY')}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"xAI image API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI image API request failed: {exc.reason}") from exc

    try:
        image_b64 = data["data"][0]["b64_json"]
    except Exception as exc:
        raise RuntimeError(f"xAI image API returned no base64 image: {data}") from exc
    return base64.b64decode(image_b64), data.get("usage") or {}
