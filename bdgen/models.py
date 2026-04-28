"""Pydantic models for bdgen.json (input) and bdgen-script.json (LLM output)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class ReferencesOptions(BaseModel):
    generate: bool = True
    output_dir: Path | None = None
    character_views: list[str] = Field(
        default_factory=lambda: ["face_closeup", "full_body_front", "expressions_sheet"]
    )
    location_view: str = "establishing_shot"
    use_as_input_for_panels: bool = True


class GenerationOptions(BaseModel):
    script_model: ScriptModelConfig
    image_model: ImageModelConfig
    references: ReferencesOptions = Field(default_factory=ReferencesOptions)
    render_dialogs_separately: bool = True
    output_format: Literal["pdf", "images", "html"] = "pdf"
    output_path: Path | None = None
    script_path: Path | None = None


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

    @classmethod
    def load(cls, path: Path) -> "BdGenInput":
        obj = cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
        if obj.project is None:
            obj.project = Path(path).stem
        obj._fill_default_paths()
        return obj

    def _fill_default_paths(self) -> None:
        """Force every output path under ``{output_root}/{project}/``.

        Any explicit ``script_path``, ``output_path``, or ``references.output_dir``
        previously set on the config are overridden. The convention is firm:
        outputs always live in a project-specific subdirectory of ``output_root``
        for predictability, organisation, and to avoid stray files at the project
        root. To customise the location, change ``project`` or ``output_root``.
        """
        if self.project is None:
            return
        proj_dir = self.output_root / self.project
        go = self.generation_options
        go.script_path = proj_dir / "bdgen-script.json"
        go.output_path = proj_dir / f"{self.project}.pdf"
        go.references.output_dir = proj_dir / "references"


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
    generation_options: GenerationOptions | None = None
    characters: list[ScriptCharacter]
    locations: list[ScriptLocation]
    objects: list[ScriptObject] = Field(default_factory=list)
    cover: Cover | None = None
    back_cover: BackCover | None = None
    pages: list[Page]

    @classmethod
    def load(cls, path: Path) -> "BdGenScript":
        obj = cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
        obj._enforce_path_consistency(Path(path))
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
        proj_dir = script_path.parent
        project_name = self.project or proj_dir.name
        go = self.generation_options
        go.script_path = proj_dir / "bdgen-script.json"
        go.output_path = proj_dir / f"{project_name}.pdf"
        go.references.output_dir = proj_dir / "references"

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

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
