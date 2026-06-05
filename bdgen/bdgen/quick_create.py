"""Free-text prompt → full project draft.

Given a single free-text idea (from the vaguest "surprends-moi avec une
histoire de SF" to the most precise "la fondation d'une entreprise
informatique par deux amis, en manga"), calls a text LLM to pre-fill the
whole "Nouveau projet" form: identity, story, visual style, structure AND
casting (characters / locations / objects). The user then reviews and
adjusts the pre-filled form before creating the project.

The LLM call is dispatched through ``script._call_llm`` so it works with any
configured provider (Anthropic / OpenAI / xAI). The output schema, the
anti-real-names constraints and the sanitization helpers mirror
``style_from_image`` so the same safety net applies here.
"""
from __future__ import annotations

from textwrap import dedent

from pydantic import BaseModel, Field

from .models import ScriptModelConfig
from .script import _call_llm
from .style_from_image import _sanitize, _slugify


# Hard cap on the number of pages a quick-created draft may request. The quick
# path is the "just an idea" entry point, where the LLM would otherwise pick a
# full 44–48-page album for an epic premise — generating that many pages is slow
# and costly for someone who isn't watching the count. We both steer the LLM to
# stay within this budget and clamp defensively. Users who want more raise it
# themselves on the (detailed, deliberate) preparation form.
MAX_QUICK_CREATE_PAGES = 10


# Canonical art-style presets offered by the "Nouveau projet" form. Kept in
# sync with the frontend list in
# ``web/src/components/projectFormPresets.js`` (STYLE_ART_STYLE_PRESETS): the
# quick-create LLM must pick one of these VERBATIM so the form's style selector
# lands on a real preset instead of falling back to a free-text custom value.
ART_STYLE_PRESETS: list[str] = [
    "Ligne claire",
    "Franco-belge classique",
    "Manga shōnen",
    "Manga shōjo",
    "Manga seinen",
    "Comics américain",
    "Comics indépendant",
    "Roman graphique réaliste",
    "Roman graphique stylisé",
    "Aquarelle douce",
    "Encre lavée / Lavis",
    "Crayon de couleur",
    "Croquis / Carnet de voyage",
    "Peinture numérique",
    "Cartoon / Dessin animé",
    "Caricature",
    "Style minimaliste / Lineart",
    "Pixel art",
    "Album jeunesse illustré",
    "BD européenne contemporaine",
    "Noir et blanc encrage fort",
    "Style graphique géométrique",
    "Réalisme photographique",
    "Semi-réaliste",
    "Style fanzine / underground",
]

_ART_STYLE_PRESETS_BY_KEY: dict[str, str] = {
    p.strip().casefold(): p for p in ART_STYLE_PRESETS
}


def _match_art_style_preset(value: str) -> str:
    """Return the canonical preset matching ``value`` (case/space-insensitive),
    or ``""`` when none does. The LLM is asked to copy a preset verbatim, but
    we normalize defensively against stray casing/whitespace.
    """
    return _ART_STYLE_PRESETS_BY_KEY.get((value or "").strip().casefold(), "")


# --- LLM output schema -------------------------------------------------------


class _StoryDraft(BaseModel):
    synopsis: str = Field(
        default="",
        description=(
            "A vivid 2–4 sentence synopsis of the story: the protagonist(s), "
            "the central tension or quest, the stakes. Concrete and "
            "evocative, not a vague pitch."
        ),
    )
    genre: str = Field(
        default="",
        description="Genre (e.g. 'science-fiction', 'polar', 'comédie'). Empty if unclear.",
    )
    tone: str = Field(
        default="",
        description="Overall tone (e.g. 'sombre et tendu', 'léger et burlesque'). Empty if unclear.",
    )
    setting: str = Field(
        default="",
        description="Time and place where the story unfolds. Empty if unclear.",
    )
    target_audience: str = Field(
        default="",
        description="Intended audience (e.g. 'ados', 'tout public', 'adultes'). Empty if unclear.",
    )


