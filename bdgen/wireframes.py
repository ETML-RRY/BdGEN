"""Step 3 (optional): generate one low-resolution wireframe per page.

These wireframes capture the full page layout (panel borders, rough scene
sketches inside each panel, no text). They serve two purposes:

1. **Visual validation** before paying for the high-quality compose step:
   the user can eyeball the page composition cheaply.
2. **Layout guide** for the compose step: when wireframes exist on disk,
   compose injects them as additional reference inputs to gpt-image-2.
"""
from __future__ import annotations

import base64
from pathlib import Path
from textwrap import dedent

from openai import OpenAI

from .feedback import FeedbackStore, feedback_block
from .image_rules import IMAGE_CONSTRAINTS
from .models import BackCover, BdGenScript, Cover, GenerationOptions, ImageModelConfig, Page
from .progress import (
    InterruptFlag,
    ProgressEvent,
    ProgressReporter,
    _coerce_flag,
    _coerce_reporter,
)

WIREFRAME_SIZE = "1024x1536"
WIREFRAME_QUALITY = "low"


def generate_wireframes(
    script: BdGenScript,
    options: GenerationOptions,
    output_dir: Path,
    feedback_store: FeedbackStore | None = None,
    force: bool = False,
    reporter: ProgressReporter | None = None,
    interrupt: InterruptFlag | None = None,
) -> None:
    """Generate one low-res wireframe per page showing the full panel layout.

    Idempotent: skips any page whose wireframe PNG already exists on disk
    (unless ``force`` is True). Writes are atomic. When ``feedback_store`` is
    provided, any feedback recorded for a page is appended to its prompt.
    ``reporter`` receives structured progress events; ``interrupt`` is checked
    between each page so generation can stop cleanly.
    """
    rep = _coerce_reporter(reporter)
    flag = _coerce_flag(interrupt)
    output_dir.mkdir(parents=True, exist_ok=True)
    client = _client(options.image_model)

    targets: list[tuple[str, str, Path]] = []  # (kind, label, path)
    if script.cover is not None:
        targets.append(("cover", "Couverture", output_dir / "cover.png"))
    for page in script.pages:
        targets.append((
            f"page_{page.page_number}",
            f"Planche {page.page_number}",
            output_dir / f"page_{page.page_number:02d}.png",
        ))
    if script.back_cover is not None:
        targets.append(("back", "Quatrième de couverture", output_dir / "back.png"))
    total = len(targets)
    done = 0

    if script.cover is not None:
        flag.check()
        done += 1
        target = output_dir / "cover.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="wireframes", phase="cover_skipped",
                message="Esquisse couverture déjà sur disque.",
                current=done, total=total, artifact=str(target),
                extra={"id": "cover"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="wireframes", phase="cover",
                message="Esquisse de la couverture…",
                current=done, total=total, extra={"id": "cover"},
            ))
            _generate_cover_wireframe(
                client, options.image_model, script, script.cover, target, feedback_store
            )
            rep.emit(ProgressEvent(
                step="wireframes", phase="cover_done",
                message="Esquisse couverture générée.",
                current=done, total=total, artifact=str(target),
                extra={"id": "cover"},
            ))

    for page in script.pages:
        flag.check()
        done += 1
        target = output_dir / f"page_{page.page_number:02d}.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="wireframes", phase=f"page_{page.page_number}_skipped",
                message=f"Esquisse planche {page.page_number} déjà sur disque.",
                current=done, total=total, artifact=str(target),
                extra={"id": f"page_{page.page_number}"},
            ))
            continue
        rep.emit(ProgressEvent(
            step="wireframes", phase=f"page_{page.page_number}",
            message=f"Esquisse de la planche {page.page_number}…",
            current=done, total=total,
            extra={"id": f"page_{page.page_number}"},
        ))
        _generate_wireframe(
            client, options.image_model, script, page, target, feedback_store
        )
        rep.emit(ProgressEvent(
            step="wireframes", phase=f"page_{page.page_number}_done",
            message=f"Esquisse planche {page.page_number} générée.",
            current=done, total=total, artifact=str(target),
            extra={"id": f"page_{page.page_number}"},
        ))

    if script.back_cover is not None:
        flag.check()
        done += 1
        target = output_dir / "back.png"
        if not force and _is_complete(target):
            rep.emit(ProgressEvent(
                step="wireframes", phase="back_skipped",
                message="Esquisse 4ᵉ de couverture déjà sur disque.",
                current=done, total=total, artifact=str(target),
                extra={"id": "back"},
            ))
        else:
            rep.emit(ProgressEvent(
                step="wireframes", phase="back",
                message="Esquisse de la 4ᵉ de couverture…",
                current=done, total=total, extra={"id": "back"},
            ))
            _generate_back_wireframe(
                client, options.image_model, script, script.back_cover, target, feedback_store
            )
            rep.emit(ProgressEvent(
                step="wireframes", phase="back_done",
                message="Esquisse 4ᵉ de couverture générée.",
                current=done, total=total, artifact=str(target),
                extra={"id": "back"},
            ))

    rep.emit(ProgressEvent(
        step="wireframes", phase="done",
        message="Toutes les esquisses sont prêtes.",
        current=total, total=total,
    ))


