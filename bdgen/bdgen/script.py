"""Step 1: generate the script in two phases (setup + per-page) with bounded retries."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import threading
from textwrap import dedent
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .feedback import feedback_block
from .models import (
    BackCover,
    BdGenInput,
    BdGenScript,
    Cover,
    Page,
    ScriptCharacter,
    ScriptLocation,
    ScriptModelConfig,
    ScriptObject,
    ScriptSource,
)
from . import secret_store
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)
from .stats import TimedCall, normalise_usage, record_event, start_timer, stop_timer
from . import trace

MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 2
ANTHROPIC_DEFAULT_INPUT_TOKENS_PER_MINUTE = 30_000
ANTHROPIC_TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4
ANTHROPIC_TOKEN_ESTIMATE_SAFETY_TOKENS = 1_000
ANTHROPIC_DEFAULT_TIMEOUT_SECONDS = 1_800
ANTHROPIC_DEFAULT_EFFORT = "medium"
ANTHROPIC_EFFORT_LEVELS = {"low", "medium", "high", "max", "xhigh"}

_ANTHROPIC_THROTTLE_LOCK = threading.Lock()
_ANTHROPIC_THROTTLE_STATE = {
    "tokens": float(ANTHROPIC_DEFAULT_INPUT_TOKENS_PER_MINUTE),
    "last": time.monotonic(),
}

T = TypeVar("T", bound=BaseModel)


@dataclass
class _LLMCallResult:
    value: BaseModel
    usage: dict
    elapsed_seconds: float
    started_at: str


class _RetryableRateLimit(RuntimeError):
    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


SETUP_SYSTEM_PROMPT = dedent("""\
    You are a professional comic book ("bande dessinée") scriptwriter and storyboard director.

    You are working on a multi-page BD project. Your current task is the SETUP phase ONLY:
    produce the characters, locations, objects, cover, and back cover. The page contents
    (panels, dialogs) will be generated in subsequent calls — DO NOT include any pages in
    this response.

    You must produce JSON containing:

    1. CHARACTERS — first, for EACH entry in the input `characters` array, copy `id`,
       `name`, `physical_description` and `outfit` verbatim. ADD `reference_prompt`: a
       detailed English image-generation prompt for a character sheet showing THREE
       views on a single image with a neutral white background — face close-up, full
       body front, and an expressions sheet.
       The prompt must describe the character's full physical appearance and outfit
       with as much visual specificity as possible (hair, face, build, skin tone, age,
       clothing cut and colors, accessories). Do NOT include any art style, color
       palette, line work, rendering technique, or stylization instructions — visual
       style is injected separately at image-generation time.
       HANDS AND ARMS — MANDATORY in every `reference_prompt`: the full-body
       front view MUST explicitly show both hands with clearly separated fingers
       (5 fingers per hand: 4 fingers + 1 thumb). Include the instruction:
       "Both hands fully visible at the character's sides with all five fingers
       on each hand clearly defined and anatomically correct — four fingers plus
       one shorter opposable thumb per hand. Arms with correct proportions:
       shoulder to elbow to wrist, single elbow joint per arm."
       The prompt MUST end with "No text. No speech bubbles." Whether
       you may invent ADDITIONAL characters is decided by the AUTHORING RULES at the
       end of the user message.

    2. LOCATIONS — first, for EACH entry in the input `locations` array (which may be
       empty), copy `id`, `name`, and `description` verbatim. ADD `reference_prompt`:
       an English image-generation prompt for a hand-drawn comic-book background
       illustration of the place, no characters, no text. The prompt MUST open with
       a phrase that anchors the output as a drawn illustration — never as a
       photograph or photorealistic scene — such as "A hand-drawn comic-book
       background panel showing…" or "A stylized comic-book illustration of…".
       The prompt must describe the place's key visual features — spatial layout,
       dominant landmarks, characteristic architecture, atmosphere and lighting mood —
       with as much specificity as possible. Avoid photographic vocabulary (depth of
       field, bokeh, establishing shot, camera, lens); use illustration vocabulary
       instead (composition, foreground, midground, scene, layout). Do NOT include
       any art style, color palette, line work, rendering technique, or stylization
       instructions — visual style is injected separately at image-generation time.
       End with "No text. No characters." Whether you may invent ADDITIONAL locations
       is decided by the AUTHORING RULES at the end of the user message.

    3. OBJECTS — first, for EACH entry in the input `objects` array (which may be
       empty), copy `id`, `name`, and `description` verbatim. ADD `reference_prompt`:
       an English image-generation prompt for a hand-drawn comic-book object
       reference sheet showing the object isolated on a neutral white background,
       no characters, no text. The prompt MUST open with a phrase that anchors the
       output as a drawn illustration — never as a product photograph — such as
       "A hand-drawn comic-book illustration of…" or "A stylized object reference
       sheet showing…". The prompt must describe the object's shape, proportions,
       silhouette, key structural details, dominant colors and any distinctive
       markings with as much specificity as possible. Avoid photographic vocabulary
       (product shot, studio photo, macro, depth of field, lighting rig); use
       illustration vocabulary instead (drawing, illustration, reference sheet,
       composition). If the user provided a photo of this object (passed at
       image-generation time), the resulting illustration must remain recognizably
       the SAME object — same shape, key markings, characteristic silhouette. Do NOT
       include any art style, color palette, line work, rendering technique, or
       stylization instructions — visual style is injected separately at
       image-generation time. Plan how each object will recur across the story so
       panels can reference it consistently. End with "No text. No characters."
       Whether you may invent ADDITIONAL objects is decided by the AUTHORING RULES
       at the end of the user message.

    4. COVER — only if `structure.include_cover` is true. Provide:
       - `scene_description`: an evocative illustration concept for the front cover
       - `title_placement`: hint for where and how the title is laid out
       - `subtitle`: optional subtitle or null
       - `tagline`: optional short marketing tagline or null

    5. BACK COVER — only if `structure.include_back_cover` is true. Provide:
       - `synopsis_blurb`: a 3-5 sentence marketing-tone presentation of the story
         WITHOUT spoilers, ending on a hook
       - `scene_description`: optional small illustration concept for the back, or null
       - `tagline`: optional short tagline or null
       - `layout_notes`: optional layout hints (e.g. "barcode bottom-right corner")

    HARD CONSTRAINTS:
    - Write narrative content (location/object names and descriptions, blurb) in the
      language specified by `metadata.language`.
    - Write all `reference_prompt` fields in English regardless of `metadata.language`.
    - DESCRIBE, NEVER NAME — in EVERY field you produce (reference_prompt,
      scene_description, synopsis_blurb, tagline, title_placement, layout_notes,
      character/location/object name and description), NEVER use the proper name
      of any real-world artist, illustrator, studio, publisher, franchise, series,
      brand, mascot or copyrighted character. If the input brief invokes such a
      name as a stylistic inspiration (e.g. "in the style of <name>",
      "<franchise>-like"), treat it as a CUE ONLY: translate it into precise
      visual descriptors (line quality, palette, proportions, costumes,
      decorative motifs, panel rhythm, color blocking technique) and use those
      descriptors instead. Emulate the LOOK, never the LABEL — even when the
      user has lifted the copyright safeguard, the generated content must still
      describe its inspiration in pure visual terms rather than naming the
      source.
    - Honor the AUTHORING RULES at the end of the user message regarding inventing
      additional characters, locations or objects.
    - Plan characters, locations and objects for the full story arc, not just for the
      opening.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


