from __future__ import annotations

from bdgen.models import BackCover, Cover, Page
from bdgen.script import (
    _DraftCharacter,
    _LLMSetupDraft,
    _anthropic_max_tokens,
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


def test_estimate_input_tokens_adds_safety_margin() -> None:
    assert _estimate_anthropic_input_tokens("abcd", "abcd") == 1002


def test_anthropic_max_tokens_matches_expected_payload_size() -> None:
    assert _anthropic_max_tokens(_LLMSetupDraft) == 16000
    assert _anthropic_max_tokens(Page) == 8000
    assert _anthropic_max_tokens(_DraftCharacter) == 5000
    assert _anthropic_max_tokens(Cover) == 3000
    assert _anthropic_max_tokens(BackCover) == 3000


def test_detects_rate_limit_and_retry_after_header() -> None:
    exc = FakeApiError(429, {"retry-after": "12.5"})

    assert _is_anthropic_rate_limit(exc) is True
    assert _retry_after_seconds(exc) == 12.5


def test_missing_retry_after_returns_none() -> None:
    exc = FakeApiError(429)

    assert _retry_after_seconds(exc) is None
