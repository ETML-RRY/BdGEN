"""Step 1: generate the script in two phases (setup + per-page) with bounded retries."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
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
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)

MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE_SECONDS = 2

T = TypeVar("T", bound=BaseModel)


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
       body front, and an expressions sheet. The prompt MUST quote the project's
       full global style: `style.art_style`, `style.line_work`, `style.color_palette`
       and — CRITICALLY — `style.character_rendering` verbatim (face geometry, eye/
       nose/mouth treatment, body proportions, hands, hair, skin shading). If
       `style.stylization_level` is set, quote it verbatim — it tells the image
       generator HOW FAR from realism to push (e.g. "extremely abstract — characters
       are amorphous ink blobs"). If `style.negative_constraints` is set, include
       it as a "DO NOT …" instruction. It must also describe the character's full
       appearance and outfit, and MUST end with "No text. No speech bubbles." Whether
       you may invent ADDITIONAL characters is decided by the AUTHORING RULES at the
       end of the user message.

    2. LOCATIONS — first, for EACH entry in the input `locations` array (which may be
       empty), copy `id`, `name`, and `description` verbatim. ADD `reference_prompt`:
       an English image-generation prompt for an establishing shot, no characters, no
       text. The prompt MUST quote the project's `style.art_style`,
       `style.color_palette`, `style.line_work`, and if set `style.stylization_level`
       and `style.negative_constraints` verbatim so the location matches the album's
       visual identity, and end with "No text. No characters." Whether you may invent
       ADDITIONAL locations is decided by the AUTHORING RULES at the end of the user
       message.

    3. OBJECTS — first, for EACH entry in the input `objects` array (which may be
       empty), copy `id`, `name`, and `description` verbatim. ADD `reference_prompt`:
       an English image-generation prompt for an isolated object reference rendered
       as a stylized caricature in the project's art style, on a neutral background,
       no characters, no text. The prompt MUST quote `style.art_style`,
       `style.color_palette`, `style.line_work`, and if set `style.stylization_level`
       and `style.negative_constraints` verbatim, and end with "No text.
       No characters." If the user provided a photo of this object (passed at image-
       generation time), the resulting illustration must remain recognizably the
       SAME object — same shape, key markings, characteristic silhouette — but
       rendered ENTIRELY in the project's art style (never as a photograph). Plan
       how each object will recur across the story so panels can reference it
       consistently. Whether you may invent ADDITIONAL objects is decided by the
       AUTHORING RULES at the end of the user message.

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
    - NEVER include the proper name of any real-world artist, illustrator, studio,
      franchise or copyrighted character in any `reference_prompt`. Use generic
      stylistic descriptors instead.
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
    `current_character`, and `user_feedback`. Treat it as INPUT CONTEXT only.
    Apply the feedback to `current_character` and return the UPDATED character
    record. You may rewrite `name`, `physical_description`, `outfit`, and
    `reference_prompt` as needed; the `id` MUST stay unchanged.

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
    - Never name a real-world artist, studio, franchise or copyrighted character.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


LOCATION_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single location record for a comic book project.

    The user message contains a JSON wrapper with `metadata`, `style`,
    `current_location`, and `user_feedback`. Treat it as INPUT CONTEXT only.
    Apply the feedback to `current_location` and return the UPDATED location
    record. The `id` MUST stay unchanged.

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
    - Never name a real-world artist, studio, franchise or copyrighted character.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


OBJECT_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising a single object / product / reference record for a comic
    book project.

    The user message contains a JSON wrapper with `metadata`, `style`,
    `current_object`, and `user_feedback`. Treat it as INPUT CONTEXT only.
    Apply the feedback to `current_object` and return the UPDATED object
    record. The `id` MUST stay unchanged.

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
    - Never name a real-world artist, studio, franchise or copyrighted character.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


COVER_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising the FRONT COVER specification of an in-progress comic
    book script.

    The user has supplied a feedback note. Apply it to the cover record below
    and return the updated `Cover` object as JSON.

    Fields:
    - `scene_description`: evocative illustration concept for the front cover
    - `title_placement`: hint for where and how the title is laid out
    - `subtitle`: optional subtitle or null
    - `tagline`: optional short marketing tagline or null

    HARD CONSTRAINTS:
    - Write content in the language specified by `metadata.language`.
    - Never name a real-world artist, studio, franchise or copyrighted character.
    - Output ONLY the JSON object. No markdown fences, no commentary.
    """)


