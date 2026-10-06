"""Regression tests for the SCALE & RELATIVE PROPORTIONS block in compose prompts.

Before this fix, entity sizes reached the image prompt only as flavour text —
"Hero (1m20)" in the PANELS section and "Size anchor: ..." on input-image
labels — with no rule telling the image model those dimensions are binding.
The model freely rescaled characters to fit the composition, so a character
set to 1m20 could come out knee-high in one panel and adult-height in the
next.
"""

from __future__ import annotations

from pathlib import Path

from bdgen.compose import _build_page_prompt, _scale_block
from tests.factories import make_minimal_script


def test_scale_block_lists_sized_entities(tmp_path: Path) -> None:
    script = make_minimal_script(
        tmp_path,
        character_size="1m20, hauteur d'un enfant de 7 ans",
        location_size="petite grotte, 3m de plafond",
        object_size="livre de poche, 18cm",
    )
    block = _scale_block(script, script.pages[0])

    assert "SCALE & RELATIVE PROPORTIONS" in block
    assert "Hero: 1m20, hauteur d'un enfant de 7 ans" in block
    assert "Home: petite grotte, 3m de plafond" in block
    assert "Book: livre de poche, 18cm" in block
    # The block must state the sizes are binding, not decorative.
    assert "BINDING" in block
    assert "NEVER shrink or enlarge" in block


def test_scale_block_absent_when_no_entity_has_a_size(tmp_path: Path) -> None:
    """Older scripts without the size field must produce unchanged prompts."""
    script = make_minimal_script(tmp_path)
    assert _scale_block(script, script.pages[0]) == ""


def test_page_prompt_includes_scale_block_when_sizes_present(tmp_path: Path) -> None:
    script = make_minimal_script(
        tmp_path,
        character_size="1m20",
        location_size="3m de plafond",
        object_size="18cm",
    )
    prompt = _build_page_prompt(script, script.pages[0], ref_labels=None)

    assert "SCALE & RELATIVE PROPORTIONS" in prompt
    # The block sits before the publication specs so the model reads it as part
    # of the scene contract, not as an afterthought.
    assert prompt.index("SCALE & RELATIVE PROPORTIONS") < prompt.index("PUBLICATION SPECS")


def test_page_prompt_has_no_scale_block_without_sizes(tmp_path: Path) -> None:
    script = make_minimal_script(tmp_path)
    prompt = _build_page_prompt(script, script.pages[0], ref_labels=None)
    assert "SCALE & RELATIVE PROPORTIONS" not in prompt