class _StyleDraft(BaseModel):
    art_style_preset: str = Field(
        default="",
        description=(
            "The SINGLE closest-matching visual-style preset, copied VERBATIM "
            "(exact spelling, accents and casing) from this fixed list — do not "
            "invent, translate or merge values: "
            + " | ".join(ART_STYLE_PRESETS)
            + ". This populates the form's style selector, so it MUST be one of "
            "these exact strings. Leave empty only if genuinely none fits."
        ),
    )
    art_style: str = Field(
        default="",
        description=(
            "Image-generator-ready description of the visual approach: drawing "
            "technique, level of realism, body-proportion style, level of "
            "detail, with explicit negative constraints (e.g. 'no photorealism', "
            "'no smooth 3D gradients'). Be concrete and prescriptive."
        ),
    )
    color_palette: str = Field(
        default="",
        description="The dominant colour treatment (e.g. 'aplats chauds, peu de teintes', 'noir et blanc'). Empty if unclear.",
    )
    line_work: str = Field(
        default="",
        description="Inking / line-work directive (stroke weight, regularity, texture, hatching). Empty if unclear.",
    )
    mood: str = Field(
        default="",
        description="Overall atmosphere and rendering intent in one short sentence. Empty if unclear.",
    )
    panel_borders: str = Field(
        default="",
        description="How panel frames are drawn (stroke, regularity, corners, gutters, ornament). Empty if unclear.",
    )
    speech_bubbles: str = Field(
        default="",
        description="How speech / thought / shout bubbles are drawn (outline, fill, tail, signature traits). Empty if unclear.",
    )
    character_rendering: str = Field(
        default="",
        description="How characters are drawn (face geometry, eye/nose/mouth, body proportions, hands, hair, shading). Empty if unclear.",
    )


class _CharacterDraft(BaseModel):
    name: str = Field(
        default="",
        description=(
            "GENERIC placeholder name for the character — describe them by "
            "appearance or role, NEVER a real or copyrighted character's "
            "actual name (e.g. 'La jeune ingénieure aux cheveux courts')."
        ),
    )
    role: str = Field(default="", description="Narrative role (e.g. 'protagoniste', 'antagoniste'). Empty if unclear.")
    physical_description: str = Field(
        default="",
        description="Detailed physical description (age, build, hair, eyes, skin, distinguishing features). Generic descriptors only.",
    )
    outfit: str = Field(default="", description="Typical clothing and accessories. Generic descriptors only.")
    personality: str = Field(default="", description="Short personality sketch. Empty if unclear.")


class _LocationDraft(BaseModel):
    name: str = Field(
        default="",
        description=(
            "GENERIC placeholder name for the place (e.g. 'Le garage de "
            "banlieue', 'Le quartier général'). NEVER a real-world or "
            "copyrighted place name."
        ),
    )
    description: str = Field(
        default="",
        description="Vivid description (spatial layout, dominant elements, atmosphere, time of day). Generic descriptors only.",
    )


class _ObjectDraft(BaseModel):
    name: str = Field(
        default="",
        description="Short, neutral label for a recurring object / prop that matters to the story (e.g. 'Le carnet de croquis').",
    )
    description: str = Field(
        default="",
        description="Description precise enough to draw it (shape, materials, colours, markings). Generic descriptors only.",
    )


class _StructureDraft(BaseModel):
    page_count: int = Field(
        default=6,
        description=(
            f"Number of story pages, from 1 to {MAX_QUICK_CREATE_PAGES} MAXIMUM "
            "(see the pagination standards in the system prompt). Gag strip: 1. "
            f"Short story: 4–8. Longer story: up to {MAX_QUICK_CREATE_PAGES}. Even "
            "an epic premise must be condensed into a short opening episode here — "
            f"NEVER exceed {MAX_QUICK_CREATE_PAGES}."
        ),
    )
    panels_per_page_avg: int = Field(
        default=4,
        description=(
            "Average panels per page, consistent with the detected style/pacing: "
            "comic strip 3–4 (single row); standard BD album 4–8; dense classic "
            "page up to 9; cinematic/dramatic or splashy pages 1–3."
        ),
    )
    narrative_pacing: str = Field(default="", description="Pacing intent (e.g. 'rythme soutenu', 'contemplatif'). Empty if unclear.")
    page_format: str = Field(
        default="portrait",
        description="One of exactly: 'portrait', 'landscape', 'square', 'strip'. Use 'strip' only for a single-row gag comic.",
    )
    include_cover: bool = Field(default=True, description="Whether the BD should have a front cover.")
    include_back_cover: bool = Field(default=True, description="Whether the BD should have a back cover.")


class _ConfigDraft(BaseModel):
    title: str = Field(default="", description="An evocative title for the BD, invented from the idea.")
    author: str = Field(default="", description="Author name ONLY if the user explicitly gave one; otherwise empty string.")
    story: _StoryDraft = Field(default_factory=_StoryDraft)
    style: _StyleDraft = Field(default_factory=_StyleDraft)
    characters: list[_CharacterDraft] = Field(
        default_factory=list,
        description="The main cast the story implies. Invent a coherent cast when the idea is vague. Empty only if truly inapplicable.",
    )
    locations: list[_LocationDraft] = Field(
        default_factory=list,
        description="The main settings the story implies. Empty if none stand out.",
    )
    objects: list[_ObjectDraft] = Field(
        default_factory=list,
        description="Recurring objects / props the story implies. Often empty — only include ones that genuinely matter.",
    )
    structure: _StructureDraft = Field(default_factory=_StructureDraft)


