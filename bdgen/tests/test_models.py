from __future__ import annotations

import json
from pathlib import Path

from bdgen.models import (
    BdGenInput,
    BdGenScript,
    CharacterInput,
    GenerationOptions,
    ImageModelConfig,
    Metadata,
    ScriptModelConfig,
    Story,
    Structure,
    Style,
)

from tests.factories import make_minimal_script, make_options


def _input(output_root: Path, *, project: str | None = "demo") -> BdGenInput:
    return BdGenInput(
        project=project,
        output_root=output_root,
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        story=Story(synopsis="Une histoire.", genre="test", tone="leger", setting="ici"),
        style=Style(art_style="ligne claire"),
        characters=[
            CharacterInput(id="hero", name="Hero", physical_description="Hero desc"),
        ],
        structure=Structure(page_count=1),
        generation_options=GenerationOptions(
            script_model=ScriptModelConfig(provider="test", model="test"),
            image_model=ImageModelConfig(provider="openai", model="gpt-image-2"),
        ),
    )


def test_bdgen_input_load_falls_back_to_config_stem_for_project(tmp_path: Path) -> None:
    config_path = tmp_path / "my_project.json"
    payload = _input(tmp_path, project=None).model_dump(mode="json")
    payload["project"] = None
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = BdGenInput.load(config_path)

    assert loaded.project == "my_project"


def test_bdgen_input_load_pins_paths_to_project_dir_when_filename_is_bdgen_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config_path = project_dir / "bdgen.json"
    payload = _input(tmp_path, project="demo").to_portable_dict(config_path)
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = BdGenInput.load(config_path)

    assert loaded.output_root == tmp_path.resolve()
    assert loaded.generation_options.script_path == project_dir.resolve() / "bdgen-script.json"
    assert loaded.generation_options.output_path == project_dir.resolve() / "demo.pdf"
    assert loaded.generation_options.references.output_dir == project_dir.resolve() / "references"
    assert loaded.generation_options.upscale.output_dir == project_dir.resolve() / "pages_upscaled"


def test_bdgen_input_to_portable_dict_without_path_returns_raw_payload(tmp_path: Path) -> None:
    cfg = _input(tmp_path)

    payload = cfg.to_portable_dict(None)

    # No path normalization applied: output_root keeps its absolute form.
    assert payload["output_root"] == str(tmp_path) or payload["output_root"] == tmp_path.as_posix()


def test_bdgen_input_fill_default_paths_is_noop_when_project_is_none(tmp_path: Path) -> None:
    cfg = _input(tmp_path, project=None)
    original_script_path = cfg.generation_options.script_path

    cfg._fill_default_paths(tmp_path / "anything.json")

    assert cfg.generation_options.script_path == original_script_path


def test_bdgen_script_save_load_round_trip_preserves_paths(tmp_path: Path) -> None:
    script_path = tmp_path / "demo" / "bdgen-script.json"
    make_minimal_script(tmp_path / "demo").save(script_path)

    loaded = BdGenScript.load(script_path)

    project_dir = (tmp_path / "demo").resolve()
    assert loaded.generation_options.script_path == project_dir / "bdgen-script.json"
    assert loaded.generation_options.references.output_dir == project_dir / "references"
    assert loaded.generation_options.upscale.output_dir == project_dir / "pages_upscaled"


def test_bdgen_script_to_portable_dict_without_path_returns_raw_payload(tmp_path: Path) -> None:
    script = make_minimal_script(tmp_path / "demo")

    payload = script.to_portable_dict(None)

    # No path normalisation: paths remain absolute as stored.
    assert "generation_options" in payload
    assert payload["project"] == "demo"


def test_bdgen_script_enforce_path_consistency_skips_when_generation_options_missing(tmp_path: Path) -> None:
    # Build a portable script payload then strip generation_options before save.
    script = make_minimal_script(tmp_path / "demo")
    payload = script.to_portable_dict(tmp_path / "demo" / "bdgen-script.json")
    payload["generation_options"] = None
    script_path = tmp_path / "demo" / "bdgen-script.json"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = BdGenScript.load(script_path)

    assert loaded.generation_options is None


def test_bdgen_script_getters_return_entity_or_none(tmp_path: Path) -> None:
    script = make_minimal_script(tmp_path / "demo")

    assert script.character_by_id("hero").name == "Hero"
    assert script.location_by_id("home").name == "Home"
    assert script.object_by_id("book").name == "Book"
    assert script.character_by_id("missing") is None
    assert script.location_by_id("missing") is None
    assert script.object_by_id("missing") is None


def test_bdgen_script_project_dir_uses_explicit_script_path_first(tmp_path: Path) -> None:
    script = make_minimal_script(tmp_path / "demo")

    assert script.project_dir() == tmp_path / "demo"


def test_bdgen_script_project_dir_falls_back_to_output_project_when_no_script_path() -> None:
    script = make_minimal_script(Path("ignored"))
    script.generation_options.script_path = None

    assert script.project_dir() == Path("./output") / "demo"


def test_bdgen_script_project_dir_uses_fallback_when_no_project_or_script_path() -> None:
    script = make_minimal_script(Path("ignored"))
    script.generation_options.script_path = None
    script.project = None

    fallback = Path("/some/where/bdgen-script.json")
    assert script.project_dir(fallback) == fallback.parent


def test_bdgen_script_relative_reference_image_resolves_against_project_dir(tmp_path: Path) -> None:
    script = make_minimal_script(tmp_path / "demo")
    # Persist with a relative reference_image that should resolve on load.
    script.characters[0].reference_image = Path("references/characters/hero.png")
    script_path = tmp_path / "demo" / "bdgen-script.json"
    script.save(script_path)

    loaded = BdGenScript.load(script_path)

    assert loaded.characters[0].reference_image == (tmp_path / "demo").resolve() / "references" / "characters" / "hero.png"


def test_make_options_paths_are_pinned_to_root(tmp_path: Path) -> None:
    opts = make_options(tmp_path, image_provider="openai", image_model="gpt-image-1")

    assert opts.image_model.model == "gpt-image-1"
    assert opts.references.output_dir == tmp_path / "references"
    assert opts.upscale.output_dir == tmp_path / "pages_upscaled"
    assert opts.script_path == tmp_path / "bdgen-script.json"
