from __future__ import annotations

import json
from pathlib import Path

import pytest

from bdgen.stats import (
    STATS_NAME,
    TimedCall,
    aggregate_events,
    estimate_cost_usd,
    load_stats,
    normalise_usage,
    record_event,
    start_timer,
    stop_timer,
    word_count,
)


def test_start_and_stop_timer_returns_non_negative_elapsed() -> None:
    started_at, monotonic = start_timer()
    timer = stop_timer(started_at, monotonic)

    assert isinstance(timer, TimedCall)
    assert timer.started_at == started_at
    assert timer.elapsed_seconds >= 0


def test_word_count_counts_unicode_words() -> None:
    assert word_count("hello world") == 2
    assert word_count("") == 0
    assert word_count("c'est-à-dire ok") == 2
    assert word_count("   ") == 0


@pytest.mark.parametrize(
    "usage,expected",
    [
        (None, {}),
        ({}, {}),
        ({"prompt_tokens": 10, "completion_tokens": 5}, {"input_tokens": 10, "output_tokens": 5}),
        ({"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}, {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}),
    ],
)
def test_normalise_usage_maps_known_keys(usage: dict | None, expected: dict[str, int]) -> None:
    assert normalise_usage(usage) == expected


def test_normalise_usage_extracts_nested_cached_tokens() -> None:
    usage = {
        "input_tokens": 100,
        "input_tokens_details": {"cached_tokens": 30, "image_tokens": 12},
    }

    result = normalise_usage(usage)

    assert result["cached_input_tokens"] == 30
    assert result["image_input_tokens"] == 12


def test_normalise_usage_supports_pydantic_like_model_dump() -> None:
    class FakeUsage:
        def model_dump(self) -> dict:
            return {"input_tokens": 4, "output_tokens": 2}

    assert normalise_usage(FakeUsage()) == {"input_tokens": 4, "output_tokens": 2}


def test_estimate_cost_usd_returns_none_when_no_usage() -> None:
    assert estimate_cost_usd("openai", "gpt-5", {}) is None


def test_estimate_cost_usd_returns_none_for_unknown_provider() -> None:
    assert estimate_cost_usd("unknown", "model-x", {"input_tokens": 1000}) is None


def test_estimate_cost_usd_for_openai_input_only() -> None:
    # gpt-5: input rate is 1.25 / 1M tokens.
    cost = estimate_cost_usd("openai", "gpt-5", {"input_tokens": 1_000_000})

    assert cost == pytest.approx(1.25, abs=1e-6)


def test_estimate_cost_usd_for_anthropic_includes_cache_creation() -> None:
    cost = estimate_cost_usd(
        "anthropic",
        "claude-sonnet",
        {
            "input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
            "cached_input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
        },
    )

    # Subtraction logic excludes cached and cache-creation tokens from the
    # base input bucket: pure input -> 0 (1M - 1M cached - 1M cache_creation, clamped at 0).
    # Cost = 0*input + 1M*0.3 (cached) + 1M*3.75 (cache_creation) + 1M*15 (output)
    assert cost == pytest.approx(0.3 + 3.75 + 15.0, abs=1e-6)


def test_load_stats_returns_default_when_missing(tmp_path: Path) -> None:
    data = load_stats(tmp_path)

    assert data == {"version": 1, "updated_at": None, "events": []}


def test_load_stats_recovers_from_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / STATS_NAME).write_text("{not valid", encoding="utf-8")

    data = load_stats(tmp_path)

    assert data == {"version": 1, "updated_at": None, "events": []}


def test_load_stats_recovers_when_json_root_is_not_an_object(tmp_path: Path) -> None:
    (tmp_path / STATS_NAME).write_text("[]", encoding="utf-8")

    data = load_stats(tmp_path)

    assert data == {"version": 1, "updated_at": None, "events": []}


def test_record_event_is_noop_when_project_dir_is_none(tmp_path: Path) -> None:
    started_at, monotonic = start_timer()
    record_event(
        None,
        step="script",
        target_id="t",
        target_kind="script",
        operation="generate",
        provider="openai",
        model="gpt-5",
        timer=stop_timer(started_at, monotonic),
    )

    # Sanity: nothing got written anywhere we can observe.
    assert list(tmp_path.iterdir()) == []


def test_record_event_appends_to_stats_file(tmp_path: Path) -> None:
    started_at, monotonic = start_timer()
    timer = stop_timer(started_at, monotonic)

    record_event(
        tmp_path,
        step="references",
        target_id="hero",
        target_kind="character",
        operation="generate",
        provider="openai",
        model="gpt-image-2",
        timer=timer,
        usage={"input_tokens": 1000},
        prompt="hero portrait",
        input_images=2,
        artifact=tmp_path / "hero.png",
    )

    payload = json.loads((tmp_path / STATS_NAME).read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    assert event["step"] == "references"
    assert event["target_id"] == "hero"
    assert event["provider"] == "openai"
    assert event["model"] == "gpt-image-2"
    assert event["prompt_chars"] == len("hero portrait")
    assert event["prompt_words"] == 2
    assert event["input_images"] == 2
    assert event["artifact"].endswith("hero.png")
    assert event["cost_is_estimate"] is True
    assert event["usage"] == {"input_tokens": 1000}


def test_record_event_appends_multiple_events(tmp_path: Path) -> None:
    timer = stop_timer(*start_timer())
    for i in range(3):
        record_event(
            tmp_path,
            step="script",
            target_id=f"page_{i}",
            target_kind="page",
            operation="generate",
            provider="anthropic",
            model="claude-sonnet",
            timer=timer,
        )

    payload = json.loads((tmp_path / STATS_NAME).read_text(encoding="utf-8"))
    assert len(payload["events"]) == 3
    assert {e["target_id"] for e in payload["events"]} == {"page_0", "page_1", "page_2"}


def test_aggregate_events_returns_zeros_for_empty_input() -> None:
    summary = aggregate_events([])

    assert summary["event_count"] == 0
    assert summary["total_seconds"] == 0
    assert summary["total_cost_usd"] is None
    assert summary["by_step"] == {}
    assert summary["by_model"] == {}


def test_aggregate_events_buckets_by_step_and_model() -> None:
    events = [
        {
            "step": "script",
            "provider": "openai",
            "model": "gpt-5",
            "elapsed_seconds": 1.5,
            "cost_usd": 0.01,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
        {
            "step": "references",
            "provider": "openai",
            "model": "gpt-image-2",
            "elapsed_seconds": 4.0,
            "cost_usd": 0.05,
            "usage": {"input_tokens": 200, "image_output_tokens": 1000},
        },
        {
            "step": "references",
            "provider": "openai",
            "model": "gpt-image-2",
            "elapsed_seconds": 2.0,
            "cost_usd": None,
            "usage": {},
        },
    ]

    summary = aggregate_events(events)

    assert summary["event_count"] == 3
    assert summary["total_seconds"] == pytest.approx(7.5)
    assert summary["total_cost_usd"] == pytest.approx(0.06)
    assert summary["by_step"]["references"]["events"] == 2
    assert summary["by_step"]["references"]["seconds"] == pytest.approx(6.0)
    assert summary["by_step"]["references"]["known_cost_events"] == 1
    assert summary["by_step"]["references"]["input_tokens"] == 200
    assert summary["by_step"]["references"]["image_output_tokens"] == 1000
    assert summary["by_model"]["openai/gpt-5"]["events"] == 1
    assert summary["by_model"]["openai/gpt-image-2"]["events"] == 2
