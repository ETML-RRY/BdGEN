from __future__ import annotations

import io
import sys
import tempfile
import unittest
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


class UpscaleTests(unittest.TestCase):
    @patch.dict("os.environ", {"REPLICATE_API_TOKEN": "test-token"})
    def test_upscale_calls_replicate_and_writes_output(self) -> None:
        mock_replicate = MagicMock()
        mock_replicate.run.return_value = _fake_replicate_output()

        with patch.dict(sys.modules, {"replicate": mock_replicate}):
            from bdgen.upscale import upscale_pages

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                pages = root / "pages"
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
                            output_dir=root / "pages_upscaled",
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
                    project_dir=root,
                    options=script.generation_options.upscale,
                    reporter=NullReporter(),
                    force=True,
                )

                upscaled = out_dir / "cover.png"
                self.assertTrue(upscaled.exists())
                mock_replicate.run.assert_called_once()
                call_args = mock_replicate.run.call_args
                self.assertIn("prunaai/p-image-upscale", call_args[0][0])
                self.assertEqual(call_args[1]["input"]["upscale_mode"], "target")
                self.assertEqual(call_args[1]["input"]["target"], 4)
                with Image.open(upscaled) as img:
                    self.assertEqual(img.size, (400, 600))


if __name__ == "__main__":
    unittest.main()