PAGE_SYSTEM_PROMPT = dedent("""\
    You are a professional comic book ("bande dessinée") scriptwriter.

    You are writing ONE page of a multi-page comic book. The project brief, the setup
    (characters, locations, objects, cover, back cover) and any previously generated
    pages are provided in the user message.

    Your task: produce ONLY the requested page. Honor the structural constraints (panels
    per page average, range), populate panels with vivid scene descriptions and dialogs,
    and ensure narrative coherence with prior pages. Pace the story so the full arc
    resolves by the final page.

    You must produce JSON for one Page object:
    {
      "page_number": <integer>,
      "layout": "<short composition description>",
      "panels": [
        {
          "panel_number": <1-indexed integer within the page>,
          "size": "small" | "medium" | "large" | "half_page" | "full_page",
          "location": "<id from the setup's locations list>",
          "characters": ["<character id>", ...],
          "objects": ["<object id>", ...],
          "shot": "<e.g. plan large, plan moyen, gros plan, contre-plongée>",
          "scene_description": "<1-3 vivid sentences>",
          "narration": "<optional off-frame caption text, or null>",
          "dialogs": [
            {"speaker": "<character id>", "type": "speech|thought|shout|whisper|narration", "text": "<...>"}
          ],
          "sound_effects": ["<optional onomatopoeia>"]
        }
      ]
    }

    HARD CONSTRAINTS:
    - Write narrative content (scene descriptions, narration, dialogs, sound effects)
      in the language specified by `metadata.language`.
    - The page's `layout` description MUST exactly describe the number of panels you
      produce. Don't say "3 cases" if you emit 4 panels.
    - Use ONLY character ids, location ids and object ids defined in the setup. Do not
      introduce new ones in this call.
    - List in `objects` the ids of EVERY object visible in the panel (only objects from
      the setup; leave the array empty if none). When an object is in the panel,
      reference it explicitly in `scene_description` so its placement is unambiguous.
    - Honor `structure.panels_per_page_avg` and `structure.panels_per_page_range`.
    - Vary panel sizes and camera shots for visual rhythm.
    - Keep dialog lines short — they have to fit in speech bubbles.
    - Ensure narrative continuity: don't repeat or contradict prior pages.
    - DESCRIBE, NEVER NAME — NEVER reference, in `scene_description`, `narration`,
      `dialogs`, `sound_effects` or any other field, the proper name of a
      real-world artist, illustrator, studio, publisher, franchise, series, brand,
      mascot or copyrighted character. If the brief invokes such a name as a
      stylistic inspiration, translate it into precise visual descriptors
      (silhouette, costume, palette, motif, decor cues) and use those descriptors
      instead. Emulate the LOOK, never the LABEL — even when the user has lifted
      the copyright safeguard.
    - Output ONLY the JSON object for this page. No markdown fences, no commentary.
    """)


# --- Draft models for LLM output ---


class _DraftCharacter(BaseModel):
    id: str
    name: str
    physical_description: str
    outfit: str | None = None
    reference_prompt: str


class _DraftLocation(BaseModel):
    id: str
    name: str
    description: str
    reference_prompt: str


class _DraftObject(BaseModel):
    id: str
    name: str
    description: str
    reference_prompt: str


class _LLMSetupDraft(BaseModel):
    characters: list[_DraftCharacter]
    locations: list[_DraftLocation]
    objects: list[_DraftObject] = []
    cover: Cover | None = None
    back_cover: BackCover | None = None


