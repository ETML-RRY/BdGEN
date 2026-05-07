from __future__ import annotations

from pathlib import Path

from bdgen.compose import _collect_refs
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
from bdgen.service import attach_existing_reference_images


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001"
            "0802000000907753de0000000c4944415408d763f8cfc000"
            "0003010100c9fe92ef0000000049454e44ae426082"
        )
    )


def _script(root: Path) -> BdGenScript:
    return BdGenScript(
        project="copy",
        display_name="Copy",
        source=ScriptSource(
            input_file="bdgen.json",
            generated_at="2026-04-30T00:00:00Z",
            script_model="test/test",
        ),
        metadata=Metadata(title="Copy", author="Tester", language="fr"),
        style=Style(art_style="ligne claire"),
        generation_options=GenerationOptions(
            script_model=ScriptModelConfig(provider="test", model="test"),
            image_model=ImageModelConfig(provider="openai", model="gpt-image-2"),
            references=ReferencesOptions(output_dir=root / "references"),
            upscale=UpscaleOptions(output_dir=root / "pages_upscaled"),
            script_path=root / "bdgen-script.json",
            output_path=root / "copy.pdf",
        ),
        characters=[
            ScriptCharacter(
                id="hero",
                name="Hero",
                physical_description="Hero desc",
                reference_prompt="Hero prompt",
                reference_image=None,
            )
        ],
        locations=[
            ScriptLocation(
                id="home",
                name="Home",
                description="Home desc",
                reference_prompt="Home prompt",
                reference_image=None,
            )
        ],
        objects=[
            ScriptObject(
                id="book",
                name="Book",
                description="Book desc",
                reference_prompt="Book prompt",
                reference_image=None,
            )
        ],
        pages=[
            Page(
                page_number=1,
                layout="one panel",
                panels=[
                    Panel(
                        panel_number=1,
                        location="home",
                        characters=["hero"],
                        objects=["book"],
                        scene_description="Hero reads the book at home.",
                    )
                ],
            )
        ],
    )


def test_existing_copied_references_are_attached_and_used_for_compose(tmp_path: Path) -> None:
    _png(tmp_path / "references" / "characters" / "hero.png")
    _png(tmp_path / "references" / "locations" / "home.png")
    _png(tmp_path / "references" / "objects" / "book.png")

    script = _script(tmp_path)
    changed = attach_existing_reference_images(tmp_path, script)

    assert changed is True
    assert script.characters[0].reference_image == tmp_path / "references" / "characters" / "hero.png"
    assert script.locations[0].reference_image == tmp_path / "references" / "locations" / "home.png"
    assert script.objects[0].reference_image == tmp_path / "references" / "objects" / "book.png"

    refs = _collect_refs(script, script.pages[0])
    assert len(refs) == 3
    assert {p.name for p, _ in refs} == {"hero.png", "home.png", "book.png"}
