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
"""
