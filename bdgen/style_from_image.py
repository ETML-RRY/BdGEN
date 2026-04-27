"""Image → BD style + character extractor.

Given an uploaded image, calls OpenAI's vision-capable chat model to produce
both a structured style description AND character descriptions usable by the
BdGEN script and image pipelines.

Hard rule: descriptions must NEVER name real artists, illustrators, studios,
franchises or copyrighted characters. Only generic stylistic and physical
descriptors are allowed (e.g. "ligne claire avec aplats de couleur" instead
of "style Hergé"; "le jeune homme aux cheveux roux" instead of any real
character's actual name). The system prompt enforces this and the output is
sanitized as a safety net.
"""
from __future__ import annotations

import base64
import os
import re
import unicodedata
from textwrap import dedent

from openai import OpenAI
from pydantic import BaseModel, Field

from .models import CharacterInput, LocationInput, Style


SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

DEFAULT_MODEL = os.environ.get("BDGEN_STYLE_MODEL", "gpt-4o-mini")
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB safety cap

# Generic catch-all of names users might try to inject. Not exhaustive — the
# system prompt is the primary guard. This is a belt-and-braces sanitizer that
# replaces forbidden tokens with a neutral phrase if they slip through.
_FORBIDDEN_PATTERNS = re.compile(
    r"\b(?:hergé|herge|tintin|asterix|astérix|obelix|obélix|moebius|"
    r"giraud|uderzo|goscinny|franquin|spirou|marvel|dc comics|disney|"
    r"pixar|miyazaki|ghibli|naruto|sasuke|goku|dragon\s*ball|"
    r"mickey|donald|batman|superman|spiderman|spider-man)\b",
    re.IGNORECASE,
)


class ExtractionResult(BaseModel):
    """Public payload returned by ``extract``. Maps cleanly to the form."""
    style: Style
    characters: list[CharacterInput] = Field(default_factory=list)
    locations: list[LocationInput] = Field(default_factory=list)


# --- LLM output schema (strict variants, all fields required) ---

class _StyleDraft(BaseModel):
    art_style: str = Field(
        description=(
            "An image-generator-ready description of the visual approach: "
            "drawing technique (e.g. hand-drawn ink, flat digital vector, "
            "loose sketch), level of realism, body proportions style, "
            "level of detail. Must include explicit negative constraints "
            "for what NOT to do (e.g. 'no photorealism', 'no smooth 3D "
            "gradients', 'no polished animation style'). Be concrete and "
            "prescriptive — this description must override an image "
            "model's defaults."
        )
    )
    color_palette: str = Field(
        description=(
            "Precise palette for an image generator: list the actual colors "
            "used (e.g. 'black ink line work, flat cobalt blue fills, white "
            "background, occasional red/orange for emphasis, no skin-tone "
            "gradients, no color blending'). Include what is absent."
        )
    )
    line_work: str = Field(
        description=(
            "Inking / line-work directive: stroke weight (thin/thick/variable), "
            "regularity (clean/irregular/sketchy), line texture, use of "
            "hatching. Be prescriptive: 'irregular hand-drawn contours of "
            "variable thickness, no clean vector lines, gestural hatching "
            "for shadows'."
        )
    )
    mood: str = Field(
        description=(
            "Overall atmosphere and rendering intent: e.g. 'raw indie-press "
            "fanzine energy, deliberately imperfect, warm and approachable'. "
            "Keep short (1 sentence)."
        )
    )
    negative_constraints: str = Field(
        description=(
            "A single sentence starting with 'DO NOT' that lists the most "
            "important things the image generator must avoid to stay true "
            "to this style. E.g.: 'DO NOT use smooth gradients, photorealistic "
            "skin textures, polished 3D shading, or American superhero "
            "comic aesthetics.'"
        )
    )


class _CharacterDraft(BaseModel):
    name: str = Field(
        description=(
            "GENERIC placeholder name describing the character through their "
            "appearance or role, e.g. 'Le jeune homme aux cheveux roux', "
            "'La femme âgée à la canne', 'L'enfant masqué'. NEVER the real "
            "character's actual name."
        )
    )
    role: str = Field(
        default="",
        description=(
            "Optional narrative role hint, if it can be inferred from the "
            "scene (e.g. 'protagoniste apparent', 'figurant', 'antagoniste'). "
            "Empty string if uncertain."
        ),
    )
    physical_description: str = Field(
        description=(
            "Detailed physical description: approximate age, build, hair, "
            "eyes, skin, distinguishing features. Generic descriptors only."
        )
    )
    outfit: str = Field(
        description=(
            "Description of the clothing and accessories the character wears "
            "in the image. Generic descriptors only."
        )
    )
    personality: str = Field(
        default="",
        description=(
            "Optional personality hint inferable from posture/expression. "
            "Empty string if uncertain."
        ),
    )


