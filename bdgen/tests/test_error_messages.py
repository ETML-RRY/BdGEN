from __future__ import annotations

from bdgen.server.error_messages import format_user_error


class _FakeAnthropicError(Exception):
    __module__ = "anthropic._exceptions"

    def __init__(self, status_code: int, body: dict, request_id: str | None = None):
        super().__init__(str(body))
        self.status_code = status_code
        self.body = body
        self.request_id = request_id


class _FakeOpenAIError(Exception):
    __module__ = "openai._exceptions"

    def __init__(self, status_code: int, body: dict):
        super().__init__(str(body))
        self.status_code = status_code
        self.body = body


def test_overloaded_anthropic_is_user_friendly() -> None:
    exc = _FakeAnthropicError(
        status_code=529,
        body={
            "type": "error",
            "error": {"details": None, "type": "overloaded_error", "message": "Overloaded"},
            "request_id": "req_011CayFxRqsoCm3nkas3YRWS",
        },
        request_id="req_011CayFxRqsoCm3nkas3YRWS",
    )

    message = format_user_error(exc)

    assert "surchargé" in message
    assert "Claude (Anthropic)" in message
    assert "req_011CayFxRqsoCm3nkas3YRWS" in message
    assert "APIStatusError" not in message


def test_rate_limit_anthropic_mentions_quota() -> None:
    exc = _FakeAnthropicError(
        status_code=429,
        body={
            "type": "error",
            "error": {"type": "rate_limit_error", "message": "Rate limit exceeded"},
        },
    )

    message = format_user_error(exc)

    assert "Quota" in message
    assert "Claude (Anthropic)" in message


def test_authentication_uses_status_when_type_missing() -> None:
    exc = _FakeOpenAIError(status_code=401, body={})

    message = format_user_error(exc)

    assert "Clé API" in message
    assert "OpenAI" in message


def test_invalid_request_includes_detail_message() -> None:
    exc = _FakeAnthropicError(
        status_code=400,
        body={
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "max_tokens too large"},
        },
    )

    message = format_user_error(exc)

    assert "Requête refusée" in message
    assert "max_tokens too large" in message


def test_unknown_error_falls_back_to_class_and_str() -> None:
    exc = RuntimeError("boom")

    message = format_user_error(exc)

    assert message == "RuntimeError: boom"


def test_detail_is_omitted_when_already_in_friendly_text() -> None:
    exc = _FakeAnthropicError(
        status_code=529,
        body={
            "type": "error",
            "error": {"type": "overloaded_error", "message": "Overloaded"},
        },
    )

    message = format_user_error(exc)

    # "Overloaded" already implied by the French message — no redundant detail.
    assert "détail" not in message


def test_formatter_never_raises_on_weird_body() -> None:
    class Weird(Exception):
        __module__ = "anthropic"

    exc = Weird("weird")
    exc.status_code = "not-an-int"  # type: ignore[attr-defined]
    exc.body = "not-a-dict"  # type: ignore[attr-defined]

    message = format_user_error(exc)

    assert message.startswith("Weird:")
