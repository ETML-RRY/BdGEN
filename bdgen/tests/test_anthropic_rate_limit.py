from __future__ import annotations

import unittest

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


class AnthropicRateLimitHelpersTest(unittest.TestCase):
    def test_estimate_input_tokens_adds_safety_margin(self) -> None:
        estimate = _estimate_anthropic_input_tokens("abcd", "abcd")

        self.assertEqual(estimate, 1002)

    def test_anthropic_max_tokens_matches_expected_payload_size(self) -> None:
        self.assertEqual(_anthropic_max_tokens(_LLMSetupDraft), 16000)
        self.assertEqual(_anthropic_max_tokens(Page), 8000)
        self.assertEqual(_anthropic_max_tokens(_DraftCharacter), 5000)
        self.assertEqual(_anthropic_max_tokens(Cover), 3000)
        self.assertEqual(_anthropic_max_tokens(BackCover), 3000)

    def test_detects_rate_limit_and_retry_after_header(self) -> None:
        exc = FakeApiError(429, {"retry-after": "12.5"})

        self.assertTrue(_is_anthropic_rate_limit(exc))
        self.assertEqual(_retry_after_seconds(exc), 12.5)

    def test_missing_retry_after_returns_none(self) -> None:
        exc = FakeApiError(429)

        self.assertIsNone(_retry_after_seconds(exc))


if __name__ == "__main__":
    unittest.main()
