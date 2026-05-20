from __future__ import annotations

from pathlib import Path

from bdgen.models import ImageModelConfig
from bdgen.references import (
    XAI_MAX_PROMPT_CHARS,
    _build_xai_prompt,
    _generate_xai_image,
)


def test_xai_prompt_is_kept_under_provider_limit() -> None:
    prompt = "Subject: a heroic librarian.\n" + ("middle details " * 700) + "\nFINAL STYLE CONSTRAINTS: black ink only."
    result = _build_xai_prompt(["STYLE REF: keep comic style."], prompt)

    assert len(result) < XAI_MAX_PROMPT_CHARS
    assert "Subject: a heroic librarian." in result
    assert "FINAL STYLE CONSTRAINTS: black ink only." in result
    assert "Prompt abridged for Grok" in result


def test_xai_prompt_without_prefix_is_kept_under_provider_limit() -> None:
    prompt = "Subject first.\n" + ("very long body " * 800) + "\nNegative constraints last."
    result = _build_xai_prompt([], prompt)

    assert len(result) < XAI_MAX_PROMPT_CHARS
    assert result.startswith("Subject first.")
    assert result.endswith("Negative constraints last.")


def test_xai_image_inputs_use_edit_endpoint(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_request(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"data": [{"b64_json": "ZmFrZS1pbWFnZQ=="}]}

    monkeypatch.setattr("bdgen.references._xai_image_request", fake_request)
    monkeypatch.setattr("bdgen.references._write_png", lambda target, image_bytes: target.write_bytes(image_bytes))

    target = tmp_path / "reference.png"
    _generate_xai_image(
        ImageModelConfig(provider="xai", model="grok-imagine-image", quality="medium"),
        "Render the same person as a comic character.",
        target,
        [("user.png", b"png-bytes", "image/png")],
    )

    assert captured["endpoint"].endswith("/images/edits")
    assert captured["payload"]["image"]["type"] == "image_url"
    assert captured["payload"]["image"]["url"].startswith("data:image/png;base64,")
    assert "images" not in captured["payload"]
    assert target.read_bytes() == b"fake-image"