BACK_COVER_REFINE_SYSTEM_PROMPT = dedent("""\
    You are revising the BACK COVER specification of an in-progress comic
    book script.

    The user has supplied a feedback note. Apply it to the back cover record
    below and return the updated `BackCover` object as JSON.

    Fields:
    - `synopsis_blurb`: 3-5 sentence marketing-tone presentation of the story
      WITHOUT spoilers, ending on a hook
    - `scene_description`: optional small illustration concept, or null
    - `tagline`: optional short tagline or null
    - `layout_notes`: optional layout hints (e.g. "barcode bottom-right corner")

    HARD CONSTRAINTS:
    - Write content in the language specified by `metadata.language`.
    - Never name a real-world artist, studio, franchise or copyrighted character.
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
    - Output ONLY the JSON object for this page. No markdown fences, no commentary.
    """)


# --- Top-level orchestration ---

def generate_script(
    config: BdGenInput,
    input_path: Path,
    feedback: list[str] | None = None,
    preview_pages: int | None = None,
    script_path: Path | None = None,
    reporter: ProgressReporter | None = None,
    interrupt: InterruptFlag | None = None,
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

    bd_script = _try_resume(script_path, config, target_pages, rep)

    if bd_script is None:
        rep.emit(ProgressEvent(
            step="script",
            phase="setup",
            message=f"Setup phase: characters, locations, cover, back cover ({label})…",
        ))
        flag.check()
        setup = _call_llm(
            SETUP_SYSTEM_PROMPT,
            _build_setup_prompt(config, feedback, preview_pages, target_pages),
            model_cfg,
            _LLMSetupDraft,
        )
        bd_script = _build_skeleton(config, setup, input_path, label)
        if script_path:
            bd_script.save(script_path)
        rep.emit(ProgressEvent(
            step="script",
            phase="setup_done",
            message=(
                f"Setup terminé : {len(bd_script.characters)} personnages, "
                f"{len(bd_script.locations)} décors."
            ),
            extra={
                "characters": len(bd_script.characters),
                "locations": len(bd_script.locations),
            },
        ))

    for page_n in range(len(bd_script.pages) + 1, target_pages + 1):
        flag.check()
        rep.emit(ProgressEvent(
            step="script",
            phase=f"page_{page_n}",
            message=f"Génération de la planche {page_n}/{target_pages} ({label})…",
            current=page_n,
            total=target_pages,
        ))
        page_draft = _call_llm(
            PAGE_SYSTEM_PROMPT,
            _build_page_prompt(
                config, bd_script, page_n, target_pages, feedback, preview_pages
            ),
            model_cfg,
            Page,
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
        rep.emit(ProgressEvent(
            step="script",
            phase=f"page_{page_n}_done",
            message=f"Planche {page_n} écrite.",
            current=page_n,
            total=target_pages,
        ))

    rep.emit(ProgressEvent(
        step="script",
        phase="done",
        message=(
            f"Scénario complet : {len(bd_script.characters)} personnages, "
            f"{len(bd_script.locations)} décors, {len(bd_script.pages)} planches, "
            f"{sum(len(p.panels) for p in bd_script.pages)} cases."
        ),
    ))
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
        reporter.emit(ProgressEvent(
            step="script",
            phase="resume_failed",
            message=f"Script existant illisible ({e}) ; regénération complète.",
        ))
        return None
    if existing.project != config.project or not existing.characters:
        return None
    if len(existing.pages) >= target_pages:
        reporter.emit(ProgressEvent(
            step="script",
            phase="already_complete",
            message=(
                f"Scénario déjà complet sur disque ({len(existing.pages)} planches)."
            ),
            current=len(existing.pages),
            total=target_pages,
        ))
        return existing
    reporter.emit(ProgressEvent(
        step="script",
        phase="resuming",
        message=(
            f"Reprise : {len(existing.pages)}/{target_pages} planches déjà écrites."
        ),
        current=len(existing.pages),
        total=target_pages,
    ))
    return existing


def _build_skeleton(
    config: BdGenInput, setup: _LLMSetupDraft, input_path: Path, model_label: str
) -> BdGenScript:
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
        generation_options=config.generation_options,
        characters=[
            ScriptCharacter(**c.model_dump(), reference_image=None)
            for c in setup.characters
        ],
        locations=[
            ScriptLocation(**l.model_dump(), reference_image=None)
            for l in setup.locations
        ],
        objects=[
            ScriptObject(**o.model_dump(), reference_image=None)
            for o in setup.objects
        ],
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
            loc_rule = (
                "Invent every location your story will need across the FULL story "
                "arc (the input has none)."
            )
    else:
        loc_rule = (
            f"STRICT: Use ONLY the {n_locs} input location(s). Do NOT invent any "
            f"new location."
        )
    if n_objs == 0 and config.structure.allow_extra_objects:
        obj_rule = (
            "The user provided no objects. Do NOT invent any: leave the `objects` "
            "array empty unless the brief explicitly requires a recurring object."
        )
    elif n_objs == 0:
        obj_rule = (
            "STRICT: The user provided no objects and disallowed inventing any. "
            "Leave the `objects` array empty."
        )
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
        "time.\n\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + preview_note
        + authoring_rules
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
        "locations": [
            {"id": l.id, "name": l.name, "description": l.description}
            for l in bd_script.locations
        ],
        "objects": [
            {"id": o.id, "name": o.name, "description": o.description}
            for o in bd_script.objects
        ],
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
                "This is the LAST preview page — end on a natural beat, do NOT "
                "artificially wrap up the full arc."
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
        parts.extend([
            "PREVIOUSLY GENERATED PAGES (for narrative continuity, DO NOT regenerate):",
            json.dumps(prior_pages, ensure_ascii=False, indent=2),
            "",
        ])
    else:
        parts.append("(No previous pages — this is page 1.)")
        parts.append("")
    parts.append(
        f"Now generate page {page_n} of {target_pages} as a single JSON Page object."
        + preview_note
    )

    base = "\n".join(parts)
    if feedback:
        base += feedback_block(feedback)
    return base


# --- LLM dispatch with retries ---

def _call_llm(
    system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]
) -> T:
    """Dispatch to the configured provider, with bounded retries on parse failure.

    Per-call retries (rather than per-script) mean a single page failure only
    re-runs that page, not the whole script.
    """
    last_error: RuntimeError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if model_config.provider == "openai":
                return _call_openai(system, user, model_config, output_type)
            if model_config.provider == "anthropic":
                return _call_anthropic(system, user, model_config, output_type)
            raise NotImplementedError(
                f"Provider '{model_config.provider}' is not yet supported."
            )
        except RuntimeError as e:
            last_error = e
            short_reason = str(e).split("\n", 1)[0]
            if attempt < MAX_ATTEMPTS:
                wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                print(
                    f"  Attempt {attempt}/{MAX_ATTEMPTS} failed: {short_reason}\n"
                    f"  Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                print(f"  All {MAX_ATTEMPTS} attempts failed.")
                raise

    assert last_error is not None
    raise last_error


def _call_openai(
    system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]
) -> T:
    """OpenAI Chat Completions with structured Pydantic output."""
    client = OpenAI()
    kwargs = {
        "model": model_config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": output_type,
    }
    try:
        completion = client.chat.completions.parse(
            temperature=model_config.temperature, **kwargs
        )
    except Exception as e:
        if "temperature" not in str(e).lower():
            raise
        completion = client.chat.completions.parse(**kwargs)

    message = completion.choices[0].message
    if message.parsed is None:
        raise RuntimeError(
            f"LLM returned no parsed content. Refusal: {message.refusal}"
        )
    return message.parsed


def _call_anthropic(
    system: str, user: str, model_config: ScriptModelConfig, output_type: type[T]
) -> T:
    """Anthropic Messages API in streaming mode + manual JSON parsing.

    The system prompt is cached (5-minute TTL) so successive calls (setup +
    pages, or retries) pay only ~0.1x for the system block on cache hits.
    """
    import anthropic

    client = anthropic.Anthropic()
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
            sys.stdout.write(
                f"\r  [writing JSON] {state['chars']} chars, {elapsed}s elapsed   "
            )
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

    with client.messages.stream(
        model=model_config.model,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
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

    if final.usage:
        u = final.usage
        cache_read = u.cache_read_input_tokens or 0
        cache_write = u.cache_creation_input_tokens or 0
        cached_note = f", cache hit: {cache_read}" if cache_read else ""
        if cache_write and not cache_read:
            cached_note = f", cache write: {cache_write}"
        print(
            f"  Tokens: input={u.input_tokens + cache_read + cache_write}"
            f"{cached_note}, output={u.output_tokens}"
        )

    raw = "".join(text_parts)
    if not raw.strip():
        raise RuntimeError("Claude returned no text content (only thinking blocks?).")
    json_text = _strip_json_fences(raw)
    try:
        return output_type.model_validate_json(json_text)
    except Exception as e:
        unwrapped = _try_unwrap_echoed_input(json_text, output_type)
        if unwrapped is not None:
            return unwrapped
        raise RuntimeError(
            f"Failed to parse Claude response as {output_type.__name__}: {e}\n"
            f"Raw text (first 800 chars): {raw[:800]}"
        )


def _strip_json_fences(text: str) -> str:
    """Strip surrounding ```json fences if the model wrapped its output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _try_unwrap_echoed_input(
    json_text: str, output_type: type[BaseModel]
) -> BaseModel | None:
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
        k for k in data
        if k.startswith("current_") or k.startswith("updated_") or k in {"character", "location"}
    ]
    for key in candidate_keys:
        try:
            return output_type.model_validate(data[key])
        except Exception:
            continue
    return None


# --- Targeted regeneration (single character / location / page) ---

def regenerate_character(
    bd_script: BdGenScript,
    character_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
) -> ScriptCharacter:
    """Rewrite a single character via a focused LLM call. Returns the updated record."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    char = bd_script.character_by_id(character_id)
    if char is None:
        raise RuntimeError(f"Personnage inconnu : {character_id}")
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_character_{character_id}",
        message=f"Retouche du personnage « {char.name} »…",
    ))
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "current_character": char.model_dump(mode="json", exclude={"reference_image"}),
        "user_feedback": feedback_text,
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        CHARACTER_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        _DraftCharacter,
    )
    if draft.id != character_id:
        draft.id = character_id  # never let the model rename
    char.physical_description = draft.physical_description
    char.outfit = draft.outfit
    char.reference_prompt = draft.reference_prompt
    char.name = draft.name
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_character_{character_id}_done",
        message=f"Personnage « {char.name} » mis à jour.",
    ))
    return char


