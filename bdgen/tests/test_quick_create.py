from __future__ import annotations

import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from bdgen import quick_create, secret_store
from bdgen.models import ScriptModelConfig
from bdgen.quick_create import (
    _CharacterDraft,
    _ConfigDraft,
    _LocationDraft,
    _ObjectDraft,
    _StoryDraft,
    _StructureDraft,
    _StyleDraft,
)
from bdgen.server import app as app_module

_PROVIDER_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"]


def _clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_store.lock_vault()
    for key in _PROVIDER_KEYS:
        monkeypatch.delenv(key, raising=False)


def _make_draft(**overrides) -> _ConfigDraft:
    base = dict(
        title="L'Aube des circuits",
        author="",
        story=_StoryDraft(synopsis="Deux amis bâtissent une machine pensante."),
        style=_StyleDraft(art_style="ligne claire, aplats, no photorealism"),
        characters=[
            _CharacterDraft(name="L'inventeur barbu", physical_description="grand, barbe"),
            _CharacterDraft(name="L'inventeur barbu", physical_description="autre"),
        ],
        locations=[_LocationDraft(name="Le garage", description="encombré")],
        objects=[_ObjectDraft(name="Le prototype", description="boîte de circuits")],
        structure=_StructureDraft(),
    )
    base.update(overrides)
    return _ConfigDraft(**base)


# --- Mapping ----------------------------------------------------------------


def test_draft_to_config_maps_sections_and_unique_ids() -> None:
    cfg = quick_create._draft_to_config(_make_draft())

    assert cfg["metadata"]["title"] == "L'Aube des circuits"
    assert cfg["story"]["synopsis"].startswith("Deux amis")
    assert cfg["style"]["art_style"].startswith("ligne claire")

    # Two characters share a name → slugified ids must be unique.
    ids = [c["id"] for c in cfg["characters"]]
    assert len(ids) == len(set(ids))
    assert all(ids), "ids must be non-empty slugs"

    assert cfg["locations"][0]["id"]
    assert cfg["objects"][0]["id"]

    # Only the sections the form edits are returned.
    assert set(cfg) == {
        "metadata",
        "story",
        "style",
        "structure",
        "characters",
        "locations",
        "objects",
    }
    assert "generation_options" not in cfg


def test_draft_to_config_sanitizes_real_names() -> None:
    draft = _make_draft(
        characters=[_CharacterDraft(name="Tintin", physical_description="jeune reporter")],
    )
    cfg = quick_create._draft_to_config(draft)

    assert "tintin" not in cfg["characters"][0]["name"].lower()


def test_draft_to_config_falls_back_to_portrait_for_bad_format() -> None:
    draft = _make_draft(structure=_StructureDraft(page_format="hexagonal"))
    cfg = quick_create._draft_to_config(draft)

    assert cfg["structure"]["page_format"] == "portrait"


def test_draft_to_config_clamps_structure() -> None:
    draft = _make_draft(structure=_StructureDraft(page_count=500, panels_per_page_avg=99))
    cfg = quick_create._draft_to_config(draft)
    assert cfg["structure"]["page_count"] == 60
    assert cfg["structure"]["panels_per_page_avg"] == 12


def test_generate_config_passes_art_style_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _make_draft()
    captured: dict[str, str] = {}

    def fake_call_llm(system, user, model_config, output_type, trace_name="call_llm"):
        captured["user"] = user
        return types.SimpleNamespace(value=draft)

    monkeypatch.setattr(quick_create, "_call_llm", fake_call_llm)

    quick_create.generate_config(
        "une histoire de SF", "fr", ScriptModelConfig(model="x"), art_style="Manga shōnen"
    )
    assert "Manga shōnen" in captured["user"]


def test_generate_config_rejects_empty_prompt() -> None:
    with pytest.raises(ValueError):
        quick_create.generate_config("   ", "fr", ScriptModelConfig(model="x"))


