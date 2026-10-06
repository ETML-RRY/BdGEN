"""Cross-cutting constraints applied to every image-generation prompt.

These rules are injected into every prompt sent to the image API (references,
page panels, cover, back cover) so the model has a consistent set of authoring
constraints across the whole pipeline.
"""

IMAGE_CONSTRAINTS = """\
GLOBAL IMAGE CONSTRAINTS (apply to every image, no exceptions):
- KEEP IT READABLE: avoid overloading the image with details. Prioritize
  clarity, breathing room and strong silhouettes over visual busyness.
  A clean, well-staged composition beats a cluttered one. When in doubt,
  simplify.
- NO INCIDENTAL TEXT IN THE SCENE: outside of intentional speech bubbles,
  narration boxes and stylized sound effects, render NO readable text
  anywhere in the décor. This means: no street signs, shop signs, posters,
  book titles or covers, screen text, computer interfaces, labels,
  brand names, graffiti, magazine covers, banners, license plates, road
  markings with words, neon signs, or any other text in the environment.
  Replace anywhere a sign or text would naturally be with abstract patterns,
  shapes, or simply leave the surface plain.
- HANDS AND ARMS — ANATOMICAL CORRECTNESS (CRITICAL, NON-NEGOTIABLE):
  Every human character MUST have anatomically correct hands and arms.
  This is a hard constraint — violations are automatic failures.
  * Each hand has EXACTLY 5 fingers (4 fingers + 1 thumb). Count them.
    Never 4, never 6, never 7. FIVE fingers per hand, always.
  * Thumbs are shorter and opposable, positioned on the inner side of
    the hand. They are NOT just another finger.
  * Fingers have 3 visible segments (phalanges) each; thumbs have 2.
    No extra joints, no boneless noodle fingers, no fused digits.
  * Each arm has exactly ONE elbow joint that bends in ONE direction
    (toward the body front). Arms do NOT have extra bends, kinks, or
    rubber-hose curves between shoulder and wrist.
  * Forearms connect wrist to elbow; upper arms connect elbow to
    shoulder. No segment is missing, duplicated, or impossibly long.
  * Wrists are narrower than the forearm and connect cleanly to the
    palm — no abrupt width changes, no hands growing from elbows.
  * When hands hold objects, the grip must look natural: fingers wrap
    around the object, the thumb opposes, and the object's size is
    consistent with the hand holding it.
  * If a hand or arm would be difficult to render correctly at the
    chosen camera angle, prefer a composition that shows them clearly
    (e.g. hands at sides, on a table, holding a prop) rather than
    attempting a complex foreshortening that risks anatomical errors.
  * SELF-CHECK before finalizing: for every character visible in the
    image, verify: (1) correct number of fingers on each visible hand,
    (2) elbows bend correctly, (3) no extra limbs or missing limbs,
    (4) left and right hands are not swapped. If any check fails,
    redraw that character.
"""

# OpenAI's gpt-image models tend to dress up any lettering with their own
# decorative signature: emphasis strokes, radiating rays, sparkles, stars,
# glows and little vector flourishes. Only sent to OpenAI — other providers
# don't exhibit the habit and xAI has a tight prompt-length budget.
OPENAI_TEXT_ARTIFACT_RULES = """\
TEXT CLEANLINESS (NON-NEGOTIABLE):
- No decorative graphic elements around any text.
- Text must be bare: no emphasis lines, no rays, no stars, no sparkles,
  no glow or highlight effects.
- No vector flourishes, no underline effects, no small ornamental strokes
  or tick marks next to the lettering.
- Plain background behind the text, no decorative lines or sparkles.
- EXCEPTION — SOUND EFFECTS (onomatopoeia): they keep their classic comic
  energy. Bold, dynamic, deformed lettering is allowed, and so are speed
  lines, impact bursts and motion lines that belong to the ACTION of the
  scene. Still no sparkles, stars, glows or ornamental flourishes on them.
  The rules above apply in full to speech bubbles, narration captions,
  titles, folios and any other text.
"""


def with_openai_text_rules(prompt: str, provider: str) -> str:
    """Append ``OPENAI_TEXT_ARTIFACT_RULES`` when the image provider is OpenAI.

    Idempotent: a prompt that already carries the block (e.g. a stored prompt
    being replayed) is returned unchanged.
    """
    if provider != "openai" or OPENAI_TEXT_ARTIFACT_RULES in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{OPENAI_TEXT_ARTIFACT_RULES}"