def regenerate_location(
    bd_script: BdGenScript,
    location_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
) -> ScriptLocation:
    """Rewrite a single location via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    loc = bd_script.location_by_id(location_id)
    if loc is None:
        raise RuntimeError(f"Décor inconnu : {location_id}")
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_location_{location_id}",
        message=f"Retouche du décor « {loc.name} »…",
    ))
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "current_location": loc.model_dump(mode="json", exclude={"reference_image"}),
        "user_feedback": feedback_text,
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        LOCATION_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        _DraftLocation,
    )
    if draft.id != location_id:
        draft.id = location_id
    loc.name = draft.name
    loc.description = draft.description
    loc.reference_prompt = draft.reference_prompt
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_location_{location_id}_done",
        message=f"Décor « {loc.name} » mis à jour.",
    ))
    return loc


def regenerate_object(
    bd_script: BdGenScript,
    object_id: str,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
) -> ScriptObject:
    """Rewrite a single object via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    obj = bd_script.object_by_id(object_id)
    if obj is None:
        raise RuntimeError(f"Objet inconnu : {object_id}")
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_object_{object_id}",
        message=f"Retouche de l'objet « {obj.name} »…",
    ))
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "current_object": obj.model_dump(mode="json", exclude={"reference_image"}),
        "user_feedback": feedback_text,
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        OBJECT_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        _DraftObject,
    )
    if draft.id != object_id:
        draft.id = object_id
    obj.name = draft.name
    obj.description = draft.description
    obj.reference_prompt = draft.reference_prompt
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_object_{object_id}_done",
        message=f"Objet « {obj.name} » mis à jour.",
    ))
    return obj