def test_generate_config_uses_call_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _make_draft()

    def fake_call_llm(system, user, model_config, output_type, trace_name="call_llm"):
        assert output_type is _ConfigDraft
        return types.SimpleNamespace(value=draft)

    monkeypatch.setattr(quick_create, "_call_llm", fake_call_llm)

    cfg = quick_create.generate_config("une histoire de SF", "fr", ScriptModelConfig(model="x"))
    assert cfg["metadata"]["title"] == "L'Aube des circuits"


def test_generate_config_accepts_documents_without_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _make_draft()
    captured: dict[str, str] = {}

    def fake_call_llm(system, user, model_config, output_type, trace_name="call_llm"):
        captured["user"] = user
        return types.SimpleNamespace(value=draft)

    monkeypatch.setattr(quick_create, "_call_llm", fake_call_llm)

    cfg = quick_create.generate_config(
        "", "fr", ScriptModelConfig(model="x"), documents_text="La photosynthèse convertit la lumière."
    )
    assert cfg["metadata"]["title"] == "L'Aube des circuits"
    # The document text must reach the prompt sent to the LLM.
    assert "photosynthèse" in captured["user"]


def test_generate_config_rejects_empty_prompt_and_docs() -> None:
    with pytest.raises(ValueError):
        quick_create.generate_config("   ", "fr", ScriptModelConfig(model="x"), documents_text="  ")


def test_partial_draft_missing_style_still_maps() -> None:
    # Regression: the LLM sometimes omits whole sections (e.g. ``style``).
    # With defaults in place the draft must still validate and map cleanly.
    draft = _ConfigDraft(title="Sir Tituban")
    cfg = quick_create._draft_to_config(draft)
    assert cfg["metadata"]["title"] == "Sir Tituban"
    assert cfg["style"]["art_style"] == ""
    assert cfg["structure"]["page_format"] == "portrait"


# --- Model selection --------------------------------------------------------


def test_pick_text_model_prefers_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENAI_API_KEY", "o")

    chosen = app_module._pick_text_model()
    assert chosen.provider == "anthropic"
    assert chosen.model == "claude-sonnet-4-6"
    assert chosen.effort == "medium"


def test_pick_text_model_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "o")

    chosen = app_module._pick_text_model()
    assert chosen.provider == "openai"
    assert chosen.model == "gpt-5.4"
    assert chosen.effort is None


def test_pick_text_model_falls_back_to_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("XAI_API_KEY", "x")

    chosen = app_module._pick_text_model()
    assert chosen.provider == "xai"
    assert chosen.model == "grok-4.3"


def test_pick_text_model_raises_400_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_provider_keys(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        app_module._pick_text_model()
    assert exc.value.status_code == 400


# --- Endpoint ---------------------------------------------------------------


def test_quick_create_endpoint_400_without_keys(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_provider_keys(monkeypatch)
    resp = client.post("/api/quick-create", data={"prompt": "une histoire de SF"})
    assert resp.status_code == 400


def test_quick_create_endpoint_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    draft = _make_draft()
    monkeypatch.setattr(
        quick_create,
        "_call_llm",
        lambda *a, **k: types.SimpleNamespace(value=draft),
    )

    resp = client.post("/api/quick-create", data={"prompt": "une histoire de SF"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["title"] == "L'Aube des circuits"
    assert len(body["characters"]) == 2


def test_quick_create_endpoint_with_document(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    draft = _make_draft()
    captured: dict[str, str] = {}

    def fake_call_llm(system, user, *a, **k):
        captured["user"] = user
        return types.SimpleNamespace(value=draft)

    monkeypatch.setattr(quick_create, "_call_llm", fake_call_llm)

    resp = client.post(
        "/api/quick-create",
        data={"prompt": ""},  # no idea: drive entirely from the document
        files=[("files", ("cours_bio.txt", b"La mitose comprend cinq phases.", "text/plain"))],
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["title"] == "L'Aube des circuits"
    assert "mitose" in captured["user"]