class _LocationDraft(BaseModel):
    name: str = Field(
        description=(
            "GENERIC placeholder name for the location, e.g. 'Le phare "
            "isolé', 'Le marché animé', 'La salle du trône en pierre'. "
            "NEVER the real-world or fictional copyrighted place name."
        )
    )
    description: str = Field(
        description=(
            "Vivid description of the place: spatial layout, dominant "
            "elements, atmosphere, time of day, weather. Generic descriptors "
            "only — no real-world or copyrighted place names."
        )
    )


class _ExtractionDraft(BaseModel):
    art_style: str
    color_palette: str
    line_work: str
    mood: str
    characters: list[_CharacterDraft] = Field(
        default_factory=list,
        description=(
            "List of distinct characters visible in the image. Empty list "
            "if no characters are visible (e.g. landscape or abstract art)."
        ),
    )
    locations: list[_LocationDraft] = Field(
        default_factory=list,
        description=(
            "List of distinct locations / settings visible in the image. "
            "Often there is only one. Empty list if the image is purely "
            "abstract or focuses entirely on a character with no visible "
            "environment."
        ),
    )


SYSTEM_PROMPT = dedent("""\
    You analyze a single image and produce a structured description meant to
    drive a downstream comic-book ("bande dessinée") generator. You produce
    THREE things in one go:

    1. The visual STYLE of the image (art_style, color_palette, line_work,
       mood). You are NOT summarizing the image's content here; you focus
       exclusively on its STYLE.

    2. A list of CHARACTERS visible in the image. For each visible character,
       provide a generic placeholder name plus physical description, outfit,
       and optional role/personality. Empty list if the image has no
       characters.

    3. A list of LOCATIONS / settings visible in the image. Usually one
       (the main setting), occasionally several if the image splits into
       distinct scenes. Empty list if the image is purely abstract or
       focuses entirely on a character with no visible environment.

    HARD CONSTRAINTS — APPLY WITHOUT EXCEPTION:
    - NEVER name a real artist, illustrator, studio, publisher, franchise,
      copyrighted character, brand, manga title, or movie. The output must
      NOT contain any proper noun referring to such entities. Forbidden:
      "style Hergé", "à la manière de Moebius", "comme Tintin",
      "manga Naruto", "Disney style", "Marvel-like", "Ghibli". Use generic
      descriptors instead.
    - For characters, NEVER use the actual name of a recognizable character.
      Even if you recognize the character, refer to them ONLY through
      generic descriptive placeholders like "Le jeune homme aux cheveux roux"
      or "La guerrière à l'armure dorée". Treat every character as if they
      were original.
    - For locations, NEVER use the real-world or copyrighted name of a
      place ("Tour Eiffel", "Hogwarts", "Tatooine"…). Use generic
      descriptors of WHAT the place looks like ("la tour de fer dans une
      capitale européenne", "le château de magie sur une falaise"…).
    - Stay descriptive and concrete. Vague hand-waving wastes downstream
      signal.
    - Each style field is 1–3 sentences. Each character/location field is
      1–3 sentences. Optional fields can be empty strings if uncertain.
    - All free-text fields are written in the requested response language.
    - Output ONLY the structured JSON object. No commentary, no quotes
      around the values, no markdown.
    """)


