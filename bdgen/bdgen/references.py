"""Step 2: generate one reference sheet per character and per location."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openai import OpenAI
from PIL import Image

from . import secret_store
from .feedback import FeedbackStore, feedback_block
from .image_rules import IMAGE_CONSTRAINTS
from .models import (
    BdGenScript,
    ImageModelConfig,
    ReferencesOptions,
    Style,
)
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)
from .stats import normalise_usage, record_event, start_timer, stop_timer
from . import trace
from . import versioning

REFERENCE_SIZE = "1024x1024"
XAI_MAX_PROMPT_CHARS = 8000
XAI_PROMPT_MARGIN = 200
XAI_PROMPT_OMISSION = "\n\n[Prompt abridged for Grok's 8000-character image prompt limit.]\n\n"
# Per-entity photo caps per provider. xAI total input = 3 (style-ref + entity photos).
OPENAI_MAX_ENTITY_PHOTOS = 4
XAI_MAX_ENTITY_PHOTOS = 2


def generate_references(
    script: BdGenScript,
    options: ReferencesOptions,
    image_model: ImageModelConfig,
    script_path: Path | None = None,
    feedback_store: FeedbackStore | None = None,
    force: bool = False,
    reporter: ProgressReporter | None = None,
    interrupt: InterruptFlag | None = None,
    style_ref: Path | None = None,
    character_photos: dict[str, list[Path]] | None = None,
    location_photos: dict[str, list[Path]] | None = None,
    object_photos: dict[str, list[Path]] | None = None,
    stats_project_dir: Path | None = None,
    allow_style_copy: bool | None = None,
) -> BdGenScript:
    """Generate every character, location and object reference sheet.

    Saves images under ``{options.output_dir}/{characters|locations|objects}/{id}.png``
    and fills the matching ``reference_image`` field on the script. Resumable: skips
    any entry whose target PNG already exists on disk and is non-empty (unless
    ``force`` is True). When ``script_path`` is provided, the script JSON is re-saved
    after each successful generation so progress survives a crash. When
    ``feedback_store`` is provided, any feedback recorded for a given target is
    appended to its prompt. ``reporter`` receives structured progress events;
    ``interrupt`` is checked between each entry so generation can stop cleanly.
    """
    rep = _coerce_reporter(reporter)
    flag = _coerce_flag(interrupt)
    # The flag lives on the script; allow callers to override it explicitly.
    if allow_style_copy is None:
        allow_style_copy = bool(getattr(script, "allow_style_copy", False))
    with (
        trace.project_session(stats_project_dir),
        trace.node(
            "generate_references",
            "flow",
            inputs={
                "project": script.project,
                "characters": len(script.characters),
                "locations": len(script.locations),
                "objects": len(script.objects),
                "force": force,
                "image_model": f"{image_model.provider}/{image_model.model}",
            },
        ),
    ):
        return _generate_references_traced(
            script,
            options,
            image_model,
            script_path,
            feedback_store,
            force,
            rep,
            flag,
            style_ref,
            character_photos,
            location_photos,
            object_photos,
            stats_project_dir,
            allow_style_copy,
        )


def _generate_references_traced(
    script: BdGenScript,
    options: ReferencesOptions,
    image_model: ImageModelConfig,
    script_path: Path | None,
    feedback_store: FeedbackStore | None,
    force: bool,
    rep: ProgressReporter,
    flag: InterruptFlag,
    style_ref: Path | None,
    character_photos: dict[str, list[Path]] | None,
    location_photos: dict[str, list[Path]] | None,
    object_photos: dict[str, list[Path]] | None,
    stats_project_dir: Path | None,
    allow_style_copy: bool,
) -> BdGenScript:
    if not options.generate:
        rep.emit(
            ProgressEvent(
                step="references",
                phase="skipped",
                message="Génération des références désactivée dans les options.",
            )
        )
        return script

    char_dir = options.output_dir / "characters"
    loc_dir = options.output_dir / "locations"
    obj_dir = options.output_dir / "objects"
    char_dir.mkdir(parents=True, exist_ok=True)
    loc_dir.mkdir(parents=True, exist_ok=True)
    obj_dir.mkdir(parents=True, exist_ok=True)

    client = _client(image_model)

    total = len(script.characters) + len(script.locations) + len(script.objects)
    done = 0

    for character in script.characters:
        flag.check()
        done += 1
        target = char_dir / f"{character.id}.png"
        if not force and _is_complete(target):
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"character_{character.id}_skipped",
                    message=f"Personnage « {character.name} » déjà sur disque.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": character.id, "kind": "character"},
                )
            )
        else:
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"character_{character.id}",
                    message=f"Génération de la référence pour « {character.name} »…",
                    current=done,
                    total=total,
                    extra={"id": character.id, "kind": "character"},
                )
            )
            prompt = _augment_prompt(
                character.reference_prompt,
                feedback_store,
                character.id,
                style=script.style,
            )
            photos = (character_photos or {}).get(character.id) or []
            started_at, started = start_timer()
            image_stats = _generate_image(
                client,
                image_model,
                prompt,
                target,
                style_ref=style_ref,
                character_photos=photos,
                allow_style_copy=allow_style_copy,
                trace_name=f"ref_character:{character.id}",
            )
            record_event(
                stats_project_dir,
                step="references",
                target_id=character.id,
                target_kind="character",
                operation="generate_reference",
                provider=image_model.provider,
                model=image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=target,
                extra={"quality": image_model.quality},
            )
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"character_{character.id}_done",
                    message=f"Référence « {character.name} » générée.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": character.id, "kind": "character"},
                )
            )
        character.reference_image = target
        if script_path is not None:
            script.save(script_path)

    for location in script.locations:
        flag.check()
        done += 1
        target = loc_dir / f"{location.id}.png"
        if not force and _is_complete(target):
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"location_{location.id}_skipped",
                    message=f"Décor « {location.name} » déjà sur disque.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": location.id, "kind": "location"},
                )
            )
        else:
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"location_{location.id}",
                    message=f"Génération de la référence pour le décor « {location.name} »…",
                    current=done,
                    total=total,
                    extra={"id": location.id, "kind": "location"},
                )
            )
            prompt = _augment_prompt(
                location.reference_prompt,
                feedback_store,
                location.id,
                style=script.style,
                medium_anchor=_LOCATION_MEDIUM_ANCHOR,
            )
            photos = (location_photos or {}).get(location.id) or []
            started_at, started = start_timer()
            image_stats = _generate_image(
                client,
                image_model,
                prompt,
                target,
                style_ref=style_ref,
                location_photos=photos,
                allow_style_copy=allow_style_copy,
                trace_name=f"ref_location:{location.id}",
            )
            record_event(
                stats_project_dir,
                step="references",
                target_id=location.id,
                target_kind="location",
                operation="generate_reference",
                provider=image_model.provider,
                model=image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=target,
                extra={"quality": image_model.quality},
            )
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"location_{location.id}_done",
                    message=f"Référence « {location.name} » générée.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": location.id, "kind": "location"},
                )
            )
        location.reference_image = target
        if script_path is not None:
            script.save(script_path)

    for obj in script.objects:
        flag.check()
        done += 1
        target = obj_dir / f"{obj.id}.png"
        if not force and _is_complete(target):
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"object_{obj.id}_skipped",
                    message=f"Objet « {obj.name} » déjà sur disque.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": obj.id, "kind": "object"},
                )
            )
        else:
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"object_{obj.id}",
                    message=f"Génération de la référence pour l'objet « {obj.name} »…",
                    current=done,
                    total=total,
                    extra={"id": obj.id, "kind": "object"},
                )
            )
            prompt = _augment_prompt(
                obj.reference_prompt,
                feedback_store,
                obj.id,
                style=script.style,
                medium_anchor=_OBJECT_MEDIUM_ANCHOR,
            )
            photos = (object_photos or {}).get(obj.id) or []
            started_at, started = start_timer()
            image_stats = _generate_image(
                client,
                image_model,
                prompt,
                target,
                style_ref=style_ref,
                object_photos=photos,
                allow_style_copy=allow_style_copy,
                trace_name=f"ref_object:{obj.id}",
            )
            record_event(
                stats_project_dir,
                step="references",
                target_id=obj.id,
                target_kind="object",
                operation="generate_reference",
                provider=image_model.provider,
                model=image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=target,
                extra={"quality": image_model.quality},
            )
            rep.emit(
                ProgressEvent(
                    step="references",
                    phase=f"object_{obj.id}_done",
                    message=f"Référence « {obj.name} » générée.",
                    current=done,
                    total=total,
                    artifact=str(target),
                    extra={"id": obj.id, "kind": "object"},
                )
            )
        obj.reference_image = target
        if script_path is not None:
            script.save(script_path)

    rep.emit(
        ProgressEvent(
            step="references",
            phase="done",
            message="Toutes les références sont prêtes.",
            current=total,
            total=total,
        )
    )
    return script


_STYLE_RESET_BRIDGE = (
    "STYLE RESET — The description above defines WHAT to draw (subject, "
    "appearance, composition). It may contain style mentions that are now "
    "OUTDATED. Disregard any art style, color palette, line work, or rendering "
    "technique named anywhere above this line. The MANDATORY STYLE ENFORCEMENT "
    "section below is the sole and final authority on visual style."
)

_LOCATION_MEDIUM_ANCHOR = (
    "FINAL MEDIUM ENFORCEMENT — NON-NEGOTIABLE: the output MUST be a "
    "hand-drawn comic-book illustration (a background panel). It MUST NOT "
    "look like a photograph, a photorealistic render, or any non-illustrated "
    "medium. If the description above uses photographic language (depth of "
    "field, bokeh, establishing shot, camera angle…), translate it into "
    "drawn-illustration equivalents. The entire output must read as a drawn "
    "comic-book panel background — not as a photograph."
)

_OBJECT_MEDIUM_ANCHOR = (
    "FINAL MEDIUM ENFORCEMENT — NON-NEGOTIABLE: the output MUST be a "
    "hand-drawn comic-book illustration (an object reference sheet on a "
    "neutral white background). It MUST NOT look like a product photograph, "
    "a studio shot, or any photorealistic render. If the description above "
    "uses photographic language (macro, depth of field, studio lighting…), "
    "translate it into drawn-illustration equivalents. The entire output must "
    "read as a drawn comic-book object illustration — not as a photograph."
)


def _augment_prompt(
    prompt: str,
    feedback_store: FeedbackStore | None,
    target: str,
    style: Style | None = None,
    medium_anchor: str | None = None,
) -> str:
    parts = [prompt, IMAGE_CONSTRAINTS]
    if style is not None:
        parts.append(_STYLE_RESET_BRIDGE)
        parts.append(_style_enforcement_block(style))
    if medium_anchor:
        parts.append(medium_anchor)
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("references", target)
        if feedbacks:
            parts.append(feedback_block(feedbacks))
    return "\n\n".join(parts)


def _style_enforcement_block(style: Style) -> str:
    """Build a mandatory style-enforcement block appended at the end of every
    image-generation prompt. Repeating the style at the tail of the prompt
    ensures gpt-image-2 treats it as a hard constraint, even when a photo
    reference introduces conflicting colors or rendering.
    """
    lines = [
        "MANDATORY STYLE ENFORCEMENT — these constraints override any "
        "conflicting visual cue from input images or prior instructions:"
    ]
    lines.append(f"- Art style: {style.art_style}")
    if style.color_palette:
        lines.append(f"- Color palette (STRICT): {style.color_palette}")
        lines.append(
            "  YOU MUST follow this palette exactly. If it specifies black and "
            "white, the output MUST contain NO color whatsoever — no skin "
            "tones, no colored clothing, no colored backgrounds, no warm or "
            "cool tints. Use ONLY black ink, white paper, and gray values for "
            "shading. Any color in the output is a failure."
        )
    if style.line_work:
        lines.append(f"- Line work: {style.line_work}")
    if style.character_rendering:
        lines.append(f"- Character rendering (STRICT): {style.character_rendering}")
        lines.append(
            "  Match the EXACT degree of anatomical distortion described above. "
            "If the style calls for exaggerated/bloated/crude proportions, the "
            "output MUST look equally exaggerated — do NOT clean up, do NOT "
            "regularize proportions, do NOT add anatomical precision that the "
            "style does not call for. A polished or realistic rendering when "
            "the style demands crude/abstract is a failure."
        )
    if style.stylization_level:
        lines.append(f"- Stylization intensity (CRITICAL): {style.stylization_level}")
        lines.append(
            "  This is the REQUIRED level of distortion. You MUST match it. "
            "If 'heavily stylized' or 'extremely abstract', the output must "
            "look raw, crude, and deliberately imperfect — NOT polished, NOT "
            "well-proportioned, NOT clean. Err on the side of MORE distortion "
            "rather than less. A clean, polished output when the style demands "
            "heavy stylization is worse than an overly crude one."
        )
    if style.negative_constraints:
        lines.append("")
        lines.append(f"FORBIDDEN — {style.negative_constraints}")
        lines.append(
            "Violating any of the above negative constraints is an automatic "
            "failure regardless of how good the output looks otherwise."
        )
    return "\n".join(lines)


def _is_complete(path: Path) -> bool:
    """A reference is considered complete only if the file exists and is non-empty."""
    return path.exists() and path.stat().st_size > 0


def _client(image_model: ImageModelConfig) -> OpenAI | None:
    if image_model.provider == "openai":
        return secret_store.openai_client()
    if image_model.provider == "xai":
        return None
    raise NotImplementedError(f"Provider '{image_model.provider}' is not yet supported.")


_STYLE_REF_PREAMBLE = (
    "STYLE REFERENCE (this input image): this image is provided ONLY as a "
    "visual style reference. Study its drawing technique, line quality, "
    "coloring method, level of detail, body proportions, palette and overall "
    "visual tone, and replicate THOSE STYLISTIC QUALITIES in your output.\n\n"
    "DEGREE OF STYLIZATION — CRITICAL:\n"
    "- Match the EXACT level of crudeness, distortion and imperfection you "
    "  see in this reference. If the characters in this reference look like "
    "  rough ink blobs with exaggerated limbs, your output MUST look equally "
    "  rough and exaggerated. Do NOT 'improve' or 'polish' the style.\n"
    "- If the reference has messy, chaotic line work, your output must be "
    "  equally messy and chaotic. If proportions are wildly exaggerated, "
    "  yours must be too. If faces are barely recognizable, yours must be "
    "  too. NEVER default to clean, polished, well-proportioned comic art "
    "  when the reference is crude and raw.\n"
    "- Think of it as: if someone placed your output next to this reference, "
    "  they should believe the SAME ARTIST drew both. Same energy, same "
    "  level of finish, same degree of anatomical distortion."
)


_STYLE_REF_STRICT_NON_COPY = (
    "STRICT NON-COPYING RULE — MANDATORY, NO EXCEPTIONS (this is a copyright "
    "constraint, not a stylistic suggestion):\n"
    "- DO NOT reproduce, paraphrase, OCR, or recreate ANY text visible in "
    "  the style reference. This includes titles, subtitles, taglines, "
    "  captions, character names, dialog, sound effects, signs, labels, "
    "  speech bubbles, headers, footers, page numbers, magazine logos, "
    "  publisher names, barcodes, or ANY other lettering, in part or in full.\n"
    "- DO NOT reproduce ANY characters, faces, hairstyles, body types, "
    "  outfits, accessories, props, vehicles, animals or recognizable "
    "  objects from the reference. Only the project's own character sheets "
    "  (the OTHER input images) are authoritative for who appears.\n"
    "- DO NOT reproduce the reference's specific scenes, panel content, "
    "  compositions, settings, locations, decorative motifs, logos, mascots, "
    "  or any other narrative element.\n"
    "- DO NOT reuse the reference's color schemes literally if they encode "
    "  identifiable branding; abstract the palette, do not photocopy it.\n"
    "- The reference is a STYLE TEACHER, not a CONTENT SOURCE. Imagine you "
    "  have only seen it through frosted glass: you can tell HOW it was drawn "
    "  but not WHAT was drawn. Output the project's own content rendered in "
    "  that learned style."
)


_STYLE_REF_COPY_ALLOWED = (
    "STYLE COPY MODE — the user has explicitly authorized close emulation of "
    "this reference, including its recognizable visual identity. Treat it as "
    "both a STYLE TEACHER and a permitted source of visual inspiration:\n"
    "- You MAY emulate the reference's character designs, costumes, props, "
    "  settings, decorative motifs and color schemes in order to reproduce "
    "  its known style faithfully.\n"
    "- The project's own character sheets (the OTHER input images) remain "
    "  authoritative for WHO appears in the BD — when the project provides "
    "  a character sheet for a given character, that sheet wins. The style "
    "  reference is used to shape HOW everything is drawn.\n"
    "- DESCRIBE, NEVER NAME — the rendered output must NOT contain, anywhere, "
    "  the proper name of the real-world author, illustrator, studio, "
    "  publisher, franchise, series, brand or copyrighted character that "
    "  inspired the reference. Specifically: no signature, no credit line, "
    "  no watermark, no logo, no series title, no publisher mark, no "
    "  trademark and no caption naming a known author or work may appear in "
    "  the image. The output must read as an original piece that happens to "
    "  share the same visual style. Emulate the LOOK, not the LABEL.\n"
    "- Still do NOT transcribe verbatim any text visible in the reference "
    "  (titles, logos, captions, brand names). Render text in the project's "
    "  own language and content only. Other visual elements may be emulated."
)


def style_ref_label(allow_copy: bool = False) -> str:
    """Build the label appended to the style-reference input image.

    The default (``allow_copy=False``) returns the strict, non-infringing
    instruction set. When ``allow_copy`` is True the strict non-copying
    rule is replaced with a permissive variant that explicitly authorises
    the model to emulate the reference's recognisable visual identity.
    """
    suffix = _STYLE_REF_COPY_ALLOWED if allow_copy else _STYLE_REF_STRICT_NON_COPY
    return f"{_STYLE_REF_PREAMBLE}\n\n{suffix}"


# Backwards-compatible constant: matches the strict (default) behaviour so
# any caller that still imports the constant keeps the safe default.
STYLE_REF_LABEL = style_ref_label(allow_copy=False)


PHOTO_REF_LABEL = (
    "PERSON LIKENESS REFERENCE (this input image is a photograph): use this "
    "photo ONLY to anchor the recognizable facial features and overall "
    "physiognomy of the character — like a caricaturist working from a "
    "reference photo. The art style described in the prompt above (and shown "
    "in the style reference if present) is the master and ALWAYS overrides "
    "any photographic quality of this image.\n\n"
    "PRESERVE FROM THE PHOTO (likeness — structural features only):\n"
    "- Face shape, jawline, head proportions.\n"
    "- Nose shape, eye spacing and shape, eyebrow shape.\n"
    "- Hair texture and approximate length / silhouette.\n"
    "- Approximate age and build.\n"
    "- Distinguishing features: glasses, beard, freckles, moles, scars, "
    "  visible piercings, dimples.\n\n"
    "DO NOT PRESERVE FROM THE PHOTO (style stays in charge):\n"
    "- DO NOT reproduce photographic realism, photographic lighting, depth "
    "  of field, skin micro-texture, photographic grain, sharpness.\n"
    "- DO NOT reuse the photo's background, props, pose or framing.\n"
    "- DO NOT copy the photo's clothing — apply the outfit described in the "
    "  text prompt instead.\n"
    "- DO NOT reproduce the photo's COLORS. The project's color palette is "
    "  the sole authority on what colors appear in the output. If the "
    "  project's palette is black and white, render ALL skin, hair, eyes "
    "  and clothing as grayscale values — no skin tones, no colored irises, "
    "  no colored hair. Translate the photo's tonal relationships into the "
    "  project's palette.\n"
    "- DO NOT introduce any photo-derived rendering technique that would "
    "  conflict with the defined comic-book style. If in doubt, the style "
    "  always wins; the photo is only there for likeness, not for look.\n\n"
    "Output a stylized comic-book character drawn ENTIRELY in the project's "
    "art style and color palette, that recognizably resembles the person in "
    "the photo."
)


LOCATION_PHOTO_REF_LABEL = (
    "PLACE LIKENESS REFERENCE (this input image is a photograph of a real "
    "place / setting): use this photo ONLY to anchor the recognizable "
    "architecture, layout, dominant features and overall atmosphere of the "
    "location — like an illustrator sketching from a reference photo. The "
    "art style described in the prompt above (and shown in the style "
    "reference if present) is the master and ALWAYS overrides any "
    "photographic quality of this image.\n\n"
    "PRESERVE FROM THE PHOTO (likeness):\n"
    "- Overall spatial layout, perspective and characteristic structure of "
    "  the place.\n"
    "- Recognizable landmarks: distinctive buildings, walls, doors, windows, "
    "  furniture, vegetation, terrain features.\n"
    "- Dominant colors, materials and lighting mood, abstracted to the "
    "  project's palette.\n"
    "- Time of day / weather cues if they define the place's atmosphere.\n\n"
    "DO NOT PRESERVE FROM THE PHOTO (style stays in charge):\n"
    "- DO NOT reproduce photographic realism, photographic lighting, depth "
    "  of field, micro-textures, photographic grain, sharpness.\n"
    "- DO NOT include any people, vehicles or characters that happen to be "
    "  in the photo. The reference is for the SETTING only.\n"
    "- DO NOT reuse text/signage from the photo verbatim if it is brand- or "
    "  trademark-bearing; either omit it or render generic stylized lettering.\n"
    "- DO NOT introduce any photo-derived rendering technique that would "
    "  conflict with the defined comic-book style.\n\n"
    "Output a stylized comic-book establishing shot of the place, drawn "
    "ENTIRELY in the project's art style, with NO characters in frame, that "
    "is recognizably the SAME setting as the one in the photo."
)


OBJECT_PHOTO_REF_LABEL = (
    "OBJECT LIKENESS REFERENCE (this input image is a photograph of a real "
    "object, product or reference): use this photo ONLY to anchor the "
    "recognizable shape, proportions, key markings and characteristic "
    "silhouette of the object — like an illustrator working from a reference "
    "photo. The art style described in the prompt above (and shown in the "
    "style reference if present) is the master and ALWAYS overrides any "
    "photographic quality of this image.\n\n"
    "PRESERVE FROM THE PHOTO (likeness):\n"
    "- Overall shape, proportions and silhouette of the object.\n"
    "- Distinctive structural details (e.g. cover layout for a book, label "
    "  shape for a bottle, characteristic ornaments or markings).\n"
    "- Dominant colors and color zones, abstracted to the project's palette.\n"
    "- Any textual element on the object: render it as STYLIZED LETTERING "
    "  consistent with the art style, but keep the wording recognizable when "
    "  it matters for the object's identity (e.g. a book title on a cover).\n\n"
    "DO NOT PRESERVE FROM THE PHOTO (style stays in charge):\n"
    "- DO NOT reproduce photographic realism, photographic lighting, depth "
    "  of field, micro-textures, photographic grain, sharpness.\n"
    "- DO NOT reuse the photo's background, surroundings, hands or environment.\n"
    "- DO NOT introduce any photo-derived rendering technique that would "
    "  conflict with the defined comic-book style.\n\n"
    "Output a stylized comic-book illustration of the object, drawn ENTIRELY "
    "in the project's art style on a neutral background, that is recognizably "
    "the SAME object as the one in the photo."
)


_ADDITIONAL_PERSON_PHOTO_LABEL = (
    "ADDITIONAL PERSON LIKENESS REFERENCE (another photo of the same person as above): "
    "combine with the other provided reference photos to build a comprehensive likeness. "
    "Photos may show different angles, lighting, or expressions — extract the structural "
    "features that are consistent across all of them and apply caricaturist stylization."
)

_ADDITIONAL_LOCATION_PHOTO_LABEL = (
    "ADDITIONAL PLACE LIKENESS REFERENCE (another photo of the same location as above): "
    "combine with the other reference photos to understand the full layout, architecture, "
    "and atmosphere of this place. Render in the project's art style."
)

_ADDITIONAL_OBJECT_PHOTO_LABEL = (
    "ADDITIONAL OBJECT LIKENESS REFERENCE (another photo of the same object as above): "
    "combine with the other reference photos to understand the object's full shape, "
    "markings, and proportions. Render in the project's art style."
)

_XAI_ADDITIONAL_PHOTO_LABEL = (
    "ADDITIONAL REFERENCE PHOTO: another image of the same subject as described above. "
    "Combine all provided reference photos to build a complete, accurate likeness."
)


def _generate_image(
    client: OpenAI | None,
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    style_ref: Path | None = None,
    character_photos: list[Path] | None = None,
    location_photos: list[Path] | None = None,
    object_photos: list[Path] | None = None,
    allow_style_copy: bool = False,
    trace_name: str = "ref_image",
) -> dict:
    """Call images.generate() or images.edit() with optional input images.

    When a style-reference PNG is supplied, we switch to images.edit() so the
    model can *see* the target visual style rather than only reading a text
    description. ``character_photo`` / ``location_photo`` / ``object_photo``
    each anchor the likeness of one entity while keeping the defined style in
    charge. If none of the optional inputs are supplied we fall back to the
    cheaper images.generate() path.
    """
    with trace.node(
        trace_name,
        "image_call",
        inputs={
            "style_ref": style_ref,
            "character_photos": len(character_photos or []),
            "location_photos": len(location_photos or []),
            "object_photos": len(object_photos or []),
        },
    ) as tn:
        tn.set_model(image_model.provider, image_model.model)
        tn.set_extra(quality=image_model.quality, allow_style_copy=allow_style_copy)
        result = _generate_image_impl(
            client,
            image_model,
            prompt,
            target,
            style_ref,
            character_photos,
            location_photos,
            object_photos,
            allow_style_copy,
        )
        tn.set_prompt(result["prompt"])
        tn.set_usage(result["usage"])
        tn.set_outputs({"artifact": target, "input_images": result["input_images"]})
        return result


def _generate_image_impl(
    client: OpenAI | None,
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    style_ref: Path | None,
    character_photos: list[Path] | None,
    location_photos: list[Path] | None,
    object_photos: list[Path] | None,
    allow_style_copy: bool,
) -> dict:
    max_entity_photos = XAI_MAX_ENTITY_PHOTOS if image_model.provider == "xai" else OPENAI_MAX_ENTITY_PHOTOS

    inputs: list[tuple[str, bytes, str]] = []
    prompt_prefix_parts: list[str] = []
    xai_prompt_prefix_parts: list[str] = []
    if style_ref is not None and style_ref.exists() and style_ref.stat().st_size > 0:
        inputs.append((style_ref.name, style_ref.read_bytes(), _image_mime_type(style_ref)))
        prompt_prefix_parts.append(style_ref_label(allow_copy=allow_style_copy))
        xai_prompt_prefix_parts.append(_xai_style_ref_label(allow_copy=allow_style_copy))

    char_photos = [p for p in (character_photos or []) if p.exists() and p.stat().st_size > 0][:max_entity_photos]
    for idx, photo in enumerate(char_photos):
        inputs.append((photo.name, photo.read_bytes(), _image_mime_type(photo)))
        if idx == 0:
            prompt_prefix_parts.append(PHOTO_REF_LABEL)
            xai_prompt_prefix_parts.append(_XAI_PHOTO_REF_LABEL)
        else:
            prompt_prefix_parts.append(_ADDITIONAL_PERSON_PHOTO_LABEL)
            xai_prompt_prefix_parts.append(_XAI_ADDITIONAL_PHOTO_LABEL)

    loc_photos = [p for p in (location_photos or []) if p.exists() and p.stat().st_size > 0][:max_entity_photos]
    for idx, photo in enumerate(loc_photos):
        inputs.append((photo.name, photo.read_bytes(), _image_mime_type(photo)))
        if idx == 0:
            prompt_prefix_parts.append(LOCATION_PHOTO_REF_LABEL)
            xai_prompt_prefix_parts.append(_XAI_LOCATION_PHOTO_REF_LABEL)
        else:
            prompt_prefix_parts.append(_ADDITIONAL_LOCATION_PHOTO_LABEL)
            xai_prompt_prefix_parts.append(_XAI_ADDITIONAL_PHOTO_LABEL)

    obj_photos = [p for p in (object_photos or []) if p.exists() and p.stat().st_size > 0][:max_entity_photos]
    for idx, photo in enumerate(obj_photos):
        inputs.append((photo.name, photo.read_bytes(), _image_mime_type(photo)))
        if idx == 0:
            prompt_prefix_parts.append(OBJECT_PHOTO_REF_LABEL)
            xai_prompt_prefix_parts.append(_XAI_OBJECT_PHOTO_REF_LABEL)
        else:
            prompt_prefix_parts.append(_ADDITIONAL_OBJECT_PHOTO_LABEL)
            xai_prompt_prefix_parts.append(_XAI_ADDITIONAL_PHOTO_LABEL)

    if image_model.provider == "xai":
        full_prompt = _build_xai_prompt(xai_prompt_prefix_parts, prompt)
        _generate_xai_image(image_model, full_prompt, target, inputs)
        return {
            "usage": {},
            "prompt": full_prompt,
            "input_images": len(inputs),
        }

    if client is None:
        raise RuntimeError("OpenAI client missing for image generation.")

    if inputs:
        full_prompt = "\n\n".join(prompt_prefix_parts + [prompt])
        result = client.images.edit(
            model=image_model.model,
            image=inputs,
            prompt=full_prompt,
            size=REFERENCE_SIZE,
            quality=image_model.quality,
        )
    else:
        full_prompt = prompt
        result = client.images.generate(
            model=image_model.model,
            prompt=prompt,
            size=REFERENCE_SIZE,
            quality=image_model.quality,
        )
    image_b64 = result.data[0].b64_json
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(base64.b64decode(image_b64))
    versioning.archive_before_write(target, kind="regen")
    tmp.replace(target)
    return {
        "usage": normalise_usage(getattr(result, "usage", None)),
        "prompt": full_prompt,
        "input_images": len(inputs),
    }


_XAI_STYLE_REF_STRICT_LABEL = (
    "INPUT IMAGE 1 IS A STYLE REFERENCE. You must visibly use it for drawing style, palette, line work, stylization, "
    "finish level and visual mood. It is not optional. Do not copy its characters, text, logos, scene, setting, "
    "composition, brands, specific objects or narrative content. Draw only the project's requested subject."
)

_XAI_STYLE_REF_COPY_ALLOWED_LABEL = (
    "INPUT IMAGE 1 IS A STYLE REFERENCE. The user allows close visual emulation of this reference's style and "
    "recognizable visual identity. You must visibly use it to shape the look. Do not render proper names, logos, "
    "watermarks, signatures, titles or verbatim text from the reference."
)

_XAI_PHOTO_REF_LABEL = (
    "PERSON PHOTO REFERENCE: one attached input image is the user's person photo. Preserve the person's likeness: face "
    "shape, proportions, hair, age, build and distinctive features. The generated character should be recognizably the "
    "same person after stylization. Keep the requested comic style and palette; do not copy photo realism, clothing, "
    "pose, background or lighting unless explicitly requested."
)

_XAI_LOCATION_PHOTO_REF_LABEL = (
    "LOCATION PHOTO REFERENCE: one attached input image is the user's place photo. Preserve recognizable architecture, "
    "layout, materials, key landmarks and mood so the generated setting reads as the same place after stylization. "
    "Render it in the requested comic style, with no people copied from the photo and no verbatim signage."
)

_XAI_OBJECT_PHOTO_REF_LABEL = (
    "OBJECT PHOTO REFERENCE: one attached input image is the user's object photo. Preserve shape, proportions, "
    "silhouette, color zones and key markings so the generated object is recognizably the same object after "
    "stylization. Render it as a comic object on a neutral background; do not copy photo realism or surroundings."
)


def _xai_style_ref_label(allow_copy: bool) -> str:
    return _XAI_STYLE_REF_COPY_ALLOWED_LABEL if allow_copy else _XAI_STYLE_REF_STRICT_LABEL


def _build_xai_prompt(prefix_parts: list[str], prompt: str) -> str:
    """Fit Grok image prompts under xAI's 8000-character limit.

    The source prompt can be much longer because OpenAI accepts our full
    reference labels and policy blocks. Grok rejects anything over 8000 chars,
    so keep concise input-image labels and trim the main prompt from the middle:
    the beginning usually names the subject, while the end carries style and
    negative constraints appended by ``_augment_prompt``.
    """
    max_chars = XAI_MAX_PROMPT_CHARS - XAI_PROMPT_MARGIN
    prefix = "\n\n".join(part for part in prefix_parts if part)
    if prefix:
        prompt_budget = max_chars - len(prefix) - 2
        fitted = _trim_middle(prompt, max(0, prompt_budget))
        return f"{prefix}\n\n{fitted}"[:max_chars]
    return _trim_middle(prompt, max_chars)


def _trim_middle(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(XAI_PROMPT_OMISSION):
        return text[:max_chars]
    remaining = max_chars - len(XAI_PROMPT_OMISSION)
    head_chars = max(1, int(remaining * 0.6))
    tail_chars = max(1, remaining - head_chars)
    return f"{text[:head_chars].rstrip()}{XAI_PROMPT_OMISSION}{text[-tail_chars:].lstrip()}"


def _generate_xai_image(
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    inputs: list[tuple[str, bytes, str]],
) -> None:
    payload: dict[str, Any] = {
        "model": image_model.model,
        "prompt": prompt,
        "response_format": "b64_json",
    }
    if image_model.quality == "high":
        payload["resolution"] = "2k"
    else:
        payload["resolution"] = "1k"

    if inputs:
        payload["aspect_ratio"] = "1:1"
        images = [
            {
                "type": "image_url",
                "url": _data_uri(data, mime_type),
            }
            for _name, data, mime_type in inputs[:3]
        ]
        endpoint = "https://api.x.ai/v1/images/edits"
        if len(images) == 1:
            payload["image"] = images[0]
        else:
            payload["images"] = images
    else:
        endpoint = "https://api.x.ai/v1/images/generations"

    response = _xai_image_request(endpoint, payload)
    first = (response.get("data") or [{}])[0]
    image_b64 = first.get("b64_json")
    if image_b64:
        image_bytes = base64.b64decode(image_b64)
    elif first.get("url"):
        with urlopen(first["url"], timeout=120) as image_response:
            image_bytes = image_response.read()
    else:
        raise RuntimeError("xAI image response did not contain b64_json or url.")

    _write_png(target, image_bytes)


def _xai_image_request(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {secret_store.require_secret('XAI_API_KEY')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"xAI image request failed ({exc.code}): {detail}") from exc


def _data_uri(data: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _write_png(target: Path, image_bytes: bytes) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        from io import BytesIO

        with Image.open(BytesIO(image_bytes)) as img:
            img.save(tmp, format="PNG")
    except Exception:
        tmp.write_bytes(image_bytes)
    tmp.replace(target)
