"""Regression tests for the ``size`` field propagation in script prompts.

Before this fix, ``_build_page_prompt`` and ``_regenerate_page_impl`` built the
``setup`` dict that the LLM sees during page generation WITHOUT the per-entity
``size`` field. As a result, the LLM had no way to reason about relative
proportions when several characters/objects shared a frame, and the size info
that the user had entered was effectively dropped on the floor between the
setup phase and the per-page phase.
"""

from __future__ import annotations

import json
from pathlib import Path

import bdgen.script as script_mod
from bdgen.models import (
    BdGenInput,
    CharacterInput,
    GenerationOptions,
    ImageModelConfig,
    LocationInput,
    Metadata,
    ObjectInput,
    Page as PageModel,
    Panel,
    ScriptModelConfig,
    Story,
    Structure,
    Style,
)
from bdgen.progress import NullReporter
from bdgen.script import (
    _build_page_prompt,
    _build_skeleton,
    _DraftCharacter,
    _DraftLocation,
    _DraftObject,
    _LLMSetupDraft,
    _regenerate_page_impl,
)
from tests.factories import make_minimal_script


def _input_with_sizes(root: Path) -> BdGenInput:
    return BdGenInput(
        project="demo",
        output_root=root,
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        story=Story(synopsis="Une histoire.", genre="test", tone="leger", setting="ici"),
        style=Style(art_style="ligne claire"),
        characters=[
            CharacterInput(id="hero", name="Hero", physical_description="Hero desc", size="1m85, tallest"),
        ],
        locations=[
            LocationInput(id="home", name="Home", description="Home desc", size="small studio, 20m²"),
        ],
        objects=[
            ObjectInput(id="book", name="Book", description="Book desc", size="5cm wide, pocket-sized"),
        ],
        structure=Structure(page_count=2),
        generation_options=GenerationOptions(
            script_model=ScriptModelConfig(provider="test", model="test"),
            image_model=ImageModelConfig(provider="openai", model="gpt-image-2"),
        ),
    )


def _setup_with_sizes(tmp_path: Path):
    return make_minimal_script(
        tmp_path,
        character_size="1m85, tallest in the room",
        location_size="small studio, 20m²",
        object_size="5cm wide, pocket-sized",
    )


def test_build_page_prompt_includes_size_in_setup(tmp_path: Path) -> None:
    """The setup dict the LLM sees for page generation must include size."""
    config = _input_with_sizes(tmp_path)
    bd_script = _setup_with_sizes(tmp_path)

    user_prompt = _build_page_prompt(
        config=config,
        bd_script=bd_script,
        page_n=1,
        target_pages=config.structure.page_count,
        feedback=None,
        preview_pages=None,
    )

    # The setup payload is the JSON blob right after the "SETUP" label.
    setup_marker = "SETUP (already generated"
    assert setup_marker in user_prompt
    setup_start = user_prompt.index(setup_marker)
    setup_block = user_prompt[setup_start:]
    brace = setup_block.index("{")
    setup_payload = json.loads(setup_block[brace:].split("\n\n", 1)[0])

    assert setup_payload["characters"][0]["size"] == "1m85, tallest in the room", (
        f"Character size missing from _build_page_prompt's setup. Got: {setup_payload['characters'][0]!r}"
    )
    assert setup_payload["locations"][0]["size"] == "small studio, 20m²", (
        f"Location size missing from _build_page_prompt's setup. Got: {setup_payload['locations'][0]!r}"
    )
    assert setup_payload["objects"][0]["size"] == "5cm wide, pocket-sized", (
        f"Object size missing from _build_page_prompt's setup. Got: {setup_payload['objects'][0]!r}"
    )


