from __future__ import annotations

from bdgen.image_rules import IMAGE_CONSTRAINTS


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
