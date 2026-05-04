"""Step 4: generate each BD page as a single image with gpt-image-2, then assemble."""
from __future__ import annotations

import base64
from pathlib import Path
from textwrap import dedent

from openai import OpenAI
from PIL import Image

from . import secret_store
from .feedback import FeedbackStore, feedback_block
from .image_rules import IMAGE_CONSTRAINTS
from .references import STYLE_REF_LABEL as _STYLE_REF_LABEL
from .references import _style_enforcement_block
from .models import (
    BackCover,
    BdGenScript,
    Cover,
    GenerationOptions,
    ImageModelConfig,
    Page,
)
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)
from .stats import normalise_usage, record_event, start_timer, stop_timer

PAGE_SIZE = "1024x1536"


def compose_output(
    script: BdGenScript,
    options: GenerationOptions,
    pages_dir: Path,
    feedback_store: FeedbackStore | None = None,
    force: bool = False,
    reporter: ProgressReporter | None = None,
    interrupt: InterruptFlag | None = None,
    style_ref: Path | None = None,
    stats_project_dir: Path | None = None,
) -> Path:
    """Generate one image per page (full-page render with bubbles), then assemble.

    Skips pages whose final PNG already exists on disk so the step is resumable
    (unless ``force`` is True). When ``feedback_store`` is provided, any
    feedback recorded for a page is appended to its prompt. ``reporter``
    receives structured progress events; ``interrupt`` is checked between each
    page so generation can stop cleanly. Returns the path to the assembled
    output (PDF) or to the pages directory if output_format is "images".
    """
    rep = _coerce_reporter(reporter)
    flag = _coerce_flag(interrupt)
    pages_dir.mkdir(parents=True, exist_ok=True)
    options.output_path.parent.mkdir(parents=True, exist_ok=True)

    client = _client(options.image_model)

    total = (1 if script.cover else 0) + len(script.pages) + (1 if script.back_cover else 0)
    done = 0

    cover_image: Path | None = None
    if script.cover is not None:
        flag.check()
        done += 1
        cover_image = pages_dir / "cover.png"
        if not force and _is_complete(cover_image):
            rep.emit(ProgressEvent(
                step="compose", phase="cover_skipped",
                message="Couverture déjà sur disque.",
                current=done, total=total, artifact=str(cover_image),
                extra={"id": "cover"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="compose", phase="cover",
                message="Génération de la couverture…",
                current=done, total=total, extra={"id": "cover"},
            ))
            started_at, started = start_timer()
            image_stats = _generate_cover(
                client, options.image_model, script, script.cover,
                cover_image, feedback_store, style_ref=style_ref,
            )
            record_event(
                stats_project_dir,
                step="compose",
                target_id="cover",
                target_kind="cover",
                operation="compose_cover",
                provider=options.image_model.provider,
                model=options.image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=cover_image,
                extra={"quality": options.image_model.quality},
            )
            rep.emit(ProgressEvent(
                step="compose", phase="cover_done",
                message="Couverture générée.",
                current=done, total=total, artifact=str(cover_image),
                extra={"id": "cover"},
            ))

    page_images: list[Path] = []
    for page in script.pages:
        flag.check()
        done += 1
        target = pages_dir / f"page_{page.page_number:02d}.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="compose", phase=f"page_{page.page_number}_skipped",
                message=f"Planche {page.page_number} déjà sur disque.",
                current=done, total=total, artifact=str(target),
                extra={"id": f"page_{page.page_number}"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="compose", phase=f"page_{page.page_number}",
                message=f"Génération de la planche {page.page_number}…",
                current=done, total=total,
                extra={"id": f"page_{page.page_number}"},
            ))
            started_at, started = start_timer()
            image_stats = _generate_page(
                client, options.image_model, script, page, target,
                feedback_store, style_ref=style_ref,
            )
            record_event(
                stats_project_dir,
                step="compose",
                target_id=f"page_{page.page_number}",
                target_kind="page",
                operation="compose_page",
                provider=options.image_model.provider,
                model=options.image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=target,
                extra={
                    "quality": options.image_model.quality,
                    "panels": len(page.panels),
                    "dialogs": sum(len(panel.dialogs) for panel in page.panels),
                },
            )
            rep.emit(ProgressEvent(
                step="compose", phase=f"page_{page.page_number}_done",
                message=f"Planche {page.page_number} générée.",
                current=done, total=total, artifact=str(target),
                extra={"id": f"page_{page.page_number}"},
            ))
        page_images.append(target)

    back_image: Path | None = None
    if script.back_cover is not None:
        flag.check()
        done += 1
        back_image = pages_dir / "back.png"
        if not force and _is_complete(back_image):
            rep.emit(ProgressEvent(
                step="compose", phase="back_skipped",
                message="4ᵉ de couverture déjà sur disque.",
                current=done, total=total, artifact=str(back_image),
                extra={"id": "back"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="compose", phase="back",
                message="Génération de la 4ᵉ de couverture…",
                current=done, total=total, extra={"id": "back"},
            ))
            started_at, started = start_timer()
            image_stats = _generate_back(
                client, options.image_model, script, script.back_cover,
                back_image, feedback_store, style_ref=style_ref,
            )
            record_event(
                stats_project_dir,
                step="compose",
                target_id="back",
                target_kind="back_cover",
                operation="compose_back_cover",
                provider=options.image_model.provider,
                model=options.image_model.model,
                timer=stop_timer(started_at, started),
                usage=image_stats["usage"],
                prompt=image_stats["prompt"],
                input_images=image_stats["input_images"],
                artifact=back_image,
                extra={"quality": options.image_model.quality},
            )
            rep.emit(ProgressEvent(
                step="compose", phase="back_done",
                message="4ᵉ de couverture générée.",
                current=done, total=total, artifact=str(back_image),
                extra={"id": "back"},
            ))

    full_sequence = (
        ([cover_image] if cover_image else [])
        + page_images
        + ([back_image] if back_image else [])
    )

    if options.output_format == "pdf":
        rep.emit(ProgressEvent(
            step="compose", phase="assembling",
            message=f"Assemblage de {len(full_sequence)} images en PDF…",
        ))
        _assemble_pdf(full_sequence, options.output_path)
        rep.emit(ProgressEvent(
            step="compose", phase="done",
            message="PDF assemblé.",
            artifact=str(options.output_path),
        ))
        return options.output_path
    if options.output_format == "images":
        rep.emit(ProgressEvent(
            step="compose", phase="done",
            message=f"Images sauvegardées dans {pages_dir}",
            artifact=str(pages_dir),
        ))
        return pages_dir
    raise NotImplementedError(
        f"Output format '{options.output_format}' is not yet supported."
    )


def _prepend_style_ref(
    refs_with_labels: list[tuple[Path, str]],
    style_ref: Path | None,
) -> list[tuple[Path, str]]:
    """Inject the style reference as the very first input image if provided."""
    if style_ref and style_ref.exists() and style_ref.stat().st_size > 0:
        return [(style_ref, _STYLE_REF_LABEL)] + refs_with_labels
    return refs_with_labels


def _generate_page(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    page: Page,
    target: Path,
    feedback_store: FeedbackStore | None = None,
    style_ref: Path | None = None,
) -> dict:
    """Call gpt-image-2 with all relevant character/location refs as input images."""
    refs_with_labels = _prepend_style_ref(
        _collect_refs(script, page), style_ref
    )
    refs = [path for path, _ in refs_with_labels]
    labels = [label for _, label in refs_with_labels]
    prompt = _build_page_prompt(script, page, labels)
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("compose", f"page_{page.page_number}")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    return _call_image(client, image_model, prompt, target, refs)


def _collect_refs(
    script: BdGenScript, page: Page
) -> list[tuple[Path, str]]:
    """Collect refs for this page as (path, label) pairs.

    The label describes what the input image is and how the model should treat
    it. The order matches the input list order, so the prompt can refer to
    images by index ("the 1st input image is the character sheet for X").
    """
    char_ids: set[str] = set()
    loc_ids: set[str] = set()
    obj_ids: set[str] = set()
    for panel in page.panels:
        char_ids.update(panel.characters)
        loc_ids.add(panel.location)
        obj_ids.update(panel.objects)

    refs: list[tuple[Path, str]] = []
    for cid in sorted(char_ids):
        char = script.character_by_id(cid)
        ref_path = _existing_reference_path(
            script, "characters", cid, char.reference_image if char else None
        )
        if char and ref_path:
            label = (
                f'Character sheet for "{char.name}" — this is the canonical '
                f"reference for this character's face, hair, eyes, body type "
                f"and outfit. Match it EXACTLY in every panel they appear in."
            )
            refs.append((ref_path, label))
    for lid in sorted(loc_ids):
        loc = script.location_by_id(lid)
        ref_path = _existing_reference_path(
            script, "locations", lid, loc.reference_image if loc else None
        )
        if loc and ref_path:
            label = (
                f'Establishing shot of "{loc.name}" — match its mood, '
                f"atmosphere and visual elements when this location appears."
            )
            refs.append((ref_path, label))
    for oid in sorted(obj_ids):
        obj = script.object_by_id(oid)
        ref_path = _existing_reference_path(
            script, "objects", oid, obj.reference_image if obj else None
        )
        if obj and ref_path:
            label = (
                f'Object reference for "{obj.name}" — this is the canonical '
                f"stylized appearance of this object. Whenever it is visible "
                f"in a panel, match its shape, key markings and silhouette "
                f"EXACTLY so it stays recognizable across the album."
            )
            refs.append((ref_path, label))

    return refs


def _build_page_prompt(
    script: BdGenScript, page: Page, ref_labels: list[str] | None = None
) -> str:
    """Build the full page-generation prompt with publication specs and bubble guidance."""
    style = script.style
    language = script.metadata.language
    page_n = page.page_number
    folio_side = "right" if page_n % 2 == 1 else "left"

    panels_text: list[str] = []
    for panel in page.panels:
        loc = script.location_by_id(panel.location)
        loc_text = f"{loc.name} - {loc.description}" if loc else panel.location
        chars = [script.character_by_id(c) for c in panel.characters]
        chars_text = ", ".join(c.name for c in chars if c) or "(no character)"
        objs = [script.object_by_id(o) for o in panel.objects]
        objs_text = ", ".join(o.name for o in objs if o) or "(no object)"

        dialogs_block = ""
        if panel.dialogs:
            lines = []
            for d in panel.dialogs:
                speaker = script.character_by_id(d.speaker)
                speaker_name = speaker.name if speaker else d.speaker
                if d.type == "narration":
                    # Narration captions are NOT speech bubbles — render as a
                    # rectangular caption box with no tail.
                    lines.append(
                        f'    - CAPTION (narration, no speaker, no tail): "{d.text}"'
                    )
                else:
                    lines.append(
                        f'    - SPEAKER="{speaker_name}" (type={d.type}): "{d.text}"\n'
                        f"      → Bubble tail MUST originate from {speaker_name}'s mouth area "
                        f"(or from {speaker_name} for thought clouds). Never let the tail point "
                        f"to a different character."
                    )
            dialogs_block = "\n  Dialogs:\n" + "\n".join(lines)

        narration_block = (
            f"\n  Narration caption: {panel.narration}" if panel.narration else ""
        )
        sfx_block = (
            f"\n  Sound effects: {', '.join(panel.sound_effects)}"
            if panel.sound_effects
            else ""
        )

        panels_text.append(
            f"Panel {panel.panel_number} ({panel.size or 'medium'}, "
            f"{panel.shot or 'medium shot'}):\n"
            f"  Location: {loc_text}\n"
            f"  Characters in frame: {chars_text}\n"
            f"  Objects in frame: {objs_text}\n"
            f"  Scene: {panel.scene_description}"
            f"{narration_block}{dialogs_block}{sfx_block}"
        )

    header = IMAGE_CONSTRAINTS + "\n" + dedent(f"""\
        Generate page {page_n} of a comic book ("bande dessinée"), as a single
        publication-ready image containing every panel of this page.

        GLOBAL STYLE:
        - Art style: {style.art_style}
        - Color palette: {style.color_palette or "as appropriate to the mood"}
        - Line work: {style.line_work or "clean black ink, consistent thickness"}
        - Mood: {style.mood or "neutral"}
        - Stylization level: {style.stylization_level or "moderately stylized"}
        - Panel borders: {style.panel_borders or "crisp, consistent thickness, fully closed black ink rectangles (or shapes per the layout)"}
        - Speech bubbles: {style.speech_bubbles or "clean white bubbles with a thin black outline, matching the line-work weight"}
        - Character rendering: {style.character_rendering or "consistent with the art style above"}
        - HANDS & ARMS (NON-NEGOTIABLE): every character in every panel MUST
          have anatomically correct hands (exactly 5 fingers per hand: 4 fingers
          + 1 opposable thumb) and arms (one elbow per arm, bending naturally).
          Before finalizing each panel, COUNT the fingers on every visible hand.
          If any hand has fewer or more than 5 fingers, redraw it. Prefer poses
          where hands are clearly visible (at sides, holding props, gesturing)
          over complex foreshortening that risks errors.
        {f"- NEGATIVE CONSTRAINTS: {style.negative_constraints}" if style.negative_constraints else ""}

        PAGE LAYOUT:
        {page.layout or "balanced grid"}

        This page contains {len(page.panels)} panel(s). Arrange them following
        the layout description above.

        PANELS:
        """)

    footer = dedent(f"""

        PUBLICATION SPECS:
        - Format: standard album BD portrait, 21x28cm aspect ratio.
        - Bleed (fond perdu): artwork extends 5mm beyond the trim line on all
          sides; no white margin around the page.
        - Safety margin (zone tranquille): keep critical content (faces, eyes,
          text) within 5mm inside the trim line.
        - Inter-panel gutters: approximately 5mm uniform white space between
          panels.
        - Folio: render the page number "{page_n}" in sober typography in the
          bottom {folio_side} corner of the page.

        TEXT RENDERING (language: {language}):
        - Render all dialog text inside speech bubbles in {language}.
        - Render all narration captions in {language}.
        - Render sound effects as bold stylized lettering integrated into the
          scene (not inside a bubble).
        - Bubble shapes by dialog type:
          * speech    -> rounded bubble with a tail pointing toward the speaker
          * thought   -> cloud-shaped bubble with small trailing bubbles drifting
                         from the speaker's head (no straight tail)
          * shout     -> jagged spiky bubble with a tail toward the speaker
          * whisper   -> dashed-outline bubble with a tail toward the speaker
          * narration -> rectangular caption box (yellow or off-white), pinned
                         to a panel edge or corner, NO tail, NO speaker
        - SPEAKER ATTRIBUTION — NON-NEGOTIABLE:
          * Each bubble MUST be visually anchored to the EXACT character named
            in its `SPEAKER="..."` field. Match the name to the character sheet
            you were given as input.
          * The tail of every speech/shout/whisper bubble MUST terminate at the
            named speaker's mouth (or very close to it), and MUST NOT touch,
            cross, or visually associate with any other character in the panel.
          * For thought clouds, the trailing small bubbles MUST drift from the
            named speaker's head — never from another character.
          * If two or more characters are close together, place the bubble on
            the SAME side as the speaker so the tail's target is unambiguous;
            shorten or curve the tail rather than letting it cut across or
            graze a non-speaker.
          * Verify each bubble before finalizing: trace each tail back — does
            it land on the character whose name appears in SPEAKER? If not,
            reposition the bubble or redraw the tail until it does.
        - Bubble reading order: top-to-bottom, left-to-right within the panel.
          When that order conflicts with correct speaker attribution, attribution
          wins — never break the SPEAKER → tail link to improve flow.
        - Lettering style: clean comic hand-lettering, black ink on white bubble
          background, comfortably readable size.

        """) + _build_refs_section(ref_labels)

    return header + "\n\n".join(panels_text) + footer + "\n\n" + _style_enforcement_block(style)


def _build_refs_section(ref_labels: list[str] | None) -> str:
    """Render the INPUT IMAGES section, enumerating each input by index.

    Telling the model exactly what each input image is — and in what order —
    significantly improves character and location consistency vs. dumping the
    images without context.
    """
    if not ref_labels:
        return "INPUT IMAGES:\n  (none provided)\n"
    lines = ["INPUT IMAGES (in this exact order):"]
    for i, label in enumerate(ref_labels, start=1):
        lines.append(f"  {i}. {label}")
    lines.append("")
    lines.append(
        "Treat each input image as authoritative for what it describes. "
        "Character sheets are NON-NEGOTIABLE references — never invent or drift "
        "from a character's appearance across panels."
    )
    return "\n".join(lines) + "\n"


def _generate_cover(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    cover: Cover,
    target: Path,
    feedback_store: FeedbackStore | None = None,
    style_ref: Path | None = None,
) -> dict:
    refs_with_labels = _prepend_style_ref(
        _collect_album_refs(script, "cover"), style_ref
    )
    refs = [p for p, _ in refs_with_labels]
    labels = [l for _, l in refs_with_labels]
    prompt = _build_cover_prompt(script, cover, labels)
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("compose", "cover")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    return _call_image(client, image_model, prompt, target, refs)


def _generate_back(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    back: BackCover,
    target: Path,
    feedback_store: FeedbackStore | None = None,
    style_ref: Path | None = None,
) -> dict:
    refs_with_labels = _prepend_style_ref(
        _collect_album_refs(script, "back"), style_ref
    )
    refs = [p for p, _ in refs_with_labels]
    labels = [l for _, l in refs_with_labels]
    prompt = _build_back_prompt(script, back, labels)
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("compose", "back")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    return _call_image(client, image_model, prompt, target, refs)


def _collect_album_refs(
    script: BdGenScript,
    kind: str,
) -> list[tuple[Path, str]]:
    """Collect refs for the cover/back: every character + every object."""
    refs: list[tuple[Path, str]] = []
    for c in script.characters:
        ref_path = _existing_reference_path(script, "characters", c.id, c.reference_image)
        if ref_path:
            label = (
                f'Character sheet for "{c.name}" — match this character\'s '
                f"face, hair, eyes, body type and outfit EXACTLY if they "
                f"appear on the {kind}."
            )
            refs.append((ref_path, label))
    for o in script.objects:
        ref_path = _existing_reference_path(script, "objects", o.id, o.reference_image)
        if ref_path:
            label = (
                f'Object reference for "{o.name}" — match its shape, key '
                f"markings and silhouette EXACTLY if it appears on the {kind}."
            )
            refs.append((ref_path, label))
    return refs


def _existing_reference_path(
    script: BdGenScript,
    folder: str,
    ref_id: str,
    current: Path | str | None,
) -> Path | None:
    if current:
        p = Path(current)
        if p.exists() and p.stat().st_size > 0:
            return p
    fallback = script.project_dir() / "references" / folder / f"{ref_id}.png"
    if fallback.exists() and fallback.stat().st_size > 0:
        return fallback
    return None


def _call_image(
    client: OpenAI,
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    refs: list[Path],
) -> dict:
    if refs:
        files = [(p.name, p.read_bytes(), "image/png") for p in refs]
        edit_kwargs = dict(
            model=image_model.model,
            image=files,
            prompt=prompt,
            size=PAGE_SIZE,
            quality=image_model.quality,
        )
        # `input_fidelity` is a gpt-image-1 knob; gpt-image-2 rejects it with
        # 400 invalid_input_fidelity_model. Only opt in on the older model.
        if image_model.model == "gpt-image-1":
            edit_kwargs["input_fidelity"] = "high"
        result = client.images.edit(**edit_kwargs)
    else:
        result = client.images.generate(
            model=image_model.model,
            prompt=prompt,
            size=PAGE_SIZE,
            quality=image_model.quality,
        )
    image_b64 = result.data[0].b64_json
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(base64.b64decode(image_b64))
    tmp.replace(target)
    return {
        "usage": normalise_usage(getattr(result, "usage", None)),
        "prompt": prompt,
        "input_images": len(refs),
    }


def _build_cover_prompt(
    script: BdGenScript, cover: Cover, ref_labels: list[str] | None = None
) -> str:
    style = script.style
    language = script.metadata.language
    base = IMAGE_CONSTRAINTS + "\n" + dedent(f"""\
        Generate the FRONT COVER of a comic book album, as a single
        publication-ready image, portrait format.

        GLOBAL STYLE:
        - Art style: {style.art_style}
        - Color palette: {style.color_palette or "as appropriate"}
        - Line work: {style.line_work or "clean black ink"}
        - Mood: {style.mood or "neutral"}
        - Stylization level: {style.stylization_level or "moderately stylized"}
        - Character rendering: {style.character_rendering or "consistent with the art style above"}
        {f"- NEGATIVE CONSTRAINTS: {style.negative_constraints}" if style.negative_constraints else ""}

        - HANDS & ARMS (NON-NEGOTIABLE): every character MUST have anatomically
          correct hands (exactly 5 fingers: 4 + 1 thumb) and arms (one natural
          elbow joint per arm). Count fingers before finalizing.

        COVER ILLUSTRATION:
        {cover.scene_description}

        TYPOGRAPHY (language: {language}) — render EXACTLY these strings, no others:
        - Title: "{script.metadata.title}" — placement: {cover.title_placement or "top center, large display lettering"}
        - Author: "{script.metadata.author}" — secondary typography below or above the title
        - Subtitle: {cover.subtitle or "(none — leave out)"}
        - Tagline: {cover.tagline or "(none — leave out)"}

        STRICT TEXT RULE: the ONLY readable text allowed on this cover is the
        title, author, and (if non-empty above) the subtitle and tagline. DO
        NOT add any other lettering — no series tag, no issue number, no
        publisher name, no "ce mois-ci ...", no headline, no decorative
        wording, no logos with text. If a style reference image is provided,
        IGNORE every word it contains; treat its lettering as decorative
        texture you must NOT transcribe.

        PUBLICATION SPECS:
        - Format: standard album BD portrait, 21x28cm aspect ratio
        - Bleed (fond perdu): full bleed, no white margin
        - Safety margin: keep title and critical content within 5mm inside the trim
        - Eye-catching composition: the main illustration must dominate
        - NO folio (no page number on the cover)

        TEXT RENDERING:
        - All text in {language}
        - Typography integrated harmoniously with the illustration style

        """) + _build_refs_section(ref_labels) + "\n\n" + _style_enforcement_block(style)
    return base


def _ai_disclaimer(language: str) -> str:
    """Return the mandatory AI-assistance + fictional-similarity disclaimer.

    Hard-coded translations so the legal wording stays correct verbatim. Falls
    back to French when the language isn't pre-translated — the user can
    always retouch the back cover if they need a custom wording.
    """
    fr = (
        "Bande dessinée réalisée avec l'assistance de BdGEN, un outil "
        "d'intelligence artificielle générative. Toute ressemblance avec "
        "des personnes, lieux, situations ou œuvres existants ne serait "
        "que pure coïncidence."
    )
    en = (
        "Comic book created with the assistance of BdGEN, a generative "
        "artificial-intelligence tool. Any resemblance to actual persons, "
        "places, situations, or existing works is purely coincidental."
    )
    return {"fr": fr, "en": en}.get((language or "fr").lower(), fr)


def _build_back_prompt(
    script: BdGenScript, back: BackCover, ref_labels: list[str] | None = None
) -> str:
    style = script.style
    language = script.metadata.language
    disclaimer = _ai_disclaimer(language)
    base = IMAGE_CONSTRAINTS + "\n" + dedent(f"""\
        Generate the BACK COVER of a comic book album, as a single
        publication-ready image, portrait format.

        GLOBAL STYLE:
        - Art style: {style.art_style}
        - Color palette: {style.color_palette or "as appropriate, consistent with the front cover"}
        - Mood: {style.mood or "neutral"}
        - Stylization level: {style.stylization_level or "moderately stylized"}
        - Character rendering: {style.character_rendering or "consistent with the art style above"}
        {f"- NEGATIVE CONSTRAINTS: {style.negative_constraints}" if style.negative_constraints else ""}

        SYNOPSIS BLURB (render this exact text, language: {language}):
        \"\"\"
        {back.synopsis_blurb}
        \"\"\"

        OPTIONAL ILLUSTRATION:
        {back.scene_description or "(no illustration; keep the back primarily textual with a decorative background)"}

        TAGLINE: {back.tagline or "(none)"}

        MANDATORY AI-ASSISTANCE DISCLAIMER (render this EXACT text verbatim, in {language}):
        \"\"\"
        {disclaimer}
        \"\"\"
        - Place the disclaimer as a discreet line of fine print along the bottom
          of the page, ABOVE the two reserved empty zones described below and
          spanning the horizontal space BETWEEN them (centered between the
          publisher-logo zone on the left and the barcode zone on the right).
        - Use a small, sober, easily readable typeface (≈ 7–8 pt equivalent).
          Single line if it fits, otherwise two lines max, justified or
          centered. Black ink on the page background.
        - Do NOT translate, paraphrase, abbreviate or split this text across
          unrelated areas. Render it once, exactly as given.

        LAYOUT:
        - The synopsis blurb is the main element, set as readable body text in the
          central area
        - {back.layout_notes or "Standard back-cover layout with reserved zones for the publisher logo (bottom-left) and barcode (bottom-right)"}
        - Title and author may be subtly repeated at the top

        RESERVED EMPTY ZONES — MUST BE LEFT BLANK WHITE:
        - Bottom-right corner: a clean WHITE rectangular space approximately
          35mm wide x 22mm tall (standard EAN-13 barcode footprint). This area
          MUST be empty white background — DO NOT draw any barcode lines, do
          NOT print any digits, do NOT add an ISBN number, do NOT draw a frame
          around it. Just untouched white space waiting for the real barcode
          to be added later by the publisher.
        - Bottom-left corner (or wherever space allows near the bottom): a
          clean WHITE rectangular space approximately 30mm x 30mm reserved for
          the publisher logo. This area MUST be empty white background — DO NOT
          invent a logo, mascot, star, sun, swirl, monogram, or any decorative
          element. Do NOT print "votre logo", "logo éditeur", "publisher" or
          any placeholder text. Just untouched white space.
        - These two reserved zones are MANDATORY and NON-NEGOTIABLE. Treat them
          as forbidden surfaces — no ink, no pixels, no decoration, no text.

        PUBLICATION SPECS:
        - Format: standard album BD portrait, 21x28cm aspect ratio
        - Bleed (fond perdu): full bleed for the artwork; the two reserved
          empty zones above stay white regardless
        - Safety margin: 5mm inside trim
        - NO folio

        TEXT RENDERING:
        - All text in {language}
        - Body text in clean readable typography
        - Maintain visual consistency with the front cover style
        - The ONLY text on this back cover is: the optional title/author repeat
          at the top, the synopsis blurb, the optional tagline, and the
          MANDATORY AI-assistance disclaimer at the bottom. NOTHING ELSE —
          no fake ISBN digits, no fake publisher name, no placeholder phrases.

        """) + _build_refs_section(ref_labels) + "\n\n" + _style_enforcement_block(style)
    return base


def _client(image_model: ImageModelConfig) -> OpenAI:
    if image_model.provider == "openai":
        return secret_store.openai_client()
    raise NotImplementedError(
        f"Provider '{image_model.provider}' is not yet supported."
    )


def _is_complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _assemble_pdf(page_images: list[Path], output_path: Path) -> None:
    """Save all page PNGs into a single multi-page PDF via Pillow."""
    if not page_images:
        raise RuntimeError("No pages to assemble.")
    images = [Image.open(p).convert("RGB") for p in page_images]
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        format="PDF",
    )
