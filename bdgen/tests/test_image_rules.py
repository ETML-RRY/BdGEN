from __future__ import annotations

from bdgen.image_rules import IMAGE_CONSTRAINTS, OPENAI_TEXT_ARTIFACT_RULES, with_openai_text_rules


def test_image_constraints_is_non_empty_string() -> None:
    assert isinstance(IMAGE_CONSTRAINTS, str)
    assert IMAGE_CONSTRAINTS.strip() != ""


def test_image_constraints_covers_key_authoring_rules() -> None:
    # The pipeline depends on the rules covering: readability, no incidental
    # text, and anatomically correct hands. Removing any of these by accident
    # would silently degrade every generated image.
    assert "READABLE" in IMAGE_CONSTRAINTS
    assert "NO INCIDENTAL TEXT" in IMAGE_CONSTRAINTS
    assert "HANDS AND ARMS" in IMAGE_CONSTRAINTS
    assert "5 fingers" in IMAGE_CONSTRAINTS


def test_openai_text_rules_appended_for_openai_only() -> None:
    prompt = "Draw a page."
    out = with_openai_text_rules(prompt, "openai")
    assert out.startswith(prompt)
    assert OPENAI_TEXT_ARTIFACT_RULES in out
    assert "no decorative lines or sparkles" in out
    assert "SOUND EFFECTS" in out
    assert with_openai_text_rules(prompt, "xai") == prompt


def test_openai_text_rules_is_idempotent() -> None:
    once = with_openai_text_rules("Draw a page.", "openai")
    assert with_openai_text_rules(once, "openai") == once
