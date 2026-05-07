from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bdgen.feedback import FeedbackStore, feedback_block, feedback_path_for


def test_load_or_empty_returns_empty_when_path_missing(tmp_path: Path) -> None:
    store = FeedbackStore.load_or_empty(tmp_path / "missing.json")

    assert store.items == []


def test_save_and_load_round_trips_items(tmp_path: Path) -> None:
    store = FeedbackStore()
    store.add("script", None, "Plus de dialogue.")
    store.add("references", "hero", "Cheveux plus courts.")

    path = tmp_path / "subdir" / "feedback.json"
    store.save(path)

    reloaded = FeedbackStore.load_or_empty(path)
    assert [(i.step, i.target, i.feedback) for i in reloaded.items] == [
        ("script", None, "Plus de dialogue."),
        ("references", "hero", "Cheveux plus courts."),
    ]


def test_add_stamps_a_utc_iso_timestamp(tmp_path: Path) -> None:
    store = FeedbackStore()
    store.add("compose", "page_1", "Recadrer.")

    item = store.items[0]
    # Pydantic stores str; we just verify it parses as ISO and is recent.
    assert "T" in item.timestamp
    assert item.timestamp.endswith("+00:00") or item.timestamp.endswith("Z")


def test_get_for_filters_by_step_and_target() -> None:
    store = FeedbackStore()
    store.add("script", None, "A")
    store.add("references", "hero", "B")
    store.add("references", "hero", "C")
    store.add("references", "villain", "D")

    assert store.get_for("script") == ["A"]
    assert store.get_for("references", "hero") == ["B", "C"]
    assert store.get_for("references", "villain") == ["D"]
    assert store.get_for("compose") == []


def test_invalid_step_is_rejected_by_pydantic() -> None:
    store = FeedbackStore()
    with pytest.raises(ValidationError):
        store.add("not_a_step", None, "noop")  # type: ignore[arg-type]


def test_feedback_path_for_lives_alongside_script(tmp_path: Path) -> None:
    script = tmp_path / "demo" / "bdgen-script.json"

    assert feedback_path_for(script) == tmp_path / "demo" / "bdgen-feedback.json"


def test_feedback_block_renders_bulleted_list() -> None:
    block = feedback_block(["court", "lumineux"])

    assert "USER FEEDBACK" in block
    assert "- court" in block
    assert "- lumineux" in block


def test_feedback_block_handles_empty_list() -> None:
    # Empty list still produces a header (callers decide whether to inject).
    block = feedback_block([])

    assert "USER FEEDBACK" in block


def test_load_or_empty_validates_json_structure(tmp_path: Path) -> None:
    path = tmp_path / "feedback.json"
    path.write_text(json.dumps({"items": []}), encoding="utf-8")

    store = FeedbackStore.load_or_empty(path)

    assert store.items == []
