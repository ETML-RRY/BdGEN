from __future__ import annotations

from pathlib import Path
from typing import Callable

from bdgen.compose import _collect_refs
from bdgen.service.style_refs import attach_existing_reference_images

from tests.factories import make_minimal_script


def test_existing_copied_references_are_attached_and_used_for_compose(
    tmp_path: Path,
    make_png: Callable[[Path], None],
) -> None:
    make_png(tmp_path / "references" / "characters" / "hero.png")
    make_png(tmp_path / "references" / "locations" / "home.png")
    make_png(tmp_path / "references" / "objects" / "book.png")

    script = make_minimal_script(tmp_path, project="copy")
    changed = attach_existing_reference_images(tmp_path, script)

    assert changed is True
    assert script.characters[0].reference_image == tmp_path / "references" / "characters" / "hero.png"
    assert script.locations[0].reference_image == tmp_path / "references" / "locations" / "home.png"
    assert script.objects[0].reference_image == tmp_path / "references" / "objects" / "book.png"

    refs = _collect_refs(script, script.pages[0])
    assert len(refs) == 3
    assert {p.name for p, _ in refs} == {"hero.png", "home.png", "book.png"}
