from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from bdgen.models import (
    BdGenInput,
    BdGenScript,
    Metadata,
    Story,
    Structure,
    Style,
)
from bdgen.service import (
    detect_and_mark_stale,
    load_config,
    read_stale_index,
    save_config,
    _resolve_options,
)

from tests.factories import make_minimal_script, make_options


def _config(output_root: Path, image_provider: str, image_model: str) -> BdGenInput:
    project_root = output_root / "demo"
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
        generation_options=make_options(project_root, image_provider=image_provider, image_model=image_model),
    )


def test_image_model_change_updates_script_options_and_marks_images_stale(
    tmp_path: Path,
    make_png: Callable[[Path], None],
) -> None:
    output_root = tmp_path
    project_root = output_root / "demo"
    save_config(_config(output_root, "openai", "gpt-image-2"), output_root)
    make_minimal_script(project_root).save(project_root / "bdgen-script.json")
    make_png(project_root / "references" / "characters" / "hero.png")
    make_png(project_root / "references" / "locations" / "home.png")
    make_png(project_root / "references" / "objects" / "book.png")
    make_png(project_root / "pages" / "page_01.png")

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