def test_regenerate_page_impl_includes_size_in_setup(tmp_path: Path) -> None:
    """The setup dict the LLM sees when regenerating a page must include size."""
    bd_script = _setup_with_sizes(tmp_path)
    bd_script.save(tmp_path / "bdgen-script.json")

    captured_user_prompts: list[str] = []

    def _spy_call_llm(system, user, model_config, output_type, trace_name="call_llm"):
        captured_user_prompts.append(user)
        return script_mod._LLMCallResult(
            value=PageModel(
                page_number=bd_script.pages[0].page_number,
                layout="single row",
                panels=[
                    Panel(
                        panel_number=1,
                        location="home",
                        characters=["hero"],
                        objects=["book"],
                        scene_description="regenerated scene",
                    )
                ],
            ),
            usage={},
            elapsed_seconds=0.0,
            started_at="2026-01-01T00:00:00Z",
        )

    original = script_mod._call_llm
    script_mod._call_llm = _spy_call_llm
    try:
        _regenerate_page_impl(
            bd_script=bd_script,
            page_number=1,
            feedback_text="make it more dynamic",
            rep=NullReporter(),
            idx=0,
            stats_project_dir=tmp_path,
        )
    finally:
        script_mod._call_llm = original

    assert captured_user_prompts, "_regenerate_page_impl did not call the LLM"
    user_prompt = captured_user_prompts[0]

    # The whole user_prompt is a JSON object; parse it and pull the setup dict.
    full_payload = json.loads(user_prompt)
    setup_payload = full_payload["setup"]

    assert setup_payload["characters"][0]["size"] == "1m85, tallest in the room"
    assert setup_payload["locations"][0]["size"] == "small studio, 20m²"
    assert setup_payload["objects"][0]["size"] == "5cm wide, pocket-sized"


def test_build_skeleton_preserves_size_through_setup_draft(tmp_path: Path) -> None:
    """The setup-draft → BdGenScript path must not drop the size field."""
    config = _input_with_sizes(tmp_path)
    setup = _LLMSetupDraft(
        characters=[
            _DraftCharacter(
                id="hero",
                name="Hero",
                physical_description="Hero desc",
                outfit="red cape",
                size="1m85, tallest in the room",
                reference_prompt="Hero prompt",
            )
        ],
        locations=[
            _DraftLocation(
                id="home",
                name="Home",
                description="Home desc",
                size="small studio, 20m²",
                reference_prompt="Home prompt",
            )
        ],
        objects=[
            _DraftObject(
                id="book",
                name="Book",
                description="Book desc",
                size="5cm wide, pocket-sized",
                reference_prompt="Book prompt",
            )
        ],
        cover=None,
        back_cover=None,
    )

    bd = _build_skeleton(config, setup, tmp_path / "bdgen.json", "test/test")

    assert bd.characters[0].size == "1m85, tallest in the room"
    assert bd.locations[0].size == "small studio, 20m²"
    assert bd.objects[0].size == "5cm wide, pocket-sized"


def test_build_skeleton_auto_fills_missing_size_with_localized_fallback(tmp_path: Path) -> None:
    """When the LLM returns ``size=None`` for an entity, _build_skeleton must
    substitute a localized fallback so the field is never null on disk.
    """
    config = _input_with_sizes(tmp_path)
    setup = _LLMSetupDraft(
        characters=[
            _DraftCharacter(
                id="hero",
                name="Hero",
                physical_description="Hero desc",
                outfit="red cape",
                size=None,  # LLM ignored the SIZE — MANDATORY constraint
                reference_prompt="Hero prompt",
            )
        ],
        locations=[
            _DraftLocation(
                id="home",
                name="Home",
                description="Home desc",
                size=None,
                reference_prompt="Home prompt",
            )
        ],
        objects=[
            _DraftObject(
                id="book",
                name="Book",
                description="Book desc",
                size=None,
                reference_prompt="Book prompt",
            )
        ],
        cover=None,
        back_cover=None,
    )

    bd = _build_skeleton(config, setup, tmp_path / "bdgen.json", "test/test")

    assert bd.characters[0].size, "character size should never be null after _build_skeleton"
    assert bd.locations[0].size, "location size should never be null after _build_skeleton"
    assert bd.objects[0].size, "object size should never be null after _build_skeleton"
    # The fallback is in the project's language (fr in the test config).
    assert "non précisé" in bd.characters[0].size or "standard" in bd.characters[0].size.lower()


