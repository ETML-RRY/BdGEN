from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

import bdgen.script as script_module
from bdgen.models import BackCover, Cover, Page
from bdgen.script import (
    _DraftCharacter,
    _LLMSetupDraft,
    _call_anthropic,
    _anthropic_effort,
    _anthropic_max_tokens,
    _anthropic_supports_adaptive_thinking,
    _anthropic_timeout_seconds,
    _estimate_anthropic_input_tokens,
    _is_anthropic_rate_limit,
    _retry_after_seconds,
)


class FakeResponse:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class FakeApiError(Exception):
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        super().__init__("api error")
        self.status_code = status_code
        self.response = FakeResponse(headers or {})


class TinyPayload(BaseModel):
    ok: bool


def test_estimate_input_tokens_adds_safety_margin() -> None:
    assert _estimate_anthropic_input_tokens("abcd", "abcd") == 1002


def test_anthropic_max_tokens_matches_expected_payload_size() -> None:
    assert _anthropic_max_tokens(_LLMSetupDraft) == 16000
    assert _anthropic_max_tokens(Page) == 8000
    assert _anthropic_max_tokens(_DraftCharacter) == 5000
    assert _anthropic_max_tokens(Cover) == 3000
    assert _anthropic_max_tokens(BackCover) == 3000


def test_anthropic_timeout_defaults_to_long_script_window(monkeypatch) -> None:
    monkeypatch.delenv("BDGEN_ANTHROPIC_TIMEOUT_SECONDS", raising=False)

    assert _anthropic_timeout_seconds() == 1800.0


def test_anthropic_timeout_env_has_minimum(monkeypatch) -> None:
    monkeypatch.setenv("BDGEN_ANTHROPIC_TIMEOUT_SECONDS", "5")

    assert _anthropic_timeout_seconds() == 60.0


def test_anthropic_effort_defaults_to_medium_and_validates_env(monkeypatch) -> None:
    monkeypatch.delenv("BDGEN_ANTHROPIC_EFFORT", raising=False)
    assert _anthropic_effort() == "medium"
    assert _anthropic_effort("high") == "high"

    monkeypatch.setenv("BDGEN_ANTHROPIC_EFFORT", "low")
    assert _anthropic_effort() == "low"
    assert _anthropic_effort("wild") == "medium"

    monkeypatch.setenv("BDGEN_ANTHROPIC_EFFORT", "wild")
    assert _anthropic_effort() == "medium"


def test_adaptive_thinking_only_for_supported_models() -> None:
    assert _anthropic_supports_adaptive_thinking("claude-sonnet-4-6")
    assert _anthropic_supports_adaptive_thinking("claude-opus-4-7")
    assert not _anthropic_supports_adaptive_thinking("claude-sonnet-4-5")
    assert not _anthropic_supports_adaptive_thinking("claude-3-7-sonnet")


def test_anthropic_call_uses_configurable_timeout_and_effort(monkeypatch) -> None:
    captured = {}

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def __iter__(self):
            yield SimpleNamespace(
                type="content_block_start",
                content_block=SimpleNamespace(type="text"),
            )
            yield SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text='{"ok": true}'),
            )
            yield SimpleNamespace(type="message_stop")

        def get_final_message(self):
            usage = SimpleNamespace(
                input_tokens=1,
                output_tokens=2,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            return SimpleNamespace(usage=usage)

    class FakeMessages:
        def stream(self, **kwargs):
            captured["kwargs"] = kwargs
            return FakeStream()

    class FakeClient:
        messages = FakeMessages()

        def with_options(self, **kwargs):
            captured["options"] = kwargs
            return self

    monkeypatch.setenv("BDGEN_ANTHROPIC_TIMEOUT_SECONDS", "1200")
    monkeypatch.setenv("BDGEN_ANTHROPIC_EFFORT", "low")
    monkeypatch.setattr(script_module.secret_store, "anthropic_client", lambda: FakeClient())
    monkeypatch.setattr(script_module, "_wait_for_anthropic_input_budget", lambda _system, _user: None)

    payload, usage = _call_anthropic(
        "system",
        "user",
        SimpleNamespace(provider="anthropic", model="claude-sonnet-4-6", effort="max"),
        TinyPayload,
    )

    assert payload == TinyPayload(ok=True)
    assert usage["output_tokens"] == 2
    assert captured["options"] == {"timeout": 1200.0}
    assert captured["kwargs"]["thinking"] == {"type": "adaptive"}
    assert captured["kwargs"]["output_config"] == {"effort": "max"}


def test_detects_rate_limit_and_retry_after_header() -> None:
    exc = FakeApiError(429, {"retry-after": "12.5"})

    assert _is_anthropic_rate_limit(exc) is True
    assert _retry_after_seconds(exc) == 12.5


def test_missing_retry_after_returns_none() -> None:
    exc = FakeApiError(429)

    assert _retry_after_seconds(exc) is None
