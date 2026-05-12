"""Pydantic models for bdgen.json (input) and bdgen-script.json (LLM output)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PageFormat = Literal["portrait", "landscape", "square", "strip"]

# OpenAI gpt-image-* accepts a fixed set of canvas sizes; pick the closest match
# to each user-facing format. "strip" reuses landscape and conveys the strip
# look through the layout prompt rather than the canvas, since the API does not
# support arbitrary aspect ratios.
_PAGE_FORMAT_TO_SIZE: dict[str, str] = {
    "portrait": "1024x1536",
    "landscape": "1536x1024",
    "square": "1024x1024",
    "strip": "1536x1024",
}


def image_size_for_format(page_format: str | None) -> str:
    return _PAGE_FORMAT_TO_SIZE.get(page_format or "portrait", "1024x1536")


def _resolve_path(value: Path | str | None, base_dir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _portable_path(value: Path | str | None, base_dir: Path) -> str | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return Path(os.path.relpath(path, start=base_dir)).as_posix()
    except ValueError:
        return path.as_posix()


# --- Shared ---

class Metadata(BaseModel):
    title: str
    author: str
    language: str = "fr"


class Style(BaseModel):
    art_style: str
    color_palette: str | None = None
    line_work: str | None = None
    mood: str | None = None
    negative_constraints: str | None = None
    stylization_level: str | None = None
    panel_borders: str | None = None
    speech_bubbles: str | None = None
    character_rendering: str | None = None


# --- Input (bdgen.json) ---

class Story(BaseModel):
    synopsis: str
    genre: str | None = None
    tone: str | None = None
    setting: str | None = None
    target_audience: str | None = None


class CharacterInput(BaseModel):
    id: str
    name: str
    role: str | None = None
    physical_description: str
    outfit: str | None = None
    personality: str | None = None


class LocationInput(BaseModel):
    """User-provided seed for a location.

    The LLM copies these verbatim during the setup phase and adds the
    English ``reference_prompt`` needed by the image generator.
    """
    id: str
    name: str
    description: str


class ObjectInput(BaseModel):
    """User-provided seed for a recurring object / product / reference.

    Examples: a specific book the BD is about, a product to feature, a
    distinctive prop. The LLM copies these verbatim during the setup phase
    and adds the English ``reference_prompt`` used to generate a stylized
    caricature in the project's art style.
    """
    id: str
    name: str
    description: str


class Structure(BaseModel):
    page_count: int
    panels_per_page_avg: int | None = None
    panels_per_page_range: tuple[int, int] | None = None
    include_cover: bool = False
    include_back_cover: bool = False
    narrative_pacing: str | None = None
    # Page canvas format. Drives the image generation size and the layout
    # guidance fed to both the script LLM and the image model.
    # ``strip`` is a single horizontal row of panels on a landscape canvas.
    page_format: PageFormat = "portrait"
    # When False, the LLM must use ONLY the characters / locations / objects
    # supplied by the user. When True (default), it may invent additional ones
    # if the story arc needs them. Defaults preserve previous behavior on
    # existing projects loaded from disk.
    allow_extra_characters: bool = True
    allow_extra_locations: bool = True
    allow_extra_objects: bool = True


class ScriptModelConfig(BaseModel):
    provider: str = "openai"
    model: str
    temperature: float = 0.8


class ImageModelConfig(BaseModel):
    provider: str = "openai"
    model: str
    size: str = "1024x1536"
    quality: str = "high"


class UpscaleOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    mode: Literal["target", "factor"] = "target"
    target_megapixels: int = 4
    scale_factor: float = 2.0
    output_format: Literal["png", "jpg", "webp"] = "png"
    output_quality: int = 90
    output_dir: Path | None = None


class ReferencesOptions(BaseModel):
    generate: bool = True
    output_dir: Path | None = None
    image_model: ImageModelConfig | None = None
    character_views: list[str] = Field(
        default_factory=lambda: ["face_closeup", "full_body_front", "expressions_sheet"]
    )
    location_view: str = "establishing_shot"
    use_as_input_for_panels: bool = True


class GenerationOptions(BaseModel):
    script_model: ScriptModelConfig
    image_model: ImageModelConfig
    upscale: UpscaleOptions = Field(default_factory=UpscaleOptions)
    references: ReferencesOptions = Field(default_factory=ReferencesOptions)
    render_dialogs_separately: bool = True
    output_format: Literal["pdf", "images", "html"] = "pdf"
    output_path: Path | None = None
    script_path: Path | None = None

    def reference_image_model(self) -> ImageModelConfig:
        return self.references.image_model or self.image_model


class BdGenInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str | None = None
    # Human-readable name shown in the project listing. Distinct from
    # ``metadata.title`` (the BD's in-content title) and from ``project``
    # (the on-disk slug). Never appears in generated content.
    display_name: str | None = None
    output_root: Path = Path("./output")
    metadata: Metadata
    story: Story
    style: Style
    characters: list[CharacterInput]
    locations: list[LocationInput] = Field(default_factory=list)
    objects: list[ObjectInput] = Field(default_factory=list)
    structure: Structure
    generation_options: GenerationOptions
    # When True, the strict non-copying rule attached to the style-reference
    # image is lifted: the image generator is allowed to closely emulate the
    # reference (characters, costumes, motifs) in order to reproduce a known
    # visual style. Defaults to False — the safe, non-infringing behaviour.
    # The user is solely responsible for any copyright implications when this
    # flag is enabled.
    allow_style_copy: bool = False

    @classmethod
    def load(cls, path: Path) -> "BdGenInput":
        config_path = Path(path)
        obj = cls.model_validate(json.loads(config_path.read_text(encoding="utf-8")))
        if obj.project is None:
            obj.project = config_path.stem
        obj._fill_default_paths(config_path)
        return obj

    def _fill_default_paths(self, config_path: Path | None = None) -> None:
        """Force every output path under ``{output_root}/{project}/``.

        Any explicit ``script_path``, ``output_path``, or ``references.output_dir``
        previously set on the config are overridden. The convention is firm:
        outputs always live in a project-specific subdirectory of ``output_root``
        for predictability, organisation, and to avoid stray files at the project
        root. To customise the location, change ``project`` or ``output_root``.
        """
        if self.project is None:
            return
        if config_path is not None and config_path.name == "bdgen.json":
            proj_dir = config_path.parent.resolve()
            self.output_root = proj_dir.parent
        else:
            base_dir = config_path.parent if config_path is not None else Path.cwd()
            resolved_root = _resolve_path(self.output_root, base_dir) or Path("./output").resolve()
            self.output_root = resolved_root
            proj_dir = resolved_root / self.project
        go = self.generation_options
        go.script_path = proj_dir / "bdgen-script.json"
        go.output_path = proj_dir / f"{self.project}.pdf"
        go.references.output_dir = proj_dir / "references"
        go.upscale.output_dir = proj_dir / "pages_upscaled"

    def to_portable_dict(self, config_path: Path | None = None) -> dict:
        payload = self.model_dump(mode="json", exclude_none=False)
        if config_path is None:
            return payload
        config_dir = config_path.parent
        payload["output_root"] = _portable_path(self.output_root, config_dir)
        generation_options = payload.get("generation_options", {})
        generation_options["script_path"] = _portable_path(
            self.generation_options.script_path, config_dir
        )
        generation_options["output_path"] = _portable_path(
            self.generation_options.output_path, config_dir
        )
        references = generation_options.get("references", {})
        references["output_dir"] = _portable_path(
            self.generation_options.references.output_dir, config_dir
        )
        generation_options["references"] = references
        upscale = generation_options.get("upscale", {})
        upscale["output_dir"] = _portable_path(
            self.generation_options.upscale.output_dir, config_dir
        )
        generation_options["upscale"] = upscale
        payload["generation_options"] = generation_options
        return payload


# --- Output (bdgen-script.json) ---

class ScriptCharacter(BaseModel):
    id: str
    name: str
    physical_description: str
    outfit: str | None = None
    reference_prompt: str
    reference_image: Path | None = None


class ScriptLocation(BaseModel):
    id: str
    name: str
    description: str
    reference_prompt: str
    reference_image: Path | None = None


class ScriptObject(BaseModel):
    """Recurring object / product / reference featured in the BD."""
    id: str
    name: str
    description: str
    reference_prompt: str
    reference_image: Path | None = None


class Cover(BaseModel):
    scene_description: str
    title_placement: str | None = None
    subtitle: str | None = None
    tagline: str | None = None


class BackCover(BaseModel):
    synopsis_blurb: str
    scene_description: str | None = None
    tagline: str | None = None
    layout_notes: str | None = None


class Dialog(BaseModel):
    speaker: str
    type: Literal["speech", "thought", "shout", "whisper", "narration"]
    text: str


class Panel(BaseModel):
    panel_number: int
    size: str | None = None
    location: str
    characters: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    shot: str | None = None
    scene_description: str
    narration: str | None = None
    dialogs: list[Dialog] = Field(default_factory=list)
    sound_effects: list[str] = Field(default_factory=list)


class Page(BaseModel):
    page_number: int
    layout: str | None = None
    panels: list[Panel]


class ScriptSource(BaseModel):
    input_file: str
    generated_at: str
    script_model: str


class BdGenScript(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str | None = None
    display_name: str | None = None
    source: ScriptSource
    metadata: Metadata
    style: Style
    # Defaults to "portrait" so existing scripts on disk keep their behavior
    # when reloaded. New scripts inherit the value from their input Structure
    # via _build_skeleton.
    page_format: PageFormat = "portrait"
    # Mirrors BdGenInput.allow_style_copy so the compose/references steps
    # have everything they need on the script itself. Defaults to False so
    # scripts written before the flag existed keep the safe behaviour.
    allow_style_copy: bool = False
    generation_options: GenerationOptions | None = None
    characters: list[ScriptCharacter]
    locations: list[ScriptLocation]
    objects: list[ScriptObject] = Field(default_factory=list)
    cover: Cover | None = None
    back_cover: BackCover | None = None
    pages: list[Page]

    @classmethod
    def load(cls, path: Path) -> "BdGenScript":
        script_path = Path(path)
        obj = cls.model_validate(json.loads(script_path.read_text(encoding="utf-8")))
        obj._enforce_path_consistency(script_path)
        return obj

    def _enforce_path_consistency(self, script_path: Path) -> None:
        """Force all derived paths to live alongside this script file.

        The script's directory is the project directory by convention. Any
        explicit path embedded in ``generation_options`` is overridden so the
        script can be moved between machines or directories without dragging
        stale absolute paths along.
        """
        if self.generation_options is None:
            return
        proj_dir = script_path.parent.resolve()
        project_name = self.project or proj_dir.name
        go = self.generation_options
        self.source.input_file = str(proj_dir / "bdgen.json")
        go.script_path = proj_dir / "bdgen-script.json"
        go.output_path = proj_dir / f"{project_name}.pdf"
        go.references.output_dir = proj_dir / "references"
        go.upscale.output_dir = proj_dir / "pages_upscaled"
        for character in self.characters:
            character.reference_image = _resolve_path(character.reference_image, proj_dir)
        for location in self.locations:
            location.reference_image = _resolve_path(location.reference_image, proj_dir)
        for obj in self.objects:
            obj.reference_image = _resolve_path(obj.reference_image, proj_dir)

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_portable_dict(p), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_portable_dict(self, script_path: Path | None = None) -> dict:
        payload = self.model_dump(mode="json", exclude_none=False)
        if script_path is None:
            return payload
        project_dir = script_path.parent
        source = payload.get("source", {})
        source["input_file"] = _portable_path(self.source.input_file, project_dir)
        payload["source"] = source
        generation_options = payload.get("generation_options", {})
        generation_options["script_path"] = _portable_path(
            self.generation_options.script_path, project_dir
        )
        generation_options["output_path"] = _portable_path(
            self.generation_options.output_path, project_dir
        )
        references = generation_options.get("references", {})
        references["output_dir"] = _portable_path(
            self.generation_options.references.output_dir, project_dir
        )
        generation_options["references"] = references
        upscale = generation_options.get("upscale", {})
        upscale["output_dir"] = _portable_path(
            self.generation_options.upscale.output_dir, project_dir
        )
        generation_options["upscale"] = upscale
        payload["generation_options"] = generation_options
        for items_key, items in (
            ("characters", self.characters),
            ("locations", self.locations),
            ("objects", self.objects),
        ):
            serialised_items = payload.get(items_key, [])
            for item_payload, item in zip(serialised_items, items, strict=False):
                item_payload["reference_image"] = _portable_path(
                    item.reference_image, project_dir
                )
        return payload

    def character_by_id(self, cid: str) -> ScriptCharacter | None:
        return next((c for c in self.characters if c.id == cid), None)

    def location_by_id(self, lid: str) -> ScriptLocation | None:
        return next((l for l in self.locations if l.id == lid), None)

    def object_by_id(self, oid: str) -> ScriptObject | None:
        return next((o for o in self.objects if o.id == oid), None)

    def project_dir(self, fallback_script_path: Path | None = None) -> Path:
        """Return the project's directory.

        Priority: explicit ``script_path.parent`` from generation_options, then
        ``project`` field combined with a default ``./output`` root, then the
        parent of ``fallback_script_path`` if provided.
        """
        if self.generation_options is not None and self.generation_options.script_path is not None:
            return Path(self.generation_options.script_path).parent
        if self.project is not None:
            return Path("./output") / self.project
        if fallback_script_path is not None:
            return Path(fallback_script_path).parent
        return Path("./output")
