"""Config↔script sync must surface and apply entity *removals*.

When a character / location / object is deleted from the project config while a
script already exists, ``get_config_script_diff`` should report it under
``removed`` (with the cascade impact), and ``sync_script_with_config`` should be
able to cascade-delete the confirmed ones.
"""

from __future__ import annotations

from pathlib import Path

from bdgen.models import (
    BdGenInput,
    BdGenScript,
    CharacterInput,
    LocationInput,
    Metadata,
    ObjectInput,
    Story,
    Structure,
    Style,
)
from bdgen.service.coherence import get_config_script_diff, sync_script_with_config
from bdgen.service.config import save_config

from tests.factories import make_minimal_script, make_options


def _config(
    output_root: Path,
    *,
    characters: list[CharacterInput],
    locations: list[LocationInput],
    objects: list[ObjectInput],
) -> BdGenInput:
    project_root = output_root / "demo"
    return BdGenInput(
        project="demo",
        output_root=output_root,
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        story=Story(synopsis="Une histoire.", genre="test", tone="leger", setting="ici"),
        style=Style(art_style="ligne claire"),
        characters=characters,
        locations=locations,
        objects=objects,
        structure=Structure(page_count=1),
        generation_options=make_options(project_root),
    )


# The script (make_minimal_script) always contains: character "hero",
# location "home", object "book", and a single page using all three.
_HERO = CharacterInput(id="hero", name="Hero", physical_description="Hero desc")
_HOME = LocationInput(id="home", name="Home", description="Home desc")
_BOOK = ObjectInput(id="book", name="Book", description="Book desc")


def _setup(tmp_path: Path, *, characters, locations, objects) -> Path:
    output_root = tmp_path
    project_root = output_root / "demo"
    save_config(
        _config(output_root, characters=characters, locations=locations, objects=objects),
        output_root,
    )
    make_minimal_script(project_root).save(project_root / "bdgen-script.json")
    return output_root


def test_diff_reports_removed_location_with_impact(tmp_path: Path) -> None:
    # Config keeps hero + book but drops the "home" location.
    output_root = _setup(tmp_path, characters=[_HERO], locations=[], objects=[_BOOK])

    diff = get_config_script_diff("demo", output_root)

    removed_locs = diff["removed"]["locations"]
    assert [l["id"] for l in removed_locs] == ["home"]
    assert removed_locs[0]["pages_dropped"] == 1
    assert removed_locs[0]["earliest_affected"] == 1
    # Nothing spurious reported for the still-present entities.
    assert diff["removed"]["characters"] == []
    assert diff["removed"]["objects"] == []


def test_diff_reports_no_removals_when_config_matches(tmp_path: Path) -> None:
    output_root = _setup(tmp_path, characters=[_HERO], locations=[_HOME], objects=[_BOOK])

    diff = get_config_script_diff("demo", output_root)

    assert diff["removed"]["characters"] == []
    assert diff["removed"]["locations"] == []
    assert diff["removed"]["objects"] == []


def test_sync_cascade_deletes_confirmed_removal(tmp_path: Path) -> None:
    # "home" removed from config; user confirms removing it from the script too.
    output_root = _setup(tmp_path, characters=[_HERO], locations=[], objects=[_BOOK])

    # No new/modified entities → no LLM call, only the cascade removal runs.
    result = sync_script_with_config("demo", output_root, removals={"locations": ["home"]})

    assert result["applied"] is True
    assert result["pages_dropped"] == 1
    assert result["changes"]["location_removals"] == 1

    script = BdGenScript.load(output_root / "demo" / "bdgen-script.json")
    assert script.location_by_id("home") is None
    # The page that used "home" was truncated, awaiting regeneration.
    assert script.pages == []


def test_sync_ignores_unconfirmed_and_unknown_removals(tmp_path: Path) -> None:
    output_root = _setup(tmp_path, characters=[_HERO], locations=[], objects=[_BOOK])

    # User confirms nothing actionable (unknown id + an entity not in the diff).
    result = sync_script_with_config(
        "demo",
        output_root,
        removals={"locations": ["does_not_exist"], "characters": ["hero"]},
    )

    assert result["applied"] is False
    script = BdGenScript.load(output_root / "demo" / "bdgen-script.json")
    # "home" is still there because it was never confirmed.
    assert script.location_by_id("home") is not None
    assert len(script.pages) == 1