def test_size_fallback_uses_project_language(tmp_path: Path) -> None:
    """The fallback string must follow the project's metadata.language."""
    from bdgen.script import _size_fallback_text

    assert "non précisé" in _size_fallback_text("fr", "character").lower()
    assert "not specified" in _size_fallback_text("en", "character").lower()
    assert "nicht angegeben" in _size_fallback_text("de", "character").lower()
    # Unknown language falls back to French.
    assert "non précisé" in _size_fallback_text("xx", "character").lower()
    assert "non précisé" in _size_fallback_text(None, "character").lower()


def test_regenerate_character_auto_fills_missing_size(tmp_path: Path) -> None:
    """regenerate_character must persist a non-null size even if the LLM returns null."""
    from bdgen.script import regenerate_character, _DraftCharacter
    from bdgen.progress import NullReporter

    bd_script = _setup_with_sizes(tmp_path)
    bd_script.characters[0].size = None  # LLM will return null too
    bd_script.save(tmp_path / "bdgen-script.json")

    def _spy(system, user, model_config, output_type, trace_name="call_llm"):
        return script_mod._LLMCallResult(
            value=_DraftCharacter(
                id="hero",
                name="Hero",
                physical_description="Hero desc",
                outfit=None,
                size=None,  # LLM ignored the SIZE — MANDATORY constraint
                reference_prompt="Hero prompt",
            ),
            usage={},
            elapsed_seconds=0.0,
            started_at="2026-01-01T00:00:00Z",
        )

    original = script_mod._call_llm
    script_mod._call_llm = _spy
    try:
        char = regenerate_character(
            bd_script=bd_script,
            character_id="hero",
            feedback_text="add a hat",
            reporter=NullReporter(),
            stats_project_dir=tmp_path,
        )
    finally:
        script_mod._call_llm = original

    assert char.size, "regenerate_character must not leave size null on the script character"


def test_regenerate_location_auto_fills_missing_size(tmp_path: Path) -> None:
    """regenerate_location must persist a non-null size even if the LLM returns null."""
    from bdgen.script import regenerate_location, _DraftLocation
    from bdgen.progress import NullReporter

    bd_script = _setup_with_sizes(tmp_path)
    bd_script.locations[0].size = None
    bd_script.save(tmp_path / "bdgen-script.json")

    def _spy(system, user, model_config, output_type, trace_name="call_llm"):
        return script_mod._LLMCallResult(
            value=_DraftLocation(
                id="home",
                name="Home",
                description="Home desc",
                size=None,
                reference_prompt="Home prompt",
            ),
            usage={},
            elapsed_seconds=0.0,
            started_at="2026-01-01T00:00:00Z",
        )

    original = script_mod._call_llm
    script_mod._call_llm = _spy
    try:
        loc = regenerate_location(
            bd_script=bd_script,
            location_id="home",
            feedback_text="add a window",
            reporter=NullReporter(),
            stats_project_dir=tmp_path,
        )
    finally:
        script_mod._call_llm = original

    assert loc.size, "regenerate_location must not leave size null on the script location"


def test_regenerate_object_auto_fills_missing_size(tmp_path: Path) -> None:
    """regenerate_object must persist a non-null size even if the LLM returns null."""
    from bdgen.script import regenerate_object, _DraftObject
    from bdgen.progress import NullReporter

    bd_script = _setup_with_sizes(tmp_path)
    bd_script.objects[0].size = None
    bd_script.save(tmp_path / "bdgen-script.json")

    def _spy(system, user, model_config, output_type, trace_name="call_llm"):
        return script_mod._LLMCallResult(
            value=_DraftObject(
                id="book",
                name="Book",
                description="Book desc",
                size=None,
                reference_prompt="Book prompt",
            ),
            usage={},
            elapsed_seconds=0.0,
            started_at="2026-01-01T00:00:00Z",
        )

    original = script_mod._call_llm
    script_mod._call_llm = _spy
    try:
        obj = regenerate_object(
            bd_script=bd_script,
            object_id="book",
            feedback_text="add a cover image",
            reporter=NullReporter(),
            stats_project_dir=tmp_path,
        )
    finally:
        script_mod._call_llm = original

    assert obj.size, "regenerate_object must not leave size null on the script object"