CHARACTER_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single character record for a comic book project.

    The user message contains a JSON wrapper with `metadata`, `style`,
    `current_character`, `has_user_photo`, and `user_feedback`. Treat it as
    INPUT CONTEXT only. Apply the feedback to `current_character` and return
    the UPDATED character record. You may rewrite `name`,
    `physical_description`, `outfit`, and `reference_prompt` as needed; the
    `id` MUST stay unchanged.

    OUTPUT SHAPE — your response is a flat JSON object with EXACTLY these
    top-level keys, and nothing else:
      {
        "id": "<unchanged>",
        "name": "...",
        "physical_description": "...",
        "outfit": "...",
        "reference_prompt": "..."
      }

    Do NOT echo back `metadata`, `style`, `current_character`, or
    `user_feedback`. Do NOT wrap the output under any key. Do NOT add extra
    fields.

    HARD CONSTRAINTS:
    - Keep `id` unchanged.
    - Write narrative content in the language specified by `metadata.language`.
    - Keep `reference_prompt` in English; it must end with "No text. No speech bubbles."
    - The `reference_prompt` MUST include an explicit instruction for anatomically
      correct hands (5 fingers per hand: 4 fingers + 1 opposable thumb) and arms
      (one elbow joint per arm, correct proportions shoulder→elbow→wrist).
    - Do NOT include any art style, color palette, line work, rendering technique,
      or stylization instructions in `reference_prompt` — visual style is injected
      separately at image-generation time.
    - USER-PHOTO ANCHOR — when `has_user_photo` is true, the user has uploaded a
      reference photograph of this character. That photo is the AUTHORITATIVE,
      NON-OVERRIDABLE source of the character's physical likeness. You MUST NOT
      alter, in `physical_description` or in any other field you produce, the
      traits a photograph encodes: face shape, head proportions, eye spacing
      and shape, nose, jawline, age range, build, hair type and silhouette,
      skin tone, ethnicity and distinguishing features (glasses, beard,
      freckles, moles, scars, dimples, piercings). You MAY refine costume,
      accessories, color choices, personality, narrative role and any non-
      photographic aspect. If `user_feedback` explicitly asks for a change
      that would contradict the photo (e.g. "make them older", "change the
      face", "different ethnicity"), IGNORE that specific part of the
      feedback and keep the photo-anchored traits exactly as they are — the
      user-supplied photo always wins over conflicting text feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, mascot or copyrighted character
      in any field. If the feedback invokes such a name, translate it into precise
      visual descriptors (silhouette, costume, palette, motif) and use those
      descriptors instead. This rule applies even when the user has lifted the
      copyright safeguard — emulate the LOOK, never the LABEL.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


LOCATION_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single location record for a comic book project.

    The user message contains a JSON wrapper with `metadata`, `style`,
    `current_location`, `has_user_photo`, and `user_feedback`. Treat it as
    INPUT CONTEXT only. Apply the feedback to `current_location` and return
    the UPDATED location record. The `id` MUST stay unchanged.

    OUTPUT SHAPE — your response is a flat JSON object with EXACTLY these
    top-level keys, and nothing else:
      {
        "id": "<unchanged>",
        "name": "...",
        "description": "...",
        "reference_prompt": "..."
      }

    Do NOT echo back `metadata`, `style`, `current_location`, or
    `user_feedback`. Do NOT wrap the output under any key. Do NOT add extra
    fields.

    HARD CONSTRAINTS:
    - Keep `id` unchanged.
    - Write narrative content in the language specified by `metadata.language`.
    - Keep `reference_prompt` in English; it must end with "No text. No characters."
    - The prompt MUST open with a phrase that anchors the output as a drawn
      illustration, never as a photograph (e.g. "A hand-drawn comic-book background
      panel showing…" or "A stylized comic-book illustration of…"). Avoid
      photographic vocabulary (establishing shot, depth of field, camera, lens,
      bokeh); use illustration vocabulary instead (composition, scene, layout,
      foreground, midground).
    - Do NOT include any art style, color palette, line work, rendering technique,
      or stylization instructions in `reference_prompt` — visual style is injected
      separately at image-generation time.
    - USER-PHOTO ANCHOR — when `has_user_photo` is true, the user has uploaded a
      reference photograph of this location. That photo is the AUTHORITATIVE,
      NON-OVERRIDABLE source of the location's appearance. You MUST NOT alter,
      in `description` or in any other field you produce, the traits a
      photograph encodes: overall spatial layout, perspective, recognizable
      landmarks (buildings, walls, doors, windows, terrain features), dominant
      materials and characteristic structure. You MAY refine mood, lighting,
      time of day, weather and any narrative aspect. If `user_feedback`
      explicitly asks for a change that would contradict the photo (e.g.
      "different architecture", "move the building elsewhere"), IGNORE that
      specific part of the feedback and keep the photo-anchored traits
      unchanged — the user-supplied photo always wins over conflicting text
      feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, landmark by trademark name,
      or copyrighted property in any field. If the feedback invokes such a name,
      translate it into precise visual descriptors (architecture, materials,
      palette, atmosphere) and use those descriptors instead. This rule applies
      even when the user has lifted the copyright safeguard — emulate the LOOK,
      never the LABEL.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


OBJECT_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single object / product / reference record for a comic
    book project.

    The user message contains a JSON wrapper with `metadata`, `style`,
    `current_object`, `has_user_photo`, and `user_feedback`. Treat it as
    INPUT CONTEXT only. Apply the feedback to `current_object` and return
    the UPDATED object record. The `id` MUST stay unchanged.

    OUTPUT SHAPE — your response is a flat JSON object with EXACTLY these
    top-level keys, and nothing else:
      {
        "id": "<unchanged>",
        "name": "...",
        "description": "...",
        "reference_prompt": "..."
      }

    Do NOT echo back `metadata`, `style`, `current_object`, or
    `user_feedback`. Do NOT wrap the output under any key. Do NOT add extra
    fields.

    HARD CONSTRAINTS:
    - Keep `id` unchanged.
    - Write narrative content in the language specified by `metadata.language`.
    - Keep `reference_prompt` in English; it must end with "No text. No characters."
    - The prompt MUST open with a phrase that anchors the output as a drawn
      illustration, never as a product photograph (e.g. "A hand-drawn comic-book
      illustration of…" or "A stylized object reference sheet showing…"). Avoid
      photographic vocabulary (studio shot, product photo, macro, depth of field,
      lighting rig); use illustration vocabulary instead (drawing, illustration,
      reference sheet, composition).
    - Do NOT include any art style, color palette, line work, rendering technique,
      or stylization instructions in `reference_prompt` — visual style is injected
      separately at image-generation time.
    - USER-PHOTO ANCHOR — when `has_user_photo` is true, the user has uploaded a
      reference photograph of this object. That photo is the AUTHORITATIVE,
      NON-OVERRIDABLE source of the object's appearance. You MUST NOT alter, in
      `description` or in any other field you produce, the traits a photograph
      encodes: overall shape, proportions, silhouette, distinctive structural
      details, key markings and any feature that lets the reader recognise it
      as the SAME object. You MAY refine narrative role, recurrence across the
      story and any non-photographic aspect. If `user_feedback` explicitly
      asks for a change that would contradict the photo (e.g. "different
      shape", "round it off", "remove the logo"), IGNORE that specific part
      of the feedback and keep the photo-anchored traits unchanged — the
      user-supplied photo always wins over conflicting text feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, mascot or copyrighted character
      in any field. If the feedback invokes such a name, translate it into precise
      visual descriptors (shape, markings, palette, materials) and use those
      descriptors instead. This rule applies even when the user has lifted the
      copyright safeguard — emulate the LOOK, never the LABEL.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


COVER_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising the FRONT COVER specification of an in-progress comic
    book script.

    The user has supplied a feedback note. Apply it to the cover record below
    and return the updated `Cover` object as JSON. The user message includes
    a `photo_pinned_entities` map listing the character and object ids for
    which the user has uploaded reference photographs.

    Fields:
    - `scene_description`: evocative illustration concept for the front cover
    - `title_placement`: hint for where and how the title is laid out
    - `subtitle`: optional subtitle or null
    - `tagline`: optional short marketing tagline or null

    HARD CONSTRAINTS:
    - Write content in the language specified by `metadata.language`.
    - USER-PHOTO ANCHOR — for every character id in
      `photo_pinned_entities.characters` and every object id in
      `photo_pinned_entities.objects`, the user has supplied an authoritative
      reference photograph. Your `scene_description` MUST stay compatible with
      those photos: do NOT describe physical traits (face, build, age, hair,
      structure, shape, markings) that would contradict the photographic
      likeness, and do NOT propose changes that would override what the photo
      anchors. You may freely re-stage composition, pose, mood, lighting and
      framing. If `user_feedback` explicitly asks for a change that would
      contradict a photo-pinned entity, IGNORE that specific part and keep
      the photo-anchored traits unchanged — the user-supplied photo always
      wins over conflicting text feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, mascot or copyrighted character
      in any field. If the feedback invokes such a name, translate it into precise
      visual descriptors and use those descriptors instead. This rule applies even
      when the user has lifted the copyright safeguard — emulate the LOOK, never
      the LABEL.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


BACK_COVER_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising the BACK COVER specification of an in-progress comic
    book script.

    The user has supplied a feedback note. Apply it to the back cover record
    below and return the updated `BackCover` object as JSON. The user
    message includes a `photo_pinned_entities` map listing the character and
    object ids for which the user has uploaded reference photographs.

    Fields:
    - `synopsis_blurb`: 3-5 sentence marketing-tone presentation of the story
      WITHOUT spoilers, ending on a hook
    - `scene_description`: optional small illustration concept, or null
    - `tagline`: optional short tagline or null
    - `layout_notes`: optional layout hints (e.g. "barcode bottom-right corner")

    HARD CONSTRAINTS:
    - Write content in the language specified by `metadata.language`.
    - USER-PHOTO ANCHOR — for every character/object id listed in
      `photo_pinned_entities`, the user has supplied an authoritative
      reference photograph. Your `scene_description` and `synopsis_blurb`
      MUST stay compatible with those photos: do NOT describe physical traits
      that would contradict the photographic likeness, and do NOT propose
      changes that would override what the photo anchors. If `user_feedback`
      explicitly asks for a change that would contradict a photo-pinned
      entity, IGNORE that specific part and keep the photo-anchored traits
      unchanged — the user-supplied photo always wins over conflicting text
      feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, mascot or copyrighted character
      in any field. If the feedback invokes such a name, translate it into precise
      visual descriptors and use those descriptors instead. This rule applies even
      when the user has lifted the copyright safeguard — emulate the LOOK, never
      the LABEL.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


PAGE_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single page of an in-progress comic book script.

    The user has supplied a feedback note. Apply it to the page below and
    return the updated `Page` JSON object keeping the same `page_number`. You
    must stay consistent with the project brief, the setup, prior pages, and
    later pages (all provided in the user message).

    HARD CONSTRAINTS:
    - Keep `page_number` unchanged.
    - Use ONLY character ids and location ids defined in the setup.
    - Honor `structure.panels_per_page_avg` and `structure.panels_per_page_range`.
    - The page's `layout` description MUST exactly match the number of panels.
    - Write narrative content in the language specified by `metadata.language`.
    - Keep dialog lines short.
    - USER-PHOTO ANCHOR — the user message includes a `photo_pinned_entities`
      map listing the character / location / object ids for which the user has
      uploaded reference photographs. Those photographs are AUTHORITATIVE for
      the entity's physical likeness. In `scene_description`, `narration` and
      `dialogs`, NEVER describe physical traits (face, build, age, hair,
      structure for characters; architecture, layout for locations; shape,
      markings, silhouette for objects) that would contradict what the photo
      anchors, and NEVER propose narrative actions that would visibly alter
      photo-anchored traits ("he ages 30 years", "the building collapses
      into a different shape"). You MAY freely change pose, action, mood,
      lighting, framing and clothing accessories. If `user_feedback`
      explicitly asks for a change that would contradict a photo-pinned
      entity, IGNORE that specific part of the feedback and keep the
      photo-anchored traits unchanged — the user-supplied photo always wins
      over conflicting text feedback.
    - DESCRIBE, NEVER NAME — never reference a real-world artist, illustrator,
      studio, publisher, franchise, series, brand, mascot or copyrighted character
      in any panel content. If the feedback invokes such a name, translate it
      into precise visual descriptors (silhouette, costume, palette, motif) and
      use those descriptors instead. This rule applies even when the user has
      lifted the copyright safeguard — emulate the LOOK, never the LABEL.
    - Output ONLY the JSON object for this page. No markdown fences, no commentary.
    """)


_STRIP_LAYOUT_CONSTRAINT = dedent("""\

    STRIP FORMAT — NON-NEGOTIABLE:
    This project uses the newspaper/comic-strip format. Every planche is ONE
    single unbroken horizontal row of panels on a landscape canvas.
    - ABSOLUTELY FORBIDDEN: stacking rows, 2-row grids, 3-row grids, L-shapes,
      panels placed above or below other panels, or any arrangement where panels
      are not all on the same horizontal line.
    - The `layout` field MUST be exactly: "single horizontal row of <N> panels"
      (substitute <N> with the actual panel count). Any wording that implies
      multiple rows, a grid, or vertical stacking is rejected.
    - Every panel shares the SAME HEIGHT — the full vertical extent of the strip.
      You MUST NOT vary panel heights.
    - You MAY vary panel WIDTHS (wider for wide action shots, narrower for
      reaction close-ups); the total of all panel widths fills the full canvas.
    - The "Vary panel sizes" rule does NOT apply here; ignore it entirely.
    """)


def _page_system_prompt(page_format: str) -> str:
    base = PAGE_SYSTEM_PROMPT
    if page_format == "strip":
        base = base.replace(
            "- Vary panel sizes and camera shots for visual rhythm.",
            "- Vary panel WIDTHS only for visual rhythm; all panels MUST share the exact same HEIGHT.",
        )
        base = base.rstrip("\n") + _STRIP_LAYOUT_CONSTRAINT
    return base


def _page_refine_system_prompt(page_format: str) -> str:
    base = PAGE_REFINE_SYSTEM_PROMPT
    if page_format == "strip":
        base = base.rstrip("\n") + _STRIP_LAYOUT_CONSTRAINT
    return base


# --- Top-level orchestration ---


def generate_script(
    config: BdGenInput,
    input_path: Path,
    feedback: list[str] | None = None,
    preview_pages: int | None = None,
    script_path: Path | None = None,
    reporter: ProgressReporter | None = None,
    interrupt: InterruptFlag | None = None,
    stats_project_dir: Path | None = None,
) -> BdGenScript:
    """Generate the script in two phases: setup + per-page expansion.

    Page-by-page generation gives two key benefits:
    - Smaller responses per call → less risk of truncation / parse errors
    - On error, the work done so far is persisted to disk; rerunning resumes
      from where the failure happened instead of redoing everything

    When ``script_path`` is provided, the script is saved after each successful
    page so the next invocation can pick up where this one left off.

    ``reporter`` receives structured progress events; ``interrupt`` is checked
    between pages so generation can stop cleanly without losing prior work.
    """
    rep = _coerce_reporter(reporter)
    flag = _coerce_flag(interrupt)
    model_cfg = config.generation_options.script_model
    target_pages = (
        preview_pages
        if preview_pages is not None and preview_pages < config.structure.page_count
        else config.structure.page_count
    )
    label = f"{model_cfg.provider}/{model_cfg.model}"

    with (
        trace.project_session(stats_project_dir),
        trace.node(
            "generate_script",
            "flow",
            inputs={
                "project": config.project,
                "target_pages": target_pages,
                "preview_pages": preview_pages,
                "provider": model_cfg.provider,
                "model": model_cfg.model,
                "has_feedback": bool(feedback),
            },
        ),
    ):
        return _generate_script_impl(
            config,
            input_path,
            feedback,
            preview_pages,
            target_pages,
            script_path,
            rep,
            flag,
            model_cfg,
            label,
            stats_project_dir,
        )


def _generate_script_impl(
    config: BdGenInput,
    input_path: Path,
    feedback: list[str] | None,
    preview_pages: int | None,
    target_pages: int,
    script_path: Path | None,
    rep: ProgressReporter,
    flag: InterruptFlag,
    model_cfg: ScriptModelConfig,
    label: str,
    stats_project_dir: Path | None,
) -> BdGenScript:
    bd_script = _try_resume(script_path, config, target_pages, rep)

    if bd_script is None:
        rep.emit(
            ProgressEvent(
                step="script",
                phase="setup",
                message=f"Setup phase: characters, locations, cover, back cover ({label})…",
            )
        )
        flag.check()
        setup_result = _call_llm(
            SETUP_SYSTEM_PROMPT,
            _build_setup_prompt(config, feedback, preview_pages, target_pages),
            model_cfg,
            _LLMSetupDraft,
            trace_name="call_llm:setup",
        )
        setup = setup_result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id="setup",
            target_kind="setup",
            operation="generate_script_setup",
            model_config=model_cfg,
            result=setup_result,
        )
        bd_script = _build_skeleton(config, setup, input_path, label)
        if script_path:
            bd_script.save(script_path)
        rep.emit(
            ProgressEvent(
                step="script",
                phase="setup_done",
                message=(
                    f"Setup terminé : {len(bd_script.characters)} personnages, {len(bd_script.locations)} décors."
                ),
                extra={
                    "characters": len(bd_script.characters),
                    "locations": len(bd_script.locations),
                },
            )
        )

    for page_n in range(len(bd_script.pages) + 1, target_pages + 1):
        flag.check()
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"page_{page_n}",
                message=f"Génération de la planche {page_n}/{target_pages} ({label})…",
                current=page_n,
                total=target_pages,
            )
        )
        page_result = _call_llm(
            _page_system_prompt(config.structure.page_format),
            _build_page_prompt(config, bd_script, page_n, target_pages, feedback, preview_pages),
            model_cfg,
            Page,
            trace_name=f"call_llm:page_{page_n}",
        )
        page_draft = page_result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id=f"page_{page_n}",
            target_kind="page",
            operation="generate_script_page",
            model_config=model_cfg,
            result=page_result,
        )
        # Force the page_number we asked for, in case the model deviates.
        page = Page(
            page_number=page_n,
            layout=page_draft.layout,
            panels=page_draft.panels,
        )
        bd_script.pages.append(page)
        if script_path:
            bd_script.save(script_path)
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"page_{page_n}_done",
                message=f"Planche {page_n} écrite.",
                current=page_n,
                total=target_pages,
            )
        )

    rep.emit(
        ProgressEvent(
            step="script",
            phase="done",
            message=(
                f"Scénario complet : {len(bd_script.characters)} personnages, "
                f"{len(bd_script.locations)} décors, {len(bd_script.pages)} planches, "
                f"{sum(len(p.panels) for p in bd_script.pages)} cases."
            ),
        )
    )
    return bd_script


def _try_resume(
    script_path: Path | None,
    config: BdGenInput,
    target_pages: int,
    reporter: ProgressReporter,
) -> BdGenScript | None:
    """Return an existing script if it can be resumed/used as-is, else None."""
    if script_path is None or not script_path.exists():
        return None
    try:
        existing = BdGenScript.load(script_path)
    except Exception as e:
        reporter.emit(
            ProgressEvent(
                step="script",
                phase="resume_failed",
                message=f"Script existant illisible ({e}) ; regénération complète.",
            )
        )
        return None
    if existing.project != config.project or not existing.characters:
        return None
    if len(existing.pages) >= target_pages:
        reporter.emit(
            ProgressEvent(
                step="script",
                phase="already_complete",
                message=(f"Scénario déjà complet sur disque ({len(existing.pages)} planches)."),
                current=len(existing.pages),
                total=target_pages,
            )
        )
        return existing
    reporter.emit(
        ProgressEvent(
            step="script",
            phase="resuming",
            message=(f"Reprise : {len(existing.pages)}/{target_pages} planches déjà écrites."),
            current=len(existing.pages),
            total=target_pages,
        )
    )
    return existing


def _build_skeleton(config: BdGenInput, setup: _LLMSetupDraft, input_path: Path, model_label: str) -> BdGenScript:
    source = ScriptSource(
        input_file=str(input_path),
        generated_at=datetime.now(timezone.utc).isoformat(),
        script_model=model_label,
    )
    return BdGenScript(
        project=config.project,
        display_name=config.display_name,
        source=source,
        metadata=config.metadata,
        style=config.style,
        page_format=config.structure.page_format,
        allow_style_copy=config.allow_style_copy,
        generation_options=config.generation_options,
        characters=[ScriptCharacter(**c.model_dump(), reference_image=None) for c in setup.characters],
        locations=[ScriptLocation(**l.model_dump(), reference_image=None) for l in setup.locations],
        objects=[ScriptObject(**o.model_dump(), reference_image=None) for o in setup.objects],
        cover=setup.cover,
        back_cover=setup.back_cover,
        pages=[],
    )


# --- Prompt builders ---


def _build_setup_prompt(
    config: BdGenInput,
    feedback: list[str] | None,
    preview_pages: int | None,
    target_pages: int,
) -> str:
    brief = config.model_dump(mode="json", exclude={"generation_options"})
    preview_note = ""
    if preview_pages is not None and preview_pages < config.structure.page_count:
        preview_note = (
            f"\n\nPREVIEW MODE — workflow test. The full story is "
            f"{config.structure.page_count} pages but only the first {preview_pages} "
            f"will be expanded. Cover and back cover should still describe the full "
            f"{config.structure.page_count}-page story (they market the whole album)."
        )

    n_chars = len(config.characters)
    n_locs = len(config.locations)
    n_objs = len(config.objects)
    if config.structure.allow_extra_characters:
        char_rule = (
            f"You MAY invent additional supporting characters if the story arc "
            f"genuinely needs them. Always copy the {n_chars} input character(s) "
            f"verbatim first."
        )
    else:
        char_rule = (
            f"STRICT: Use ONLY the {n_chars} input character(s). Do NOT invent "
            f"any additional character — even minor or background figures. If a "
            f"crowd is needed, evoke it without naming or detailing anyone."
        )
    if config.structure.allow_extra_locations:
        if n_locs > 0:
            loc_rule = (
                f"You MAY invent additional locations needed by the story arc. "
                f"Always copy the {n_locs} input location(s) verbatim first."
            )
        else:
            loc_rule = "Invent every location your story will need across the FULL story arc (the input has none)."
    else:
        loc_rule = f"STRICT: Use ONLY the {n_locs} input location(s). Do NOT invent any new location."
    if n_objs == 0 and config.structure.allow_extra_objects:
        obj_rule = (
            "The user provided no objects. Do NOT invent any: leave the `objects` "
            "array empty unless the brief explicitly requires a recurring object."
        )
    elif n_objs == 0:
        obj_rule = "STRICT: The user provided no objects and disallowed inventing any. Leave the `objects` array empty."
    elif config.structure.allow_extra_objects:
        obj_rule = (
            f"You MAY add a small number of additional objects if a recurring "
            f"prop genuinely needs to be tracked. Always copy the {n_objs} input "
            f"object(s) verbatim first; weave them prominently into the story."
        )
    else:
        obj_rule = (
            f"STRICT: Use ONLY the {n_objs} input object(s). Do NOT invent any "
            f"new object. Weave each input object prominently into the story."
        )
    authoring_rules = (
        "\n\nAUTHORING RULES — APPLY STRICTLY:\n"
        f"- Characters: {char_rule}\n"
        f"- Locations: {loc_rule}\n"
        f"- Objects: {obj_rule}\n"
    )

    base = (
        "Here is the project brief. Generate the SETUP only (characters, locations, "
        "objects, cover, back cover). Pages will be requested separately, one at a "
        "time.\n\n" + json.dumps(brief, ensure_ascii=False, indent=2) + preview_note + authoring_rules
    )
    if feedback:
        base += feedback_block(feedback)
    return base


def _build_page_prompt(
    config: BdGenInput,
    bd_script: BdGenScript,
    page_n: int,
    target_pages: int,
    feedback: list[str] | None,
    preview_pages: int | None,
) -> str:
    brief = config.model_dump(mode="json", exclude={"generation_options"})
    setup = {
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "physical_description": c.physical_description,
                "outfit": c.outfit,
            }
            for c in bd_script.characters
        ],
        "locations": [{"id": l.id, "name": l.name, "description": l.description} for l in bd_script.locations],
        "objects": [{"id": o.id, "name": o.name, "description": o.description} for o in bd_script.objects],
    }
    prior_pages = [p.model_dump(mode="json") for p in bd_script.pages]

    preview_note = ""
    if preview_pages is not None and preview_pages < config.structure.page_count:
        is_last_preview_page = page_n == preview_pages
        preview_note = (
            f"\n\nPREVIEW MODE: only the first {preview_pages} pages of a "
            f"{config.structure.page_count}-page story will be expanded. "
        )
        if is_last_preview_page:
            preview_note += (
                "This is the LAST preview page — end on a natural beat, do NOT artificially wrap up the full arc."
            )

    parts = [
        "PROJECT BRIEF:",
        json.dumps(brief, ensure_ascii=False, indent=2),
        "",
        "SETUP (already generated — use these character, location and object ids verbatim):",
        json.dumps(setup, ensure_ascii=False, indent=2),
        "",
    ]
    if prior_pages:
        parts.extend(
            [
                "PREVIOUSLY GENERATED PAGES (for narrative continuity, DO NOT regenerate):",
                json.dumps(prior_pages, ensure_ascii=False, indent=2),
                "",
            ]
        )
    else:
        parts.append("(No previous pages — this is page 1.)")
        parts.append("")
    parts.append(f"Now generate page {page_n} of {target_pages} as a single JSON Page object." + preview_note)

    base = "\n".join(parts)
    if feedback:
        base += feedback_block(feedback)
    return base


# --- LLM dispatch with retries ---


def _call_llm(
    system: str,
    user: str,
    model_config: ScriptModelConfig,
    output_type: type[T],
    trace_name: str = "call_llm",
) -> _LLMCallResult:
    """Dispatch to the configured provider, with bounded retries on parse failure.

    Per-call retries (rather than per-script) mean a single page failure only
    re-runs that page, not the whole script.
    """
    last_error: RuntimeError | None = None
    started_at, started = start_timer()
    with trace.node(trace_name, "llm_call") as tn:
        tn.set_model(model_config.provider, model_config.model)
        tn.set_prompt(user)
        tn.set_extra(system_prompt=system, output_type=output_type.__name__)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                if model_config.provider == "openai":
                    value, usage = _call_openai(system, user, model_config, output_type)
                    timer = stop_timer(started_at, started)
                    tn.set_usage(usage)
                    tn.set_outputs({"value_type": type(value).__name__, "attempts": attempt})
                    return _LLMCallResult(value, usage, timer.elapsed_seconds, timer.started_at)
                if model_config.provider == "xai":
                    value, usage = _call_xai(system, user, model_config, output_type)
                    timer = stop_timer(started_at, started)
                    tn.set_usage(usage)
                    tn.set_outputs({"value_type": type(value).__name__, "attempts": attempt})
                    return _LLMCallResult(value, usage, timer.elapsed_seconds, timer.started_at)
                if model_config.provider == "anthropic":
                    value, usage = _call_anthropic(system, user, model_config, output_type)
                    timer = stop_timer(started_at, started)
                    tn.set_usage(usage)
                    tn.set_outputs({"value_type": type(value).__name__, "attempts": attempt})
                    return _LLMCallResult(value, usage, timer.elapsed_seconds, timer.started_at)
                raise NotImplementedError(f"Provider '{model_config.provider}' is not yet supported.")
            except _RetryableRateLimit as e:
                last_error = e
                short_reason = str(e).split("\n", 1)[0]
                if attempt < MAX_ATTEMPTS:
                    wait = e.retry_after_seconds
                    if wait is None:
                        wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    wait = max(1.0, float(wait))
                    print(
                        f"  Claude rate limit on attempt {attempt}/{MAX_ATTEMPTS}: {short_reason}\n"
                        f"  Waiting {wait:.0f}s before retry..."
                    )
                    time.sleep(wait)
                else:
                    print(f"  All {MAX_ATTEMPTS} attempts failed.")
                    raise
            except RuntimeError as e:
                last_error = e
                short_reason = str(e).split("\n", 1)[0]
                if attempt < MAX_ATTEMPTS:
                    wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    print(f"  Attempt {attempt}/{MAX_ATTEMPTS} failed: {short_reason}\n  Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  All {MAX_ATTEMPTS} attempts failed.")
                    raise

        assert last_error is not None
        raise last_error


def _call_openai(system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]) -> tuple[T, dict]:
    """OpenAI Chat Completions with structured Pydantic output."""
    client = secret_store.openai_client()
    kwargs = {
        "model": model_config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": output_type,
    }
    try:
        completion = client.chat.completions.parse(temperature=model_config.temperature, **kwargs)
    except Exception as e:
        if "temperature" not in str(e).lower():
            raise
        completion = client.chat.completions.parse(**kwargs)

    message = completion.choices[0].message
    if message.parsed is None:
        raise RuntimeError(f"LLM returned no parsed content. Refusal: {message.refusal}")
    return message.parsed, normalise_usage(getattr(completion, "usage", None))


def _call_xai(system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]) -> tuple[T, dict]:
    """xAI Grok through its OpenAI-compatible Chat Completions endpoint."""
    client = secret_store.xai_client()
    kwargs = {
        "model": model_config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": output_type,
    }
    try:
        completion = client.chat.completions.parse(temperature=model_config.temperature, **kwargs)
    except Exception as e:
        if "temperature" not in str(e).lower():
            raise
        completion = client.chat.completions.parse(**kwargs)

    message = completion.choices[0].message
    if message.parsed is None:
        raise RuntimeError(f"Grok returned no parsed content. Refusal: {message.refusal}")
    return message.parsed, normalise_usage(getattr(completion, "usage", None))


def _call_anthropic(system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]) -> tuple[T, dict]:
    """Anthropic Messages API in streaming mode + manual JSON parsing.

    The system prompt is cached (5-minute TTL) so successive calls (setup +
    pages, or retries) pay only ~0.1x for the system block on cache hits.
    """
    client = secret_store.anthropic_client()
    text_parts: list[str] = []
    state = {"phase": None, "phase_start": 0.0, "chars": 0, "last_render": 0.0}

    def render(force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - state["last_render"] < 0.1:
            return
        state["last_render"] = now
        elapsed = int(now - state["phase_start"])
        if state["phase"] == "thinking":
            sys.stdout.write(f"\r  [thinking] {elapsed}s elapsed       ")
        elif state["phase"] == "writing":
            sys.stdout.write(f"\r  [writing JSON] {state['chars']} chars, {elapsed}s elapsed   ")
        sys.stdout.flush()

    def commit_line() -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()

    def start_phase(phase: str) -> None:
        if state["phase"] is not None:
            render(force=True)
            commit_line()
        state["phase"] = phase
        state["phase_start"] = time.monotonic()
        state["chars"] = 0
        state["last_render"] = 0.0
        render(force=True)

    extra_kwargs: dict = {}
    if _anthropic_supports_adaptive_thinking(model_config.model):
        extra_kwargs["thinking"] = {"type": "adaptive"}
        extra_kwargs["output_config"] = {"effort": _anthropic_effort(model_config.effort)}

    _wait_for_anthropic_input_budget(system, user)
    stream_client = client.with_options(timeout=_anthropic_timeout_seconds())
    try:
        with stream_client.messages.stream(
            model=model_config.model,
            max_tokens=_anthropic_max_tokens(output_type),
            **extra_kwargs,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    bt = event.content_block.type
                    if bt == "thinking":
                        start_phase("thinking")
                    elif bt == "text":
                        start_phase("writing")
                elif event.type == "content_block_delta":
                    dt = event.delta.type
                    if dt == "thinking_delta":
                        if event.delta.thinking:
                            state["chars"] += len(event.delta.thinking)
                        render()
                    elif dt == "text_delta":
                        text_parts.append(event.delta.text)
                        state["chars"] += len(event.delta.text)
                        render()
                elif event.type == "message_stop":
                    if state["phase"] is not None:
                        render(force=True)
                        commit_line()
                        state["phase"] = None

            final = stream.get_final_message()
    except Exception as exc:
        if _is_anthropic_rate_limit(exc):
            raise _RetryableRateLimit(str(exc), _retry_after_seconds(exc)) from exc
        raise

    usage_payload = normalise_usage(final.usage)
    if final.usage:
        u = final.usage
        cache_read = u.cache_read_input_tokens or 0
        cache_write = u.cache_creation_input_tokens or 0
        cached_note = f", cache hit: {cache_read}" if cache_read else ""
        if cache_write and not cache_read:
            cached_note = f", cache write: {cache_write}"
        print(f"  Tokens: input={u.input_tokens + cache_read + cache_write}{cached_note}, output={u.output_tokens}")

    raw = "".join(text_parts)
    if not raw.strip():
        raise RuntimeError("Claude returned no text content (only thinking blocks?).")
    json_text = _strip_json_fences(raw)
    try:
        return output_type.model_validate_json(json_text), usage_payload
    except Exception as e:
        unwrapped = _try_unwrap_echoed_input(json_text, output_type)
        if unwrapped is not None:
            return unwrapped, usage_payload
        raise RuntimeError(
            f"Failed to parse Claude response as {output_type.__name__}: {e}\nRaw text (first 800 chars): {raw[:800]}"
        )


def _record_llm_stats(
    project_dir: Path | None,
    *,
    step: str,
    target_id: str,
    target_kind: str,
    operation: str,
    model_config: ScriptModelConfig,
    result: _LLMCallResult,
) -> None:
    record_event(
        project_dir,
        step=step,
        target_id=target_id,
        target_kind=target_kind,
        operation=operation,
        provider=model_config.provider,
        model=model_config.model,
        timer=TimedCall(result.started_at, result.elapsed_seconds),
        usage=result.usage,
    )


def _anthropic_input_tokens_per_minute() -> int:
    raw = os.environ.get("BDGEN_ANTHROPIC_INPUT_TOKENS_PER_MINUTE")
    if raw is None:
        return ANTHROPIC_DEFAULT_INPUT_TOKENS_PER_MINUTE
    try:
        return max(0, int(raw))
    except ValueError:
        return ANTHROPIC_DEFAULT_INPUT_TOKENS_PER_MINUTE


def _anthropic_timeout_seconds() -> float:
    raw = os.environ.get("BDGEN_ANTHROPIC_TIMEOUT_SECONDS")
    if raw is None:
        return float(ANTHROPIC_DEFAULT_TIMEOUT_SECONDS)
    try:
        return max(60.0, float(raw))
    except ValueError:
        return float(ANTHROPIC_DEFAULT_TIMEOUT_SECONDS)


def _anthropic_effort(configured: str | None = None) -> str:
    raw = (configured or os.environ.get("BDGEN_ANTHROPIC_EFFORT", ANTHROPIC_DEFAULT_EFFORT)).strip().lower()
    if raw in ANTHROPIC_EFFORT_LEVELS:
        return raw
    return ANTHROPIC_DEFAULT_EFFORT


def _anthropic_supports_adaptive_thinking(model: str) -> bool:
    return model.startswith(
        (
            "claude-mythos-preview",
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
        )
    )


def _estimate_anthropic_input_tokens(system: str, user: str) -> int:
    chars = len(system) + len(user)
    estimate = chars // ANTHROPIC_TOKEN_ESTIMATE_CHARS_PER_TOKEN
    return max(1, estimate + ANTHROPIC_TOKEN_ESTIMATE_SAFETY_TOKENS)


def _wait_for_anthropic_input_budget(system: str, user: str) -> None:
    limit = _anthropic_input_tokens_per_minute()
    if limit <= 0:
        return
    estimate = _estimate_anthropic_input_tokens(system, user)
    cost = min(float(estimate), float(limit))
    rate_per_second = float(limit) / 60.0
    with _ANTHROPIC_THROTTLE_LOCK:
        now = time.monotonic()
        last = float(_ANTHROPIC_THROTTLE_STATE["last"])
        available = min(
            float(limit),
            float(_ANTHROPIC_THROTTLE_STATE["tokens"]) + max(0.0, now - last) * rate_per_second,
        )
        missing = cost - available
        if missing <= 0:
            _ANTHROPIC_THROTTLE_STATE["tokens"] = available - cost
            _ANTHROPIC_THROTTLE_STATE["last"] = now
            return
        wait = missing / rate_per_second
        _ANTHROPIC_THROTTLE_STATE["tokens"] = 0.0
        _ANTHROPIC_THROTTLE_STATE["last"] = now + wait
    print(f"  Claude throttle: estimated input={estimate} tokens, waiting {wait:.0f}s to stay under {limit}/min...")
    time.sleep(wait)


def _anthropic_max_tokens(output_type: type[BaseModel]) -> int:
    # Anthropic pre-reserves output-token capacity from max_tokens. These caps
    # keep the reservation close to BdGEN's expected JSON size without changing
    # the model, reasoning effort, or requested content quality.
    if output_type is _LLMSetupDraft:
        return 16_000
    if output_type is Page:
        return 8_000
    if output_type is _DraftCharacter:
        return 5_000
    if output_type in {_DraftLocation, _DraftObject, Cover, BackCover}:
        return 3_000
    return 8_000


def _is_anthropic_rate_limit(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    name = exc.__class__.__name__.lower()
    return "ratelimit" in name or "rate_limit" in str(exc).lower()


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = None
    try:
        raw = headers.get("retry-after")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return max(1.0, float(raw))
    except ValueError:
        return None


def _strip_json_fences(text: str) -> str:
    """Strip surrounding ```json fences if the model wrapped its output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _try_unwrap_echoed_input(json_text: str, output_type: type[BaseModel]) -> BaseModel | None:
    # Recovery path: refine prompts pass `{metadata, style, current_*, user_feedback}`
    # and the model sometimes echoes that wrapper back. Look for a payload nested
    # under a `current_*` or `updated_*` key that matches the target schema.
    try:
        data = json.loads(json_text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    candidate_keys = [
        k for k in data if k.startswith("current_") or k.startswith("updated_") or k in {"character", "location"}
    ]
    for key in candidate_keys:
        try:
            return output_type.model_validate(data[key])
        except Exception:
            continue
    return None


# --- Targeted regeneration (single character / location / page) ---


_USER_PHOTO_DIR_BY_KIND: dict[str, str] = {
    "character": "character_photos",
    "location": "location_photos",
    "object": "object_photos",
}


def _user_photo_exists(proj_dir: Path | None, kind: str, entity_id: str) -> bool:
    """True iff the user uploaded a reference photo for that entity.

    Checks both the new subdirectory format ({kind}_photos/{id}/*.png) and
    the legacy flat-file format ({kind}_photos/{id}.png).
    """
    if proj_dir is None:
        return False
    sub = _USER_PHOTO_DIR_BY_KIND.get(kind)
    if sub is None:
        return False
    # New format: subdirectory with numbered slots
    entity_dir = proj_dir / sub / entity_id
    if entity_dir.is_dir():
        for p in entity_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".png" and p.stat().st_size > 0:
                try:
                    int(p.stem)
                    return True
                except ValueError:
                    pass
    # Legacy flat format
    p = proj_dir / sub / f"{entity_id}.png"
    return p.exists() and p.stat().st_size > 0


def _photo_pinned_entities(
    proj_dir: Path | None,
    bd_script: BdGenScript,
) -> dict[str, list[str]]:
    """Return ``{"characters": [ids], "locations": [ids], "objects": [ids]}``
    listing every entity for which the user has supplied a reference photo.
    Refine prompts use this so the LLM knows which entities the user has
    anchored visually and must not contradict in any field it rewrites.
    """
    if proj_dir is None:
        return {"characters": [], "locations": [], "objects": []}
    return {
        "characters": [c.id for c in bd_script.characters if _user_photo_exists(proj_dir, "character", c.id)],
        "locations": [l.id for l in bd_script.locations if _user_photo_exists(proj_dir, "location", l.id)],
        "objects": [o.id for o in bd_script.objects if _user_photo_exists(proj_dir, "object", o.id)],
    }


def regenerate_character(
    bd_script: BdGenScript,
    character_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> ScriptCharacter:
    """Rewrite a single character via a focused LLM call. Returns the updated record."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    char = bd_script.character_by_id(character_id)
    if char is None:
        raise RuntimeError(f"Personnage inconnu : {character_id}")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            f"refine_character:{character_id}",
            "flow",
            inputs={"character_id": character_id, "feedback_chars": len(feedback_text)},
        ),
    ):
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_character_{character_id}",
                message=f"Retouche du personnage « {char.name} »…",
            )
        )
        user_prompt = json.dumps(
            {
                "metadata": bd_script.metadata.model_dump(mode="json"),
                "style": bd_script.style.model_dump(mode="json"),
                "current_character": char.model_dump(mode="json", exclude={"reference_image"}),
                "has_user_photo": _user_photo_exists(stats_project_dir, "character", character_id),
                "user_feedback": feedback_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = _call_llm(
            CHARACTER_REFINE_SYSTEM_PROMPT,
            user_prompt,
            bd_script.generation_options.script_model,
            _DraftCharacter,
        )
        draft = result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id=character_id,
            target_kind="character",
            operation="refine_character",
            model_config=bd_script.generation_options.script_model,
            result=result,
        )
        if draft.id != character_id:
            draft.id = character_id  # never let the model rename
        char.physical_description = draft.physical_description
        char.outfit = draft.outfit
        char.reference_prompt = draft.reference_prompt
        char.name = draft.name
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_character_{character_id}_done",
                message=f"Personnage « {char.name} » mis à jour.",
            )
        )
        return char


def regenerate_location(
    bd_script: BdGenScript,
    location_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> ScriptLocation:
    """Rewrite a single location via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    loc = bd_script.location_by_id(location_id)
    if loc is None:
        raise RuntimeError(f"Décor inconnu : {location_id}")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            f"refine_location:{location_id}",
            "flow",
            inputs={"location_id": location_id, "feedback_chars": len(feedback_text)},
        ),
    ):
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_location_{location_id}",
                message=f"Retouche du décor « {loc.name} »…",
            )
        )
        user_prompt = json.dumps(
            {
                "metadata": bd_script.metadata.model_dump(mode="json"),
                "style": bd_script.style.model_dump(mode="json"),
                "current_location": loc.model_dump(mode="json", exclude={"reference_image"}),
                "has_user_photo": _user_photo_exists(stats_project_dir, "location", location_id),
                "user_feedback": feedback_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = _call_llm(
            LOCATION_REFINE_SYSTEM_PROMPT,
            user_prompt,
            bd_script.generation_options.script_model,
            _DraftLocation,
        )
        draft = result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id=location_id,
            target_kind="location",
            operation="refine_location",
            model_config=bd_script.generation_options.script_model,
            result=result,
        )
        if draft.id != location_id:
            draft.id = location_id
        loc.name = draft.name
        loc.description = draft.description
        loc.reference_prompt = draft.reference_prompt
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_location_{location_id}_done",
                message=f"Décor « {loc.name} » mis à jour.",
            )
        )
        return loc


def regenerate_object(
    bd_script: BdGenScript,
    object_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> ScriptObject:
    """Rewrite a single object via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    obj = bd_script.object_by_id(object_id)
    if obj is None:
        raise RuntimeError(f"Objet inconnu : {object_id}")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            f"refine_object:{object_id}",
            "flow",
            inputs={"object_id": object_id, "feedback_chars": len(feedback_text)},
        ),
    ):
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_object_{object_id}",
                message=f"Retouche de l'objet « {obj.name} »…",
            )
        )
        user_prompt = json.dumps(
            {
                "metadata": bd_script.metadata.model_dump(mode="json"),
                "style": bd_script.style.model_dump(mode="json"),
                "current_object": obj.model_dump(mode="json", exclude={"reference_image"}),
                "has_user_photo": _user_photo_exists(stats_project_dir, "object", object_id),
                "user_feedback": feedback_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = _call_llm(
            OBJECT_REFINE_SYSTEM_PROMPT,
            user_prompt,
            bd_script.generation_options.script_model,
            _DraftObject,
        )
        draft = result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id=object_id,
            target_kind="object",
            operation="refine_object",
            model_config=bd_script.generation_options.script_model,
            result=result,
        )
        if draft.id != object_id:
            draft.id = object_id
        obj.name = draft.name
        obj.description = draft.description
        obj.reference_prompt = draft.reference_prompt
        rep.emit(
            ProgressEvent(
                step="script",
                phase=f"refine_object_{object_id}_done",
                message=f"Objet « {obj.name} » mis à jour.",
            )
        )
        return obj


def regenerate_page(
    bd_script: BdGenScript,
    page_number: int,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> Page:
    """Rewrite a single page via a focused LLM call. Surrounding pages stay untouched."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    idx = next(
        (i for i, p in enumerate(bd_script.pages) if p.page_number == page_number),
        None,
    )
    if idx is None:
        raise RuntimeError(f"Planche inconnue : {page_number}")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            f"refine_page:{page_number}",
            "flow",
            inputs={"page_number": page_number, "feedback_chars": len(feedback_text)},
        ),
    ):
        return _regenerate_page_impl(bd_script, page_number, feedback_text, rep, idx, stats_project_dir)


def _regenerate_page_impl(
    bd_script: BdGenScript,
    page_number: int,
    feedback_text: str,
    rep: ProgressReporter,
    idx: int,
    stats_project_dir: Path | None,
) -> Page:
    rep.emit(
        ProgressEvent(
            step="script",
            phase=f"refine_page_{page_number}",
            message=f"Retouche de la planche {page_number}…",
            current=page_number,
            total=len(bd_script.pages),
        )
    )
    setup = {
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "physical_description": c.physical_description,
                "outfit": c.outfit,
            }
            for c in bd_script.characters
        ],
        "locations": [{"id": l.id, "name": l.name, "description": l.description} for l in bd_script.locations],
        "objects": [{"id": o.id, "name": o.name, "description": o.description} for o in bd_script.objects],
    }
    prior = [p.model_dump(mode="json") for p in bd_script.pages[:idx]]
    later = [p.model_dump(mode="json") for p in bd_script.pages[idx + 1 :]]
    user_prompt = json.dumps(
        {
            "metadata": bd_script.metadata.model_dump(mode="json"),
            "style": bd_script.style.model_dump(mode="json"),
            "structure": {
                "page_count": len(bd_script.pages),
                "page_format": bd_script.page_format,
            },
            "setup": setup,
            "prior_pages": prior,
            "later_pages": later,
            "current_page": bd_script.pages[idx].model_dump(mode="json"),
            "photo_pinned_entities": _photo_pinned_entities(stats_project_dir, bd_script),
            "user_feedback": feedback_text,
            "instruction": (
                f"Rewrite ONLY page {page_number} (keep page_number={page_number}). "
                f"Preserve continuity with prior_pages AND later_pages."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
    result = _call_llm(
        _page_refine_system_prompt(bd_script.page_format),
        user_prompt,
        bd_script.generation_options.script_model,
        Page,
    )
    draft = result.value
    _record_llm_stats(
        stats_project_dir,
        step="script",
        target_id=f"page_{page_number}",
        target_kind="page",
        operation="refine_page",
        model_config=bd_script.generation_options.script_model,
        result=result,
    )
    new_page = Page(
        page_number=page_number,
        layout=draft.layout,
        panels=draft.panels,
    )
    bd_script.pages[idx] = new_page
    rep.emit(
        ProgressEvent(
            step="script",
            phase=f"refine_page_{page_number}_done",
            message=f"Planche {page_number} mise à jour.",
            current=page_number,
            total=len(bd_script.pages),
        )
    )
    return new_page


def regenerate_cover(
    bd_script: BdGenScript,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> Cover:
    """Rewrite the front-cover record via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    if bd_script.cover is None:
        raise RuntimeError("Ce projet n'a pas de couverture à retoucher.")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            "refine_cover",
            "flow",
            inputs={"feedback_chars": len(feedback_text)},
        ),
    ):
        rep.emit(
            ProgressEvent(
                step="script",
                phase="refine_cover",
                message="Retouche de la couverture…",
            )
        )
        user_prompt = json.dumps(
            {
                "metadata": bd_script.metadata.model_dump(mode="json"),
                "style": bd_script.style.model_dump(mode="json"),
                "current_cover": bd_script.cover.model_dump(mode="json"),
                "photo_pinned_entities": _photo_pinned_entities(stats_project_dir, bd_script),
                "user_feedback": feedback_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = _call_llm(
            COVER_REFINE_SYSTEM_PROMPT,
            user_prompt,
            bd_script.generation_options.script_model,
            Cover,
        )
        draft = result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id="cover",
            target_kind="cover",
            operation="refine_cover",
            model_config=bd_script.generation_options.script_model,
            result=result,
        )
        bd_script.cover = draft
        rep.emit(
            ProgressEvent(
                step="script",
                phase="refine_cover_done",
                message="Couverture mise à jour.",
            )
        )
        return draft


def regenerate_back_cover(
    bd_script: BdGenScript,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
    stats_project_dir: Path | None = None,
) -> BackCover:
    """Rewrite the back-cover record via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    if bd_script.back_cover is None:
        raise RuntimeError("Ce projet n'a pas de 4ᵉ de couverture à retoucher.")
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            "refine_back_cover",
            "flow",
            inputs={"feedback_chars": len(feedback_text)},
        ),
    ):
        rep.emit(
            ProgressEvent(
                step="script",
                phase="refine_back_cover",
                message="Retouche de la 4ᵉ de couverture…",
            )
        )
        user_prompt = json.dumps(
            {
                "metadata": bd_script.metadata.model_dump(mode="json"),
                "style": bd_script.style.model_dump(mode="json"),
                "current_back_cover": bd_script.back_cover.model_dump(mode="json"),
                "photo_pinned_entities": _photo_pinned_entities(stats_project_dir, bd_script),
                "user_feedback": feedback_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        result = _call_llm(
            BACK_COVER_REFINE_SYSTEM_PROMPT,
            user_prompt,
            bd_script.generation_options.script_model,
            BackCover,
        )
        draft = result.value
        _record_llm_stats(
            stats_project_dir,
            step="script",
            target_id="back",
            target_kind="back_cover",
            operation="refine_back_cover",
            model_config=bd_script.generation_options.script_model,
            result=result,
        )
        bd_script.back_cover = draft
        rep.emit(
            ProgressEvent(
                step="script",
                phase="refine_back_cover_done",
                message="4ᵉ de couverture mise à jour.",
            )
        )
        return draft


def truncate_pages_from(bd_script: BdGenScript, page_number: int) -> int:
    """Drop pages numbered >= page_number. Returns the count removed.

    Useful when a substantial change to a page (or its predecessors) demands
    that the rest of the story be regenerated for consistency. After calling
    this, ``generate_script`` will resume from the truncation point.
    """
    keep = [p for p in bd_script.pages if p.page_number < page_number]
    removed = len(bd_script.pages) - len(keep)
    bd_script.pages = keep
    return removed
