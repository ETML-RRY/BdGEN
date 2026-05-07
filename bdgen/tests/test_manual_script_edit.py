from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

import pytest

from bdgen.models import (
    BackCover,
    BdGenScript,
    Cover,
    Dialog,
    GenerationOptions,
    ImageModelConfig,
    Metadata,
    Page,
    Panel,
    ScriptCharacter,
    ScriptLocation,
    ScriptModelConfig,
    ScriptObject,
    ScriptSource,
    Style,
)
from bdgen.service import (
    add_script_character_manual,
    add_script_location_manual,
    add_script_object_manual,
    check_script_coherence,
    read_coherence_index,
    read_stale_index,
    update_script_back_cover_manual,
    update_script_character_manual,
    update_script_cover_manual,
    update_script_location_manual,
    update_script_object_manual,
    update_script_page_manual,
)


def _save_script(script: BdGenScript, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(script.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _script() -> BdGenScript:
    return BdGenScript(
        project="demo",
        display_name="Demo",
        source=ScriptSource(
            input_file="bdgen.json",
            generated_at="2026-05-04T00:00:00Z",
            script_model="test",
        ),
        metadata=Metadata(title="Demo", author="Tester", language="fr"),
        style=Style(art_style="ligne claire"),
        generation_options=GenerationOptions(
            script_model=ScriptModelConfig(provider="test", model="test"),
            image_model=ImageModelConfig(provider="openai", model="gpt-image-2"),
        ),
        characters=[
            ScriptCharacter(
                id="perso_1",
                name="Ada",
                physical_description="Ancienne description.",
                outfit="Veste bleue.",
                reference_prompt="Old character prompt.",
            )
        ],
        locations=[
            ScriptLocation(
                id="decor_1",
                name="Bureau",
                description="Ancien decor.",
                reference_prompt="Old location prompt.",
            )
        ],
        objects=[
            ScriptObject(
                id="objet_1",
                name="Livre",
                description="Ancien objet.",
                reference_prompt="Old object prompt.",
            )
        ],
        cover=Cover(scene_description="Ancienne couverture.", title_placement="haut"),
        back_cover=BackCover(synopsis_blurb="Ancien synopsis.", scene_description="Ancienne illustration."),
        pages=[
            Page(
                page_number=1,
                layout="Une case.",
                panels=[
                    Panel(
                        panel_number=1,
                        location="decor_1",
                        characters=[],
                        scene_description="Ancien texte.",
                        dialogs=[
                            Dialog(
                                speaker="perso_1",
                                type="speech",
                                text="Ancien dialogue.",
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_update_script_page_persists_and_marks_composed_page_stale(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    script_path = project_dir / "bdgen-script.json"
    page_png = project_dir / "pages" / "page_01.png"
    page_png.parent.mkdir(parents=True)
    page_png.write_bytes(b"png")
    _save_script(_script(), script_path)

    new_page = Page(
        page_number=1,
        layout="Une case modifiee.",
        panels=[
            Panel(
                panel_number=1,
                location="decor_1",
                characters=[],
                scene_description="Nouveau texte.",
                dialogs=[
                    Dialog(
                        speaker="perso_1",
                        type="speech",
                        text="Nouveau dialogue.",
                    )
                ],
            )
        ],
    )

    update_script_page_manual("demo", 1, new_page.model_dump(mode="json"), tmp_path)

    saved = BdGenScript.load(script_path)
    assert saved.pages[0].layout == "Une case modifiee."
    assert saved.pages[0].panels[0].scene_description == "Nouveau texte."
    assert saved.pages[0].panels[0].dialogs[0].text == "Nouveau dialogue."
    assert read_stale_index(project_dir)["compose"] == ["page_1"]
    assert read_coherence_index(project_dir)["dirty"] is True


def test_update_script_page_rejects_page_number_change(tmp_path: Path) -> None:
    script_path = tmp_path / "demo" / "bdgen-script.json"
    _save_script(_script(), script_path)
    payload = _script().pages[0].model_dump(mode="json")
    payload["page_number"] = 2

    with pytest.raises(RuntimeError):
        update_script_page_manual("demo", 1, payload, tmp_path)


def test_update_script_character_location_object_and_covers(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    script_path = project_dir / "bdgen-script.json"
    (project_dir / "references" / "characters").mkdir(parents=True)
    (project_dir / "references" / "locations").mkdir(parents=True)
    (project_dir / "references" / "objects").mkdir(parents=True)
    (project_dir / "pages").mkdir(parents=True)
    (project_dir / "references" / "characters" / "perso_1.png").write_bytes(b"png")
    (project_dir / "references" / "locations" / "decor_1.png").write_bytes(b"png")
    (project_dir / "references" / "objects" / "objet_1.png").write_bytes(b"png")
    (project_dir / "pages" / "cover.png").write_bytes(b"png")
    (project_dir / "pages" / "back.png").write_bytes(b"png")
    _save_script(_script(), script_path)

    char_payload = _script().characters[0].model_dump(mode="json")
    char_payload["name"] = "Ada modifiee"
    update_script_character_manual("demo", "perso_1", char_payload, tmp_path)

    loc_payload = _script().locations[0].model_dump(mode="json")
    loc_payload["description"] = "Nouveau decor."
    update_script_location_manual("demo", "decor_1", loc_payload, tmp_path)

    obj_payload = _script().objects[0].model_dump(mode="json")
    obj_payload["description"] = "Nouvel objet."
    update_script_object_manual("demo", "objet_1", obj_payload, tmp_path)

    cover_payload = _script().cover.model_dump(mode="json")
    cover_payload["scene_description"] = "Nouvelle couverture."
    update_script_cover_manual("demo", cover_payload, tmp_path)

    back_payload = _script().back_cover.model_dump(mode="json")
    back_payload["synopsis_blurb"] = "Nouveau synopsis."
    update_script_back_cover_manual("demo", back_payload, tmp_path)

    saved = BdGenScript.load(script_path)
    assert saved.characters[0].name == "Ada modifiee"
    assert saved.locations[0].description == "Nouveau decor."
    assert saved.objects[0].description == "Nouvel objet."
    assert saved.cover.scene_description == "Nouvelle couverture."
    assert saved.back_cover.synopsis_blurb == "Nouveau synopsis."
    assert sorted(read_stale_index(project_dir)["references"]) == ["decor_1", "objet_1", "perso_1"]
    assert sorted(read_stale_index(project_dir)["compose"]) == ["back", "cover"]
    assert read_coherence_index(project_dir)["dirty"] is True


def test_add_script_character_location_object_rejects_duplicate_ids(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    script_path = project_dir / "bdgen-script.json"
    _save_script(_script(), script_path)

    add_script_character_manual(
        "demo",
        ScriptCharacter(
            id="perso_2",
            name="Marc",
            physical_description="Nouveau personnage.",
            reference_prompt="Nouveau personnage.",
        ).model_dump(mode="json"),
        tmp_path,
    )
    add_script_location_manual(
        "demo",
        ScriptLocation(
            id="decor_2",
            name="Rue",
            description="Nouveau decor.",
            reference_prompt="Nouveau decor.",
        ).model_dump(mode="json"),
        tmp_path,
    )
    add_script_object_manual(
        "demo",
        ScriptObject(
            id="objet_2",
            name="Badge",
            description="Nouvel objet.",
            reference_prompt="Nouvel objet.",
        ).model_dump(mode="json"),
        tmp_path,
    )

    saved = BdGenScript.load(script_path)
    assert [character.id for character in saved.characters] == ["perso_1", "perso_2"]
    assert [location.id for location in saved.locations] == ["decor_1", "decor_2"]
    assert [obj.id for obj in saved.objects] == ["objet_1", "objet_2"]

    with pytest.raises(RuntimeError):
        add_script_character_manual(
            "demo",
            ScriptCharacter(
                id="perso_2",
                name="Doublon",
                physical_description="Doublon.",
                reference_prompt="Doublon.",
            ).model_dump(mode="json"),
            tmp_path,
        )


def test_manual_edit_marks_coherence_dirty_and_check_flags_page_references(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    script_path = project_dir / "bdgen-script.json"
    _save_script(_script(), script_path)

    payload = _script().pages[0].model_dump(mode="json")
    payload["panels"][0]["characters"] = ["perso_inconnu"]
    payload["panels"][0]["objects"] = ["objet_inconnu"]
    update_script_page_manual("demo", 1, payload, tmp_path)

    assert read_coherence_index(project_dir)["dirty"] is True

    llm_result = {
        "issues": [
            {
                "page_number": 1,
                "panel_number": 1,
                "kind": "character",
                "target": "perso_inconnu",
                "message": "Personnage inconnu.",
            },
            {
                "page_number": 1,
                "panel_number": 1,
                "kind": "object",
                "target": "objet_inconnu",
                "message": "Objet inconnu.",
            },
        ],
        "suggestions": [],
    }
    with unittest.mock.patch("bdgen.service._llm_coherence_check", return_value=llm_result):
        coherence = check_script_coherence("demo", tmp_path)

    assert coherence["dirty"] is False
    assert coherence["flagged_pages"] == [1]
    assert {issue["target"] for issue in coherence["issues"]} == {"objet_inconnu", "perso_inconnu"}
    assert coherence["suggestions"] == []
