"""Step 2: generate one reference sheet per character and per location."""
from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

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

REFERENCE_SIZE = "1024x1024"


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
    character_photos: dict[str, Path] | None = None,
    location_photos: dict[str, Path] | None = None,
    object_photos: dict[str, Path] | None = None,
    stats_project_dir: Path | None = None,
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
    if not options.generate:
        rep.emit(ProgressEvent(
            step="references",
            phase="skipped",
            message="Génération des références désactivée dans les options.",
        ))
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
            rep.emit(ProgressEvent(
                step="references",
                phase=f"character_{character.id}_skipped",
                message=f"Personnage « {character.name} » déjà sur disque.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": character.id, "kind": "character"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="references",
                phase=f"character_{character.id}",
                message=f"Génération de la référence pour « {character.name} »…",
                current=done,
                total=total,
                extra={"id": character.id, "kind": "character"},
            ))
            prompt = _augment_prompt(
                character.reference_prompt, feedback_store, character.id,
                style=script.style,
            )
            photo = (character_photos or {}).get(character.id)
            started_at, started = start_timer()
            image_stats = _generate_image(
                client, image_model, prompt, target,
                style_ref=style_ref,
                character_photo=photo,
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
            rep.emit(ProgressEvent(
                step="references",
                phase=f"character_{character.id}_done",
                message=f"Référence « {character.name} » générée.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": character.id, "kind": "character"},
            ))
        character.reference_image = target
        if script_path is not None:
            script.save(script_path)

    for location in script.locations:
        flag.check()
        done += 1
        target = loc_dir / f"{location.id}.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="references",
                phase=f"location_{location.id}_skipped",
                message=f"Décor « {location.name} » déjà sur disque.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": location.id, "kind": "location"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="references",
                phase=f"location_{location.id}",
                message=f"Génération de la référence pour le décor « {location.name} »…",
                current=done,
                total=total,
                extra={"id": location.id, "kind": "location"},
            ))
            prompt = _augment_prompt(
                location.reference_prompt, feedback_store, location.id,
                style=script.style,
            )
            photo = (location_photos or {}).get(location.id)
            started_at, started = start_timer()
            image_stats = _generate_image(
                client, image_model, prompt, target,
                style_ref=style_ref,
                location_photo=photo,
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
            rep.emit(ProgressEvent(
                step="references",
                phase=f"location_{location.id}_done",
                message=f"Référence « {location.name} » générée.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": location.id, "kind": "location"},
            ))
        location.reference_image = target
        if script_path is not None:
            script.save(script_path)

    for obj in script.objects:
        flag.check()
        done += 1
        target = obj_dir / f"{obj.id}.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="references",
                phase=f"object_{obj.id}_skipped",
                message=f"Objet « {obj.name} » déjà sur disque.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": obj.id, "kind": "object"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="references",
                phase=f"object_{obj.id}",
                message=f"Génération de la référence pour l'objet « {obj.name} »…",
                current=done,
                total=total,
                extra={"id": obj.id, "kind": "object"},
            ))
            prompt = _augment_prompt(
                obj.reference_prompt, feedback_store, obj.id,
                style=script.style,
            )
            photo = (object_photos or {}).get(obj.id)
            started_at, started = start_timer()
            image_stats = _generate_image(
                client, image_model, prompt, target,
                style_ref=style_ref,
                object_photo=photo,
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
            rep.emit(ProgressEvent(
                step="references",
                phase=f"object_{obj.id}_done",
                message=f"Référence « {obj.name} » générée.",
                current=done,
                total=total,
                artifact=str(target),
                extra={"id": obj.id, "kind": "object"},
            ))
        obj.reference_image = target
        if script_path is not None:
            script.save(script_path)

    rep.emit(ProgressEvent(
        step="references",
        phase="done",
        message="Toutes les références sont prêtes.",
        current=total,
        total=total,
    ))
    return script


def _augment_prompt(
    prompt: str, feedback_store: FeedbackStore | None, target: str,
    style: Style | None = None,
) -> str:
    parts = [prompt, IMAGE_CONSTRAINTS]
    if style is not None:
        parts.append(_style_enforcement_block(style))
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


def _client(image_model: ImageModelConfig) -> OpenAI:
    if image_model.provider != "openai":
        raise NotImplementedError(
            f"Provider '{image_model.provider}' is not yet supported."
        )
    return secret_store.openai_client()


STYLE_REF_LABEL = (
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
    "  level of finish, same degree of anatomical distortion.\n\n"
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


def _generate_image(
    client: OpenAI,
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    style_ref: Path | None = None,
    character_photo: Path | None = None,
    location_photo: Path | None = None,
    object_photo: Path | None = None,
) -> dict:
    """Call images.generate() or images.edit() with optional input images.

    When a style-reference PNG is supplied, we switch to images.edit() so the
    model can *see* the target visual style rather than only reading a text
    description. ``character_photo`` / ``location_photo`` / ``object_photo``
    each anchor the likeness of one entity while keeping the defined style in
    charge. If none of the optional inputs are supplied we fall back to the
    cheaper images.generate() path.
    """
    inputs: list[tuple[str, bytes, str]] = []
    prompt_prefix_parts: list[str] = []
    if style_ref is not None and style_ref.exists() and style_ref.stat().st_size > 0:
        inputs.append((style_ref.name, style_ref.read_bytes(), "image/png"))
        prompt_prefix_parts.append(STYLE_REF_LABEL)
    if (
        character_photo is not None
        and character_photo.exists()
        and character_photo.stat().st_size > 0
    ):
        inputs.append(
            (character_photo.name, character_photo.read_bytes(), "image/png")
        )
        prompt_prefix_parts.append(PHOTO_REF_LABEL)
    if (
        location_photo is not None
        and location_photo.exists()
        and location_photo.stat().st_size > 0
    ):
        inputs.append(
            (location_photo.name, location_photo.read_bytes(), "image/png")
        )
        prompt_prefix_parts.append(LOCATION_PHOTO_REF_LABEL)
    if (
        object_photo is not None
        and object_photo.exists()
        and object_photo.stat().st_size > 0
    ):
        inputs.append(
            (object_photo.name, object_photo.read_bytes(), "image/png")
        )
        prompt_prefix_parts.append(OBJECT_PHOTO_REF_LABEL)

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
    tmp.replace(target)
    return {
        "usage": normalise_usage(getattr(result, "usage", None)),
        "prompt": full_prompt,
        "input_images": len(inputs),
    }