def test_setup_system_prompt_requires_size_to_be_non_null() -> None:
    """The setup system prompt must explicitly tell the LLM that size is mandatory."""
    from bdgen.script import SETUP_SYSTEM_PROMPT

    assert "MANDATORY" in SETUP_SYSTEM_PROMPT
    # The mandatory clause must appear for each of the three entity kinds.
    for kind_clause in (
        "SIZE — MANDATORY",
    ):
        assert kind_clause in SETUP_SYSTEM_PROMPT, (
            f"Setup prompt is missing the mandatory-size clause ({kind_clause!r})"
        )


def _phrase_present(prompt: str, phrase: str) -> bool:
    """Return True if ``phrase`` appears in ``prompt`` ignoring whitespace.

    The prompts are dedented to ~80 columns, so a long directive like
    "Write the inferred `size` field in the language specified by
    `metadata.language`" can wrap across two lines. We don't want false
    negatives when that happens.
    """
    normalized_prompt = " ".join(prompt.split())
    normalized_phrase = " ".join(phrase.split())
    return normalized_phrase in normalized_prompt


def test_setup_system_prompt_requires_size_in_project_language() -> None:
    """The setup SIZE clauses must instruct the LLM to write the inferred size
    in ``metadata.language`` (fr/en/de), not in English.
    """
    from bdgen.script import SETUP_SYSTEM_PROMPT

    expected_phrase = (
        "Write the inferred `size` field in the language specified by `metadata.language`"
    )
    assert _phrase_present(SETUP_SYSTEM_PROMPT, expected_phrase), (
        "Setup prompt must explicitly tell the LLM to write the inferred size "
        "in the project's metadata.language so non-English BDs get sizes in the "
        "right language."
    )
    # Each of the three entity kinds (character, location, object) must carry
    # the language directive, not just one of them. We collapse whitespace
    # because the dedent keeps per-line indentation, so a line wrap leaves
    # multiple spaces between words.
    normalized_prompt = " ".join(SETUP_SYSTEM_PROMPT.split())
    size_clause_count = SETUP_SYSTEM_PROMPT.count("SIZE — MANDATORY")
    language_phrase_count = normalized_prompt.count(
        " ".join(expected_phrase.split())
    )
    assert size_clause_count == language_phrase_count, (
        f"Every SIZE — MANDATORY clause ({size_clause_count}) must include the "
        f"language directive, but only {language_phrase_count} do."
    )


def test_refine_system_prompts_require_size_in_project_language() -> None:
    """All three refine system prompts must require the inferred size to be
    written in ``metadata.language``.
    """
    from bdgen.script import (
        CHARACTER_REFINE_SYSTEM_PROMPT,
        LOCATION_REFINE_SYSTEM_PROMPT,
        OBJECT_REFINE_SYSTEM_PROMPT,
    )

    expected_phrase = (
        "Write the inferred `size` field in the language specified by `metadata.language`"
    )
    for prompt, label in (
        (CHARACTER_REFINE_SYSTEM_PROMPT, "character"),
        (LOCATION_REFINE_SYSTEM_PROMPT, "location"),
        (OBJECT_REFINE_SYSTEM_PROMPT, "object"),
    ):
        assert _phrase_present(prompt, expected_phrase), (
            f"{label} refine prompt must instruct the LLM to write the inferred "
            f"size in the project's metadata.language."
        )