SYSTEM_PROMPT = (
    dedent("""\
    You turn a single free-text idea into a complete, coherent brief for a
    comic-book ("bande dessinée") generator. You produce, in one go: a title,
    a story (synopsis + genre/tone/setting/audience), a visual STYLE, a
    STRUCTURE, and the CASTING (characters, locations, objects) the story
    implies.

    DETAIL PROPORTIONAL TO THE REQUEST:
    - If the idea is vague (e.g. "surprends-moi avec une histoire de SF"),
      INVENT freely a complete, original and coherent brief: pick a concrete
      premise, a cast, a setting and a fitting art style.
    - If the idea is precise (named premise, era, characters, desired style),
      FAITHFULLY honor every detail the user gave, and only invent what is
      missing to make the brief complete.
    - Always fill the casting when the story implies one. A BD almost always
      has at least one or two characters and a main location.

    PAGINATION — page_count is HARD-CAPPED at __MAX_PAGES__ pages for this quick
    draft (it is the cheap "just an idea" entry point; the user can extend it
    later on the detailed form). NEVER output more than __MAX_PAGES__:
    - Single gag / comic strip → page_format "strip", page_count 1, ~3–4 panels.
    - Short humorous or educational story → 4–8 pages, ~4–6 panels.
    - Anything longer or epic in scope → condense it into a self-contained
      opening episode of at most __MAX_PAGES__ pages; do NOT plan a full album.
    - Graphic-novel / dramatic / cinematic pacing → fewer, larger panels (1–4).
    Choose panels_per_page_avg to fit the style/pacing (strip 3–4, standard
    page 4–8, cinematic 1–3). Scale page_count to the story within the cap.

    CASTING COMPLETENESS — MANDATORY:
    - Every character, place or significant recurring object that you NAME or
      clearly evoke in the synopsis MUST appear in the matching list
      (characters / locations / objects). Do not mention a protagonist, a
      sidekick, a villain, a key location or a plot-critical object in the
      story without also adding its entry. The casting and the synopsis must be
      fully consistent — no orphan references in either direction.

    OUTPUT SHAPE — your response is a SINGLE JSON object with EXACTLY these
    keys, all present, using these EXACT field names (no extra keys, no
    renaming, no translating the keys, no wrapping object):
      {
        "title": "...",
        "author": "",
        "story": {
          "synopsis": "...", "genre": "...", "tone": "...",
          "setting": "...", "target_audience": "..."
        },
        "style": {
          "art_style_preset": "<one preset copied verbatim from the list below, or empty string>",
          "art_style": "...", "color_palette": "...", "line_work": "...",
          "mood": "...", "panel_borders": "...", "speech_bubbles": "...",
          "character_rendering": "..."
        },
        "characters": [
          {"name": "...", "role": "...", "physical_description": "...",
           "outfit": "...", "personality": "..."}
        ],
        "locations": [{"name": "...", "description": "..."}],
        "objects": [{"name": "...", "description": "..."}],
        "structure": {
          "page_count": 6, "panels_per_page_avg": 4, "narrative_pacing": "...",
          "page_format": "portrait", "include_cover": true,
          "include_back_cover": true
        }
      }
    Fill EVERY section — the "style" object and the "characters"/"locations"/
    "objects" arrays must NOT be left empty when the story implies them (it
    almost always does). The casting arrays hold objects with the exact fields
    shown; never collapse them to plain strings or rename their fields.

    "art_style_preset" — copy ONE value VERBATIM (exact spelling, accents and
    casing) from this fixed list, picking the closest match to the style you
    intend; leave it "" only if genuinely none fits:
    __ART_STYLE_PRESETS__

    HARD CONSTRAINTS — APPLY WITHOUT EXCEPTION:
    - NEVER name a real artist, illustrator, studio, publisher, franchise,
      copyrighted character, brand, manga title, or movie. The output must
      NOT contain any proper noun referring to such entities. Forbidden:
      "style Hergé", "à la manière de Moebius", "comme Tintin",
      "manga Naruto", "Disney style", "Marvel-like", "Ghibli". Use generic
      stylistic descriptors instead (e.g. "ligne claire avec aplats de
      couleur", "style manga shōnen aux grands yeux expressifs").
    - For characters, even when the user names a real or famous person,
      NEVER use their actual name. Refer to them ONLY through generic
      descriptive placeholders ("le fondateur charismatique au col roulé").
      Treat every character as an original creation.
    - For locations, NEVER use a real-world or copyrighted place name
      ("Tour Eiffel", "Hogwarts", "Tatooine"…). Describe WHAT the place
      looks like instead.
    - The ``author`` field stays empty unless the user explicitly provided
      an author name. Do NOT invent one.
    - ``page_format`` must be EXACTLY one of: portrait, landscape, square, strip.
    - ``art_style_preset`` MUST be copied verbatim from the preset list in the
      OUTPUT SHAPE above (it drives the form's style selector). Pick the one
      closest to the style you intend; leave it empty only if none fits.
    - Style fields will be quoted verbatim into image-generation prompts:
      art_style must be prescriptive and include negative constraints, and the
      detailed style fields (color_palette, line_work, character_rendering,
      mood…) must each be filled — they carry the style detail even when
      art_style_preset is a short label.
    - All free-text fields are written in the requested response language.
    - Output ONLY the structured JSON object. No commentary, no markdown.
    """)
    .replace("__ART_STYLE_PRESETS__", " | ".join(ART_STYLE_PRESETS))
    .replace("__MAX_PAGES__", str(MAX_QUICK_CREATE_PAGES))
)


