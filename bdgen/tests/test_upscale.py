from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from bdgen.models import (
    BdGenScript,
    Cover,
    GenerationOptions,
    ImageModelConfig,
    Metadata,
    ReferencesOptions,
    ScriptModelConfig,
    ScriptSource,
    Style,
    UpscaleOptions,
)
from bdgen.progress import NullReporter


def _fake_replicate_output(width: int = 400, height: int = 600) -> MagicMock:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="blue").save(buf, format="PNG")
    buf.seek(0)
    output = MagicMock()
    output.read.return_value = buf.getvalue()
    return output


@patch.dict("os.environ", {"REPLICATE_API_TOKEN": "test-token"})
def test_upscale_calls_replicate_and_writes_output(tmp_path: Path) -> None:
    mock_replicate = MagicMock()
    mock_replicate.run.return_value = _fake_replicate_output()

    with patch.dict(sys.modules, {"replicate": mock_replicate}):
        from bdgen.upscale import upscale_pages

        pages = tmp_path / "pages"
        pages.mkdir()
        source = pages / "cover.png"
        Image.new("RGB", (200, 300), color="white").save(source)

        script = BdGenScript(
            project="demo",
            display_name="Demo",
            source=ScriptSource(
                input_file="demo.json",
                generated_at="2026-04-29T00:00:00Z",
                script_model="test",
            ),
            metadata=Metadata(title="Demo", author="Tester", language="fr"),
            style=Style(art_style="ligne claire"),
            generation_options=GenerationOptions(
                script_model=ScriptModelConfig(provider="test", model="test"),
                image_model=ImageModelConfig(provider="test", model="test"),
                references=ReferencesOptions(),
                upscale=UpscaleOptions(
                    enabled=True,
                    output_dir=tmp_path / "pages_upscaled",
                ),
            ),
            characters=[],
            locations=[],
            cover=Cover(scene_description="cover"),
            back_cover=None,
            pages=[],
        )

        out_dir = upscale_pages(
            script,
            project_dir=tmp_path,
            options=script.generation_options.upscale,
            reporter=NullReporter(),
            force=True,
        )

        upscaled = out_dir / "cover.png"
        assert upscaled.exists()
        mock_replicate.run.assert_called_once()
        call_args = mock_replicate.run.call_args
        assert "prunaai/p-image-upscale" in call_args[0][0]
        assert call_args[1]["input"]["upscale_mode"] == "target"
        assert call_args[1]["input"]["target"] == 4
        with Image.open(upscaled) as img:
            assert img.size == (400, 600)