def test_user_supplied_size_is_copied_verbatim_regardless_of_language() -> None:
    """The SIZE clauses must say: when the user has supplied a non-null size,
    copy it EXACTLY — do NOT translate it. The user-supplied text wins over
    the project's metadata.language.
    """
    from bdgen.script import (
        SETUP_SYSTEM_PROMPT,
        CHARACTER_REFINE_SYSTEM_PROMPT,
        LOCATION_REFINE_SYSTEM_PROMPT,
        OBJECT_REFINE_SYSTEM_PROMPT,
    )

    for prompt, label in (
        (SETUP_SYSTEM_PROMPT, "setup"),
        (CHARACTER_REFINE_SYSTEM_PROMPT, "character refine"),
        (LOCATION_REFINE_SYSTEM_PROMPT, "location refine"),
        (OBJECT_REFINE_SYSTEM_PROMPT, "object refine"),
    ):
        assert "verbatim" in prompt, (
            f"{label} prompt must say to copy the user-supplied size verbatim."
        )
        # The user-supplied text wins over the project language — the LLM must
        # not translate it.
        assert "user" in prompt.lower() and "language" in prompt.lower(), (
            f"{label} prompt must mention both the user-supplied text and the "
            f"project's metadata.language to make the precedence explicit."
        )


def test_refine_system_prompts_require_size_to_be_non_null() -> None:
    """All three refine system prompts must require a non-null size."""
    from bdgen.script import (
        CHARACTER_REFINE_SYSTEM_PROMPT,
        LOCATION_REFINE_SYSTEM_PROMPT,
        OBJECT_REFINE_SYSTEM_PROMPT,
    )

    for prompt in (CHARACTER_REFINE_SYSTEM_PROMPT, LOCATION_REFINE_SYSTEM_PROMPT, OBJECT_REFINE_SYSTEM_PROMPT):
        assert "MANDATORY" in prompt, "Refine prompt must mark the size field as MANDATORY"
        assert '"size": "<non-null string>"' in prompt, "Refine prompt output shape must say size is non-null"


def test_refine_prompts_spell_out_the_size_line_phrasing() -> None:
    """Each refine prompt's SIZE clause must spell out the full
    ``Size: <the size text>.`` phrasing for the reference_prompt line.

    Regression: the character refine prompt's SIZE clause used to end
    mid-sentence on "phrased as:" — the phrasing itself had been dropped, so
    the LLM had no instruction for how to embed the size in the
    reference_prompt.
    """
    from bdgen.script import (
        CHARACTER_REFINE_SYSTEM_PROMPT,
        LOCATION_REFINE_SYSTEM_PROMPT,
        OBJECT_REFINE_SYSTEM_PROMPT,
    )

    for prompt, label in (
        (CHARACTER_REFINE_SYSTEM_PROMPT, "character"),
        (LOCATION_REFINE_SYSTEM_PROMPT, "location"),
        (OBJECT_REFINE_SYSTEM_PROMPT, "object"),
    ):
        assert "`Size: <the size text>.`" in prompt, (
            f"The {label} refine prompt's SIZE clause must include the literal "
            f"`Size: <the size text>.` phrasing — without it the instruction "
            f"ends mid-sentence."
        )


def test_page_system_prompt_instructs_to_use_sizes_in_panels() -> None:
    """The page-generation system prompt must tell the LLM to USE the size
    field from the SETUP to reason about relative proportions in
    scene_descriptions — otherwise the proportions don't make it from the
    setup dict into the panels and the image model still draws characters at
    the same scale.
    """
    from bdgen.script import PAGE_SYSTEM_PROMPT

    assert "USE SIZES IN PANELS" in PAGE_SYSTEM_PROMPT, (
        "PAGE_SYSTEM_PROMPT must contain a USE SIZES IN PANELS hard constraint."
    )
    # The constraint must explicitly mention proportions — that's the whole
    # point of the rule.
    assert "RELATIVE PROPORTIONS" in PAGE_SYSTEM_PROMPT, (
        "The USE SIZES IN PANELS rule must call out RELATIVE PROPORTIONS so "
        "the LLM knows what the size field is for at panel-writing time."
    )