def regenerate_page(
    bd_script: BdGenScript,
    page_number: int,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
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
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_page_{page_number}",
        message=f"Retouche de la planche {page_number}…",
        current=page_number, total=len(bd_script.pages),
    ))
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
        "locations": [
            {"id": l.id, "name": l.name, "description": l.description}
            for l in bd_script.locations
        ],
        "objects": [
            {"id": o.id, "name": o.name, "description": o.description}
            for o in bd_script.objects
        ],
    }
    prior = [p.model_dump(mode="json") for p in bd_script.pages[:idx]]
    later = [p.model_dump(mode="json") for p in bd_script.pages[idx + 1:]]
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "structure": {
            "page_count": len(bd_script.pages),
        },
        "setup": setup,
        "prior_pages": prior,
        "later_pages": later,
        "current_page": bd_script.pages[idx].model_dump(mode="json"),
        "user_feedback": feedback_text,
        "instruction": (
            f"Rewrite ONLY page {page_number} (keep page_number={page_number}). "
            f"Preserve continuity with prior_pages AND later_pages."
        ),
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        PAGE_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        Page,
    )
    new_page = Page(
        page_number=page_number,
        layout=draft.layout,
        panels=draft.panels,
    )
    bd_script.pages[idx] = new_page
    rep.emit(ProgressEvent(
        step="script", phase=f"refine_page_{page_number}_done",
        message=f"Planche {page_number} mise à jour.",
        current=page_number, total=len(bd_script.pages),
    ))
    return new_page


