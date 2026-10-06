"""Prompt-contract tests for the implicit-scenery coherence rules.

The "cave problem": a story set among cavemen has a cave in the scenery, but
the cave is never registered as a location — so it has no reference image and
the image model redraws it with a different shape on every page. The fix
operates at three levels: the setup prompt must register recurring scenery as
locations, the page prompt must forbid scene descriptions from introducing
unregistered structures, and the coherence check must flag offenders in
existing scripts.
"""

from __future__ import annotations

from bdgen.script import PAGE_SYSTEM_PROMPT, SETUP_SYSTEM_PROMPT


def test_setup_prompt_requires_scenery_completeness() -> None:
    assert "SCENERY COMPLETENESS" in SETUP_SYSTEM_PROMPT, (
        "The setup prompt must require every recurring scenery structure to be "
        "registered as a location so it gets a reference image."
    )
    # The rule must explain WHY — unregistered scenery drifts between pages —
    # so the LLM understands the stakes rather than treating it as style noise.
    normalized = " ".join(SETUP_SYSTEM_PROMPT.split())
    assert "redrawn with a different shape on every page" in normalized


def test_page_prompt_forbids_unregistered_landmarks() -> None:
    assert "BACKGROUNDS COME FROM REGISTERED LOCATIONS" in PAGE_SYSTEM_PROMPT, (
        "The page prompt must forbid scene_description from introducing "
        "prominent structures that exist in no setup location."
    )
    normalized = " ".join(PAGE_SYSTEM_PROMPT.split())
    # When a landmark belongs to a setup location, panels must reuse the
    # location's own wording so the landmark stays visually stable.
    assert "reuse that location's own description wording" in normalized


def test_coherence_check_prompt_flags_unregistered_scenery() -> None:
    import inspect

    from bdgen.service import coherence

    source = inspect.getsource(coherence.check_script_coherence)
    assert "ÉLÉMENTS DE DÉCOR RÉCURRENTS" in source, (
        "check_script_coherence must ask the LLM to flag recurring scenery "
        "absent from 'locations'."
    )
    assert "'size'" in source, (
        "check_script_coherence must ask the LLM to flag scene descriptions "
        "that contradict an entity's size field."
    )
