from __future__ import annotations

import json
from pathlib import Path

from bdgen.models import (
    BdGenInput,
    BdGenScript,
    GenerationOptions,
    ImageModelConfig,
    Metadata,
    Page,
    Panel,
    ReferencesOptions,
    ScriptCharacter,
    ScriptLocation,
    ScriptModelConfig,
    ScriptObject,
    ScriptSource,
    Structure,
    Story,
    Style,
    UpscaleOptions,
)
from bdgen.service import (
    detect_and_mark_stale,
    load_config,
    read_stale_index,
    save_config,
    _resolve_options,
)


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001"
            "0802000000907753de0000000c4944415408d763f8cfc000"
            "0003010100c9fe92ef0000000049454e44ae426082"
        )
    )


def _options(root: Path, image_provider: str, image_model: str) -> GenerationOptions:
    return GenerationOptions(
        script_model=ScriptModelConfig(provider="test", model="test"),
        image_model=ImageModelConfig(provider=image_provider, model=image_model),
        references=ReferencesOptions(output_dir=root / "references"),
        upscale=UpscaleOptions(output_dir=root / "pages_upscaled"),
        script_path=root / "bdgen-script.json",
        output_path=root / "demo.pdf",
    )


def _config(output_root: Path, image_provider: str, image_model: str) -> BdGenInput:
    root = output_root / "demo"
    return BdGenInput(
        project="demo",
        output_root=output_root,
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        story=Story(synopsis="Une histoire.", genre="test", tone="leger", setting="ici"),
        style=Style(art_style="ligne claire"),
        characters=[],
        locations=[],
        objects=[],
        structure=Structure(page_count=1),
        generation_options=_options(root, image_provider, image_model),
    )


def _script(root: Path) -> BdGenScript:
    return BdGenScript(
        project="demo",
        display_name="Demo",
        source=ScriptSource(
            input_file="bdgen.json",
            generated_at="2026-05-01T00:00:00Z",
            script_model="test/test",
        ),
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        style=Style(art_style="ligne claire"),
        generation_options=_options(root, "openai", "gpt-image-2"),
        characters=[
            ScriptCharacter(
                id="hero",
                name="Hero",
                physical_description="Hero desc",
                reference_prompt="Hero prompt",
            )
        ],
        locations=[
            ScriptLocation(
                id="home",
                name="Home",
                description="Home desc",
                reference_prompt="Home prompt",
            )
        ],
        objects=[
            ScriptObject(
                id="book",
                name="Book",
                description="Book desc",
                reference_prompt="Book prompt",
            )
        ],
        pages=[
            Page(
                page_number=1,
                panels=[
                    Panel(
                        panel_number=1,
                        location="home",
                        characters=["hero"],
                        objects=["book"],
                        scene_description="Hero lit le livre.",
                    )
                ],
            )
        ],
    )


def test_image_model_change_updates_script_options_and_marks_images_stale(tmp_path: Path) -> None:
    output_root = tmp_path
    project_root = output_root / "demo"
    save_config(_config(output_root, "openai", "gpt-image-2"), output_root)
    _script(project_root).save(project_root / "bdgen-script.json")
    _png(project_root / "references" / "characters" / "hero.png")
    _png(project_root / "references" / "locations" / "home.png")
    _png(project_root / "references" / "objects" / "book.png")
    _png(project_root / "pages" / "page_01.png")

    updated = _config(output_root, "openai", "gpt-image-1")
    detect_and_mark_stale("demo", updated, output_root)
    save_config(updated, output_root)

    script = BdGenScript.load(project_root / "bdgen-script.json")
    assert script.generation_options.image_model.provider == "openai"
    assert script.generation_options.image_model.model == "gpt-image-1"

    opts = _resolve_options(script, "demo", output_root)
    assert opts.image_model.provider == "openai"
    assert opts.image_model.model == "gpt-image-1"

    stale = read_stale_index(project_root)
    assert set(stale["references"]) == {"hero", "home", "book"}
    assert stale["compose"] == ["page_1"]

    persisted_config = load_config("demo", output_root)
    assert persisted_config.generation_options.image_model.provider == "openai"
    assert persisted_config.generation_options.image_model.model == "gpt-image-1"


def test_legacy_xai_image_config_is_coerced_to_openai(tmp_path: Path) -> None:
    output_root = tmp_path
    config = _config(output_root, "xai", "legacy-xai-image-model")
    config_path = output_root / "demo" / "bdgen.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.to_portable_dict(config_path), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    persisted_config = load_config("demo", output_root)
    assert persisted_config.generation_options.image_model.provider == "openai"
    assert persisted_config.generation_options.image_model.model == "gpt-image-2"
