from __future__ import annotations

from bdgen.references import (
    XAI_MAX_PROMPT_CHARS,
    _build_xai_prompt,
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
