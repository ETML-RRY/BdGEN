from __future__ import annotations

from pathlib import Path

from bdgen.models import (
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
    Style,
    UpscaleOptions,
)


def make_options(
    root: Path,
    *,
    image_provider: str = "openai",
    image_model: str = "gpt-image-2",
) -> GenerationOptions:
    return GenerationOptions(
        script_model=ScriptModelConfig(provider="test", model="test"),
        image_model=ImageModelConfig(provider=image_provider, model=image_model),
        references=ReferencesOptions(output_dir=root / "references"),
        upscale=UpscaleOptions(output_dir=root / "pages_upscaled"),
        script_path=root / "bdgen-script.json",
        output_path=root / "output.pdf",
    )


def make_minimal_script(
    root: Path,
    *,
    project: str = "demo",
    image_provider: str = "openai",
    image_model: str = "gpt-image-2",
) -> BdGenScript:
    return BdGenScript(
        project=project,
        display_name=project.title(),
        source=ScriptSource(
            input_file="bdgen.json",
            generated_at="2026-01-01T00:00:00Z",
            script_model="test/test",
        ),
        metadata=Metadata(title=project.title(), author="Tester", language="fr"),
        style=Style(art_style="ligne claire"),
        generation_options=make_options(root, image_provider=image_provider, image_model=image_model),
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
                        scene_description=f"{project} scene.",
                    )
                ],
            )
        ],
    )