_VALID_PAGE_FORMATS: set[str] = {"portrait", "landscape", "square", "strip"}


def generate_config(
    prompt: str,
    language: str = "fr",
    model_config: ScriptModelConfig | None = None,
    documents_text: str = "",
    art_style: str = "",
) -> dict:
    """Expand a free-text idea (and/or reference documents) into a partial
    project config for the form.

    ``documents_text`` is the already-extracted, concatenated text of any
    reference documents the user attached (see :mod:`document_text`). When it
    is provided the brief must be grounded in those documents; the prompt then
    only steers the angle/style and may even be empty.

    ``art_style`` is an optional visual-style choice from the simplified form
    (e.g. "Manga shōnen", "Ligne claire"). When set, the LLM must build the
    whole ``style`` section around it instead of inventing a style freely.

    Returns only the sections the "Nouveau projet" form edits
    (``metadata.title``/``author``, ``story``, ``style``, partial
    ``structure``, ``characters``/``locations``/``objects``). The frontend
    merges this onto its ``DEFAULT_CONFIG`` (which supplies
    ``generation_options``, ``output_root``, ``project``).

    ``model_config`` is required in practice; it is the
    :class:`ScriptModelConfig` chosen by the caller (see
    ``app._pick_text_model``).
    """
    text = (prompt or "").strip()
    docs = (documents_text or "").strip()
    if not text and not docs:
        raise ValueError("Décrivez votre idée ou ajoutez au moins un document de référence.")
    if model_config is None:
        raise ValueError("Aucun modèle de texte configuré.")

    if text:
        idea_block = (
            f"Voici l'idée de l'utilisateur pour sa bande dessinée :\n\n"
            f"\"\"\"\n{text}\n\"\"\"\n\n"
        )
    else:
        idea_block = (
            "L'utilisateur n'a pas écrit d'idée précise : adapte librement les "
            "documents de référence ci-dessous en une bande dessinée vivante et "
            "pédagogique, fidèle à leur contenu.\n\n"
        )

    user_text = (
        f"{idea_block}"
        f"Construis un brief complet et cohérent en {language}, avec un niveau "
        f"de détail proportionnel à la précision de la demande. Si la demande "
        f"est vague, invente librement une histoire originale et son casting. "
        f"Renvoie le titre, l'histoire, le style visuel, la structure et le "
        f"casting (personnages, décors, objets) au format structuré demandé."
    )

    if docs:
        user_text += (
            "\n\nDocuments de référence fournis par l'utilisateur. Appuie-toi "
            "FIDÈLEMENT sur leur contenu (faits, concepts, déroulé, exemples) "
            "pour bâtir l'histoire et le casting ; vulgarise et mets en scène "
            "sans inventer de faits qui les contrediraient. Continue de "
            "respecter les contraintes (placeholders génériques pour toute "
            "personne ou marque réelle) :\n\n"
            f"\"\"\"\n{docs}\n\"\"\""
        )

    style_hint = (art_style or "").strip()
    if style_hint:
        user_text += (
            f"\n\nSTYLE VISUEL IMPOSÉ par l'utilisateur : « {style_hint} ». "
            f"Construis TOUTE la section style autour de ce choix : développe "
            f"« {style_hint} » en un champ art_style prescriptif et prêt pour un "
            f"générateur d'images (technique, niveau de réalisme, proportions, "
            f"contraintes négatives), et décline palette, encrage, ambiance, "
            f"cadres, bulles et rendu des personnages de façon cohérente avec ce "
            f"style. N'invente pas un autre style et n'utilise aucun nom d'artiste "
            f"ni de marque."
        )

    result = _call_llm(
        SYSTEM_PROMPT,
        user_text,
        model_config,
        output_type=_ConfigDraft,
        trace_name="quick_create",
    )
    draft = result.value
    assert isinstance(draft, _ConfigDraft)

    return _draft_to_config(draft, art_style_hint=style_hint)