def extract(
    image_bytes: bytes,
    mime_type: str,
    language: str = "fr",
    model: str | None = None,
) -> ExtractionResult:
    """Call OpenAI vision and return both style and characters.

    ``language`` is the ISO code for the descriptions (matches
    ``metadata.language`` on a project). ``model`` defaults to the
    ``BDGEN_STYLE_MODEL`` env var or ``gpt-4o-mini``.
    """
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError(
            f"Type d'image non supporté : {mime_type}. "
            f"Formats acceptés : JPEG, PNG, WEBP, GIF."
        )
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image trop volumineuse ({len(image_bytes) // (1024 * 1024)} Mo). "
            f"Taille max : {MAX_IMAGE_BYTES // (1024 * 1024)} Mo."
        )
    if not image_bytes:
        raise ValueError("Image vide.")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"
    client = OpenAI()

    user_text = (
        f"Analyse cette image. Renvoie en {language} :\n"
        f"  • le style visuel (art_style, color_palette, line_work, mood, "
        f"negative_constraints) — ces champs seront utilisés verbatim "
        f"dans des prompts de génération d'images : sois très prescriptif "
        f"et inclus dans art_style des contraintes négatives explicites "
        f"('no smooth gradients', 'no photorealism'…) ;\n"
        f"  • la liste des personnages visibles avec un nom de remplacement "
        f"générique (jamais le nom réel d'un personnage protégé), une "
        f"description physique et la tenue ;\n"
        f"  • la liste des décors / lieux visibles (souvent un seul, "
        f"parfois plusieurs si l'image est découpée en plusieurs scènes), "
        f"avec un nom générique et une description vivante.\n"
        f"Rappel : aucune citation d'auteur, studio, franchise, personnage "
        f"ou lieu protégé. Descripteurs génériques uniquement."
    )

    completion = client.chat.completions.parse(
        model=model or DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        response_format=_ExtractionDraft,
    )
    msg = completion.choices[0].message
    if msg.parsed is None:
        raise RuntimeError(
            f"Le modèle n'a pas retourné de description exploitable. "
            f"Refus éventuel : {msg.refusal}"
        )

    draft = msg.parsed
    # Append negative_constraints to art_style so it rides along verbatim in
    # every downstream image prompt — it's the single most influential lever.
    art_style = _sanitize(draft.art_style)
    if draft.negative_constraints:
        neg = _sanitize(draft.negative_constraints)
        if neg and not art_style.lower().strip().endswith(neg.lower().strip()):
            art_style = f"{art_style} {neg}"
    style = Style(
        art_style=art_style,
        color_palette=_sanitize(draft.color_palette),
        line_work=_sanitize(draft.line_work),
        mood=_sanitize(draft.mood),
    )
    used_char_ids: set[str] = set()
    characters = [
        _to_character_input(c, idx, used_char_ids)
        for idx, c in enumerate(draft.characters, start=1)
    ]
    used_loc_ids: set[str] = set()
    locations = [
        _to_location_input(l, idx, used_loc_ids)
        for idx, l in enumerate(draft.locations, start=1)
    ]
    return ExtractionResult(style=style, characters=characters, locations=locations)


# Backwards-compat alias for the previous public name.
def extract_style(
    image_bytes: bytes,
    mime_type: str,
    language: str = "fr",
    model: str | None = None,
) -> Style:
    return extract(image_bytes, mime_type, language, model).style


# --- Helpers ---

def _sanitize(text: str) -> str:
    """Belt-and-braces: scrub any famous-name token that slipped past the prompt."""
    return _FORBIDDEN_PATTERNS.sub("[descripteur générique]", text).strip()


def _slugify(text: str) -> str:
    """Best-effort ASCII slug. Returns empty string if nothing usable."""
    norm = unicodedata.normalize("NFD", text)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return norm[:40]


def _to_character_input(
    draft: _CharacterDraft, idx: int, used_ids: set[str]
) -> CharacterInput:
    name = _sanitize(draft.name) or f"Personnage {idx}"
    base = _slugify(name) or f"perso_{idx}"
    cid = base
    suffix = 2
    while cid in used_ids:
        cid = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(cid)
    role = _sanitize(draft.role) or None
    personality = _sanitize(draft.personality) or None
    outfit = _sanitize(draft.outfit) or None
    return CharacterInput(
        id=cid,
        name=name,
        role=role,
        physical_description=_sanitize(draft.physical_description),
        outfit=outfit,
        personality=personality,
    )


def _to_location_input(
    draft: _LocationDraft, idx: int, used_ids: set[str]
) -> LocationInput:
    name = _sanitize(draft.name) or f"Décor {idx}"
    base = _slugify(name) or f"decor_{idx}"
    lid = base
    suffix = 2
    while lid in used_ids:
        lid = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(lid)
    return LocationInput(
        id=lid,
        name=name,
        description=_sanitize(draft.description),
    )