def regenerate_cover(
    bd_script: BdGenScript,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
) -> Cover:
    """Rewrite the front-cover record via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    if bd_script.cover is None:
        raise RuntimeError("Ce projet n'a pas de couverture à retoucher.")
    rep.emit(ProgressEvent(
        step="script", phase="refine_cover",
        message="Retouche de la couverture…",
    ))
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "current_cover": bd_script.cover.model_dump(mode="json"),
        "user_feedback": feedback_text,
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        COVER_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        Cover,
    )
    bd_script.cover = draft
    rep.emit(ProgressEvent(
        step="script", phase="refine_cover_done",
        message="Couverture mise à jour.",
    ))
    return draft


def regenerate_back_cover(
    bd_script: BdGenScript,
    feedback_text: str,
    reporter: ProgressReporter | None = None,
) -> BackCover:
    """Rewrite the back-cover record via a focused LLM call."""
    rep = _coerce_reporter(reporter)
    if bd_script.generation_options is None:
        raise RuntimeError("Le script n'a pas de generation_options ; impossible de retoucher.")
    if bd_script.back_cover is None:
        raise RuntimeError("Ce projet n'a pas de 4ᵉ de couverture à retoucher.")
    rep.emit(ProgressEvent(
        step="script", phase="refine_back_cover",
        message="Retouche de la 4ᵉ de couverture…",
    ))
    user_prompt = json.dumps({
        "metadata": bd_script.metadata.model_dump(mode="json"),
        "style": bd_script.style.model_dump(mode="json"),
        "current_back_cover": bd_script.back_cover.model_dump(mode="json"),
        "user_feedback": feedback_text,
    }, ensure_ascii=False, indent=2)
    draft = _call_llm(
        BACK_COVER_REFINE_SYSTEM_PROMPT,
        user_prompt,
        bd_script.generation_options.script_model,
        BackCover,
    )
    bd_script.back_cover = draft
    rep.emit(ProgressEvent(
        step="script", phase="refine_back_cover_done",
        message="4ᵉ de couverture mise à jour.",
    ))
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