# --- Mapping helpers ---------------------------------------------------------


def _unique_id(name: str, fallback_prefix: str, idx: int, used: set[str]) -> str:
    base = _slugify(name) or f"{fallback_prefix}_{idx}"
    cid = base
    suffix = 2
    while cid in used:
        cid = f"{base}_{suffix}"
        suffix += 1
    used.add(cid)
    return cid


def _resolve_art_style(style: _StyleDraft, art_style_hint: str = "") -> str:
    """Pick the value written to ``style.art_style``.

    The form's style selector only shows a preset as *selected* when the value
    is one of the canonical presets (otherwise it falls back to a free-text
    custom entry). So we prefer a preset here:

    1. the preset the user explicitly chose in the simplified form (``hint``);
    2. else the preset the LLM matched (``art_style_preset``);
    3. else the LLM's free-text ``art_style`` (no preset fit — keep the detail).

    When a preset is used, the prescriptive detail still reaches image
    generation through the other style fields (color_palette, line_work,
    character_rendering, mood…), which are all injected into the prompts.
    """
    hinted = _match_art_style_preset(art_style_hint)
    if hinted:
        return hinted
    matched = _match_art_style_preset(style.art_style_preset)
    if matched:
        return matched
    return _sanitize(style.art_style)


def _draft_to_config(draft: _ConfigDraft, art_style_hint: str = "") -> dict:
    used_char_ids: set[str] = set()
    characters = []
    for idx, c in enumerate(draft.characters, start=1):
        name = _sanitize(c.name) or f"Personnage {idx}"
        characters.append(
            {
                "id": _unique_id(name, "perso", idx, used_char_ids),
                "name": name,
                "role": _sanitize(c.role),
                "physical_description": _sanitize(c.physical_description),
                "outfit": _sanitize(c.outfit),
                "personality": _sanitize(c.personality),
            }
        )

    used_loc_ids: set[str] = set()
    locations = []
    for idx, loc in enumerate(draft.locations, start=1):
        name = _sanitize(loc.name) or f"Décor {idx}"
        locations.append(
            {
                "id": _unique_id(name, "decor", idx, used_loc_ids),
                "name": name,
                "description": _sanitize(loc.description),
            }
        )

    used_obj_ids: set[str] = set()
    objects = []
    for idx, obj in enumerate(draft.objects, start=1):
        name = _sanitize(obj.name) or f"Objet {idx}"
        objects.append(
            {
                "id": _unique_id(name, "objet", idx, used_obj_ids),
                "name": name,
                "description": _sanitize(obj.description),
            }
        )

    page_format = draft.structure.page_format
    if page_format not in _VALID_PAGE_FORMATS:
        page_format = "portrait"

    return {
        "metadata": {
            "title": _sanitize(draft.title) or "Sans titre",
            "author": _sanitize(draft.author),
        },
        "story": {
            "synopsis": _sanitize(draft.story.synopsis),
            "genre": _sanitize(draft.story.genre),
            "tone": _sanitize(draft.story.tone),
            "setting": _sanitize(draft.story.setting),
            "target_audience": _sanitize(draft.story.target_audience),
        },
        "style": {
            "art_style": _resolve_art_style(draft.style, art_style_hint),
            "color_palette": _sanitize(draft.style.color_palette),
            "line_work": _sanitize(draft.style.line_work),
            "mood": _sanitize(draft.style.mood),
            "panel_borders": _sanitize(draft.style.panel_borders),
            "speech_bubbles": _sanitize(draft.style.speech_bubbles),
            "character_rendering": _sanitize(draft.style.character_rendering),
        },
        "structure": {
            "page_count": min(MAX_QUICK_CREATE_PAGES, max(1, int(draft.structure.page_count))),
            "panels_per_page_avg": min(12, max(1, int(draft.structure.panels_per_page_avg))),
            "narrative_pacing": _sanitize(draft.structure.narrative_pacing),
            "page_format": page_format,
            "include_cover": bool(draft.structure.include_cover),
            "include_back_cover": bool(draft.structure.include_back_cover),
        },
        "characters": characters,
        "locations": locations,
        "objects": objects,
    }