def _generate_wireframe(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    page: Page,
    target: Path,
    feedback_store: FeedbackStore | None = None,
) -> None:
    prompt = _build_wireframe_prompt(script, page)
    prompt += "\n\n" + IMAGE_CONSTRAINTS
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("wireframes", f"page_{page.page_number}")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    result = client.images.generate(
        model=image_model.model,
        prompt=prompt,
        size=WIREFRAME_SIZE,
        quality=WIREFRAME_QUALITY,
    )
    image_b64 = result.data[0].b64_json
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(base64.b64decode(image_b64))
    tmp.replace(target)


def _generate_cover_wireframe(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    cover: Cover,
    target: Path,
    feedback_store: FeedbackStore | None = None,
) -> None:
    prompt = dedent(f"""\
        Quick rough wireframe sketch of a comic book FRONT COVER, portrait
        format. Pencil-style draft, neutral grayscale, no color, no fine
        detail. Show the rough layout: where the title block goes, where the
        main illustration goes, where the author name goes.

        Title: "{script.metadata.title}"
        Author: "{script.metadata.author}"
        Title placement: {cover.title_placement or "top center, prominent"}
        Subtitle: {cover.subtitle or "(none)"}
        Tagline: {cover.tagline or "(none)"}
        Illustration concept: {cover.scene_description}
        """)
    prompt += "\n\n" + IMAGE_CONSTRAINTS
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("wireframes", "cover")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    _call_and_save(client, image_model, prompt, target)


def _generate_back_wireframe(
    client: OpenAI,
    image_model: ImageModelConfig,
    script: BdGenScript,
    back_cover: BackCover,
    target: Path,
    feedback_store: FeedbackStore | None = None,
) -> None:
    prompt = dedent(f"""\
        Quick rough wireframe sketch of a comic book BACK COVER, portrait
        format. Pencil-style draft, neutral grayscale, no color, no fine
        detail. Show the rough layout: where the synopsis blurb text block
        goes, where the optional small illustration goes, where the barcode
        placeholder sits.

        Synopsis blurb (about {len(back_cover.synopsis_blurb.split())} words of
        body text): goes in the central area.
        Optional illustration concept: {back_cover.scene_description or "(none)"}
        Tagline: {back_cover.tagline or "(none)"}
        Layout notes: {back_cover.layout_notes or "barcode placeholder bottom-right corner"}
        """)
    prompt += "\n\n" + IMAGE_CONSTRAINTS
    if feedback_store is not None:
        feedbacks = feedback_store.get_for("wireframes", "back")
        if feedbacks:
            prompt += feedback_block(feedbacks)
    _call_and_save(client, image_model, prompt, target)


def _call_and_save(
    client: OpenAI, image_model: ImageModelConfig, prompt: str, target: Path
) -> None:
    result = client.images.generate(
        model=image_model.model,
        prompt=prompt,
        size=WIREFRAME_SIZE,
        quality=WIREFRAME_QUALITY,
    )
    image_b64 = result.data[0].b64_json
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(base64.b64decode(image_b64))
    tmp.replace(target)


def _build_wireframe_prompt(script: BdGenScript, page: Page) -> str:
    """The wireframe prompt focuses on layout and rough composition only."""
    panels_text: list[str] = []
    for panel in page.panels:
        loc = script.location_by_id(panel.location)
        loc_name = loc.name if loc else panel.location
        chars = [script.character_by_id(c) for c in panel.characters]
        chars_text = ", ".join(c.name for c in chars if c) or "(no character)"
        panels_text.append(
            f"Panel {panel.panel_number} (size: {panel.size or 'medium'}, "
            f"shot: {panel.shot or 'medium shot'}): "
            f"{chars_text} in {loc_name}. {panel.scene_description}"
        )

    return dedent(f"""\
        Quick rough wireframe sketch of a complete BD comic page, portrait
        format. Pencil-style draft, neutral grayscale, no color, no text, no
        speech bubbles, no fine detail. Show the panel borders clearly and a
        rough sketch of the scene inside each panel.

        PAGE LAYOUT:
        {page.layout or "balanced grid"}

        This page contains {len(page.panels)} panel(s). Arrange them following
        the layout description above. Use uniform inter-panel gutters of about
        5mm. Render the panel borders as clear black rectangles (or shapes per
        the layout).

        PANELS (top-to-bottom, left-to-right reading order):
        """) + "\n".join(panels_text)


def _client(image_model: ImageModelConfig) -> OpenAI:
    if image_model.provider != "openai":
        raise NotImplementedError(
            f"Provider '{image_model.provider}' is not yet supported."
        )
    return OpenAI()


def _is_complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0
