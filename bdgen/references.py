"""Step 2: generate one reference sheet per character and per location."""
from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from .feedback import FeedbackStore, feedback_block
from .image_rules import IMAGE_CONSTRAINTS
from .models import (
    BdGenScript,
    ImageModelConfig,
    ReferencesOptions,
)
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)

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
) -> BdGenScript:
    """Generate every character and location reference sheet.

    Saves images under ``{options.output_dir}/{characters|locations}/{id}.png`` and
    fills the matching ``reference_image`` field on the script. Resumable: skips any
    entry whose target PNG already exists on disk and is non-empty (unless ``force``
    is True). When ``script_path`` is provided, the script JSON is re-saved after
    each successful generation so progress survives a crash. When ``feedback_store``
    is provided, any feedback recorded for a given character/location is appended to
    its prompt. ``reporter`` receives structured progress events; ``interrupt`` is
    checked between each character/location so generation can stop cleanly.
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
    char_dir.mkdir(parents=True, exist_ok=True)
    loc_dir.mkdir(parents=True, exist_ok=True)

    client = _client(image_model)

    total = len(script.characters) + len(script.locations)
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
                character.reference_prompt, feedback_store, character.id
            )
            _generate_image(client, image_model, prompt, target, style_ref=style_ref)
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
                location.reference_prompt, feedback_store, location.id
            )
            _generate_image(client, image_model, prompt, target, style_ref=style_ref)
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

    rep.emit(ProgressEvent(
        step="references",
        phase="done",
        message="Toutes les références sont prêtes.",
        current=total,
        total=total,
    ))
    return script


def _augment_prompt(
    prompt: str, feedback_store: FeedbackStore | None, target: str
) -> str:
    parts = [prompt, IMAGE_CONSTRAINTS]
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("references", target)
        if feedbacks:
            parts.append(feedback_block(feedbacks))
    return "\n\n".join(parts)


def _is_complete(path: Path) -> bool:
    """A reference is considered complete only if the file exists and is non-empty."""
    return path.exists() and path.stat().st_size > 0


def _client(image_model: ImageModelConfig) -> OpenAI:
    if image_model.provider != "openai":
        raise NotImplementedError(
            f"Provider '{image_model.provider}' is not yet supported."
        )
    return OpenAI()


STYLE_REF_LABEL = (
    "STYLE REFERENCE (this input image): this single image defines the "
    "complete visual style, artistic approach, line work, coloring technique, "
    "and aesthetic for the entire project. Study it carefully. Your output "
    "MUST match its style — including line quality, coloring method, level of "
    "detail, body proportions, and overall visual tone. Do NOT copy its "
    "content or characters; replicate ONLY its style."
)


def _generate_image(
    client: OpenAI,
    image_model: ImageModelConfig,
    prompt: str,
    target: Path,
    style_ref: Path | None = None,
) -> None:
    """Call images.generate() or images.edit() (when a style reference is provided).

    When a style-reference PNG is supplied, we switch to images.edit() so the
    model can *see* the target visual style rather than only reading a text
    description. This is significantly more reliable for unusual or non-default
    artistic styles (sketchy indie BD, limited palettes, etc.).
    """
    if style_ref is not None and style_ref.exists() and style_ref.stat().st_size > 0:
        full_prompt = STYLE_REF_LABEL + "\n\n" + prompt
        result = client.images.edit(
            model=image_model.model,
            image=[(style_ref.name, style_ref.read_bytes(), "image/png")],
            prompt=full_prompt,
            size=REFERENCE_SIZE,
            quality=image_model.quality,
        )
    else:
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
