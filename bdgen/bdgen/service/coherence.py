"""LLM-driven script coherence checks and global suggestion application."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import secret_store
from .. import stats as stats_module
from .. import trace as trace_module
from ..models import BdGenScript, Page, ScriptCharacter, ScriptLocation, ScriptObject
from .config import load_config
from .indices import mark_stale, read_coherence_index, write_coherence_index


def _llm_coherence_check(
    system: str,
    user: str,
    script_model,
    project_dir: Path | None = None,
    target_id: str = "script",
) -> dict:
    """Ask the configured LLM for coherence issues and narrative suggestions.

    Returns {"issues": [...], "suggestions": [...]}.
    """
    provider = script_model.provider if script_model else "openai"
    model = script_model.model if script_model else "gpt-4o-mini"

    started_at, started = stats_module.start_timer()
    usage: dict = {}
    with trace_module.node(
        f"coherence_check:{target_id}", "llm_call",
        project_dir=project_dir,
    ) as _tn:
        _tn.set_model(provider, model)
        _tn.set_prompt(user)
        _tn.set_extra(system_prompt=system)
        try:
            if provider == "anthropic":
                client = secret_store.anthropic_client()
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = response.content[0].text
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            elif provider == "xai":
                client = secret_store.xai_client()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            else:
                client = secret_store.openai_client()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            _tn.set_usage(usage)
            _tn.set_outputs({"raw_chars": len(raw or "")})
        except Exception as _exc:
            _tn.set_extra(error=str(_exc))
            stats_module.record_event(
                project_dir,
                step="coherence",
                target_id=target_id,
                target_kind="script",
                operation="check_coherence",
                provider=provider,
                model=model,
                timer=stats_module.stop_timer(started_at, started),
                status="error",
                usage=usage,
                prompt=user,
                extra={"retouch": False},
            )
            return {"issues": [], "suggestions": []}

    stats_module.record_event(
        project_dir,
        step="coherence",
        target_id=target_id,
        target_kind="script",
        operation="check_coherence",
        provider=provider,
        model=model,
        timer=stats_module.stop_timer(started_at, started),
        usage=usage,
        prompt=user,
        extra={"retouch": False},
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return {"issues": [], "suggestions": []}
        else:
            return {"issues": [], "suggestions": []}

    if not isinstance(data, dict):
        return {"issues": [], "suggestions": []}

    return {
        "issues": _parse_items(data.get("issues", [])),
        "suggestions": _parse_items(data.get("suggestions", [])),
    }


def _parse_items(raw_list: list) -> list[dict]:
    valid: list[dict] = []
    for item in raw_list or []:
        if not isinstance(item, dict):
            continue
        page_number = item.get("page_number")
        try:
            valid.append(
                {
                    "page_number": int(page_number) if page_number is not None else None,
                    "panel_number": item.get("panel_number"),
                    "kind": str(item.get("kind", "unknown")),
                    "target": str(item.get("target", "")),
                    "message": str(item.get("message", "")),
                }
            )
        except (ValueError, TypeError):
            continue
    return valid


def check_script_coherence(name: str, output_root: Path | None = None) -> dict:
    """Check script coherence using an LLM — both structural errors and narrative suggestions."""
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)

    try:
        script_model = load_config(name, output_root).generation_options.script_model
    except FileNotFoundError:
        opts = bd_script.generation_options
        script_model = opts.script_model if opts else None

    characters = [
        {"id": c.id, "name": c.name, "description": c.physical_description, "outfit": c.outfit}
        for c in bd_script.characters
    ]
    locations = [
        {"id": loc.id, "name": loc.name, "description": loc.description}
        for loc in bd_script.locations
    ]
    objects = [
        {"id": o.id, "name": o.name, "description": o.description}
        for o in bd_script.objects
    ]
    pages_data = []
    for page in bd_script.pages:
        panels_data = []
        for panel in page.panels:
            panels_data.append(
                {
                    "panel_number": panel.panel_number,
                    "location": panel.location,
                    "characters": panel.characters,
                    "objects": panel.objects or [],
                    "scene_description": panel.scene_description,
                    "dialogs": [{"speaker": d.speaker, "type": d.type, "text": d.text} for d in panel.dialogs],
                }
            )
        pages_data.append({"page_number": page.page_number, "layout": page.layout, "panels": panels_data})

    script_payload = {
        "characters": characters,
        "locations": locations,
        "objects": objects,
        "pages": pages_data,
    }

    system = (
        "Tu es un expert en scénarios de bande dessinée. "
        "On te donne un scénario complet avec personnages, décors, objets et planches. "
        "Tu dois :\n"
        "1. Détecter les ERREURS structurelles (dans 'issues') : références à des ids de personnages, "
        "décors ou objets inconnus ; personnages qui parlent sans figurer dans la liste 'characters' de la case "
        "(sauf type 'narration') ; numéros de planche ou de case en doublon ; toute incohérence technique.\n"
        "2. Proposer des SUGGESTIONS narratives proactives (dans 'suggestions') : personnages, décors ou objets "
        "qui n'apparaissent dans aucune planche et pourraient être exploités ; planches où un personnage "
        "récemment ajouté enrichirait la scène ; incohérences narratives subtiles entre la description d'un "
        "élément et son usage dans les cases ; améliorations pour renforcer la cohérence de l'histoire.\n"
        "Réponds UNIQUEMENT avec un objet JSON de la forme :\n"
        '{"issues": [...], "suggestions": [...]}\n'
        "Chaque entrée (issue ou suggestion) : "
        '{"page_number": int|null, "panel_number": int|null, '
        '"kind": "character"|"location"|"object"|"dialog"|"panel"|"page"|"narrative", '
        '"target": string, "message": string (en français)}.\n'
        'Si rien à signaler : {"issues": [], "suggestions": []}.'
    )
    user = f"Scénario à analyser :\n\n{json.dumps(script_payload, ensure_ascii=False, indent=2)}"

    result = _llm_coherence_check(system, user, script_model, proj_dir, name)
    issues = result.get("issues", [])
    suggestions = result.get("suggestions", [])

    idx = {
        "dirty": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
        "suggestions": suggestions,
        "flagged_pages": sorted({issue["page_number"] for issue in issues if issue.get("page_number") is not None}),
    }
    write_coherence_index(proj_dir, idx)
    return idx


def apply_global_suggestion(
    name: str,
    suggestion: str,
    output_root: Path | None = None,
) -> dict:
    """Apply a global narrative suggestion to the script via the LLM.

    The LLM returns only the modified elements (page_updates, character_updates,
    character_additions, location_updates, location_additions, object_updates,
    object_additions). Each is applied using the existing Pydantic validators and
    the script is saved. Returns a summary of applied changes.
    """
    from .lifecycle import get_project_dir

    proj_dir = get_project_dir(name, output_root)
    script_path = proj_dir / "bdgen-script.json"
    bd_script = BdGenScript.load(script_path)

    try:
        script_model = load_config(name, output_root).generation_options.script_model
    except FileNotFoundError:
        opts = bd_script.generation_options
        script_model = opts.script_model if opts else None

    provider = script_model.provider if script_model else "openai"
    model = script_model.model if script_model else "gpt-4o-mini"

    script_payload = {
        "characters": [c.model_dump(mode="json") for c in bd_script.characters],
        "locations": [loc.model_dump(mode="json") for loc in bd_script.locations],
        "objects": [o.model_dump(mode="json") for o in bd_script.objects],
        "pages": [p.model_dump(mode="json") for p in bd_script.pages],
    }

    system = (
        "Tu es un éditeur de scénarios de bande dessinée expérimenté. "
        "On te donne un scénario complet et une suggestion narrative à appliquer. "
        "Applique la suggestion en retournant UNIQUEMENT les éléments modifiés au format JSON :\n"
        "{\n"
        '  "page_updates": [<pages complètes modifiées, avec tous leurs champs>],\n'
        '  "character_updates": [<personnages existants à modifier>],\n'
        '  "character_additions": [<nouveaux personnages>],\n'
        '  "location_updates": [<décors existants à modifier>],\n'
        '  "location_additions": [<nouveaux décors>],\n'
        '  "object_updates": [<objets existants à modifier>],\n'
        '  "object_additions": [<nouveaux objets>]\n'
        "}\n"
        "Chaque page dans page_updates doit inclure tous ses champs (page_number, layout, panels…). "
        "Chaque personnage/décor/objet doit inclure tous ses champs obligatoires (id, name, etc.). "
        "Retourne un tableau vide pour les catégories non modifiées. "
        "Ne génère PAS les éléments qui n'ont pas besoin de changer."
    )
    user = (
        f"Suggestion à appliquer :\n{suggestion}\n\n"
        f"Scénario actuel :\n{json.dumps(script_payload, ensure_ascii=False, indent=2)}"
    )

    started_at, started = stats_module.start_timer()
    usage: dict = {}
    raw = ""
    with trace_module.node(
        f"apply_suggestion:{name}", "llm_call",
        project_dir=proj_dir,
    ) as _tn2:
        _tn2.set_model(provider, model)
        _tn2.set_prompt(user)
        _tn2.set_extra(system_prompt=system, suggestion=suggestion)
        try:
            if provider == "anthropic":
                client = secret_store.anthropic_client()
                response = client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = response.content[0].text
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            elif provider == "xai":
                client = secret_store.xai_client()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            else:
                client = secret_store.openai_client()
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content
                usage = stats_module.normalise_usage(getattr(response, "usage", None))
            _tn2.set_usage(usage)
            _tn2.set_outputs({"raw_chars": len(raw or "")})
        except Exception as exc:
            _tn2.set_extra(error=str(exc))
            stats_module.record_event(
                proj_dir,
                step="coherence",
                target_id=name,
                target_kind="script",
                operation="apply_suggestion",
                provider=provider,
                model=model,
                timer=stats_module.stop_timer(started_at, started),
                status="error",
                usage=usage,
                prompt=user,
                extra={"retouch": True},
            )
            raise RuntimeError(f"Erreur LLM : {exc}") from exc

    stats_module.record_event(
        proj_dir,
        step="coherence",
        target_id=name,
        target_kind="script",
        operation="apply_suggestion",
        provider=provider,
        model=model,
        timer=stats_module.stop_timer(started_at, started),
        usage=usage,
        prompt=user,
        extra={"retouch": True},
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                raise RuntimeError("Réponse LLM non parseable.")
        else:
            raise RuntimeError("Réponse LLM vide ou invalide.")

    if not isinstance(data, dict):
        raise RuntimeError("Réponse LLM invalide (objet attendu).")

    changes = {
        "page_updates": 0,
        "character_updates": 0,
        "character_additions": 0,
        "location_updates": 0,
        "location_additions": 0,
        "object_updates": 0,
        "object_additions": 0,
    }

    for page_data in data.get("page_updates") or []:
        try:
            page = Page.model_validate(page_data)
            idx = next((i for i, p in enumerate(bd_script.pages) if p.page_number == page.page_number), None)
            if idx is not None:
                bd_script.pages[idx] = page
                composed = proj_dir / "pages" / f"page_{page.page_number:02d}.png"
                if composed.exists():
                    mark_stale(proj_dir, "compose", f"page_{page.page_number}")
                changes["page_updates"] += 1
        except Exception:
            continue

    existing_char_ids = {c.id for c in bd_script.characters}
    for char_data in data.get("character_updates") or []:
        try:
            char = ScriptCharacter.model_validate(char_data)
            idx = next((i for i, c in enumerate(bd_script.characters) if c.id == char.id), None)
            if idx is not None:
                bd_script.characters[idx] = char
                ref_img = proj_dir / "references" / "characters" / f"{char.id}.png"
                if ref_img.exists():
                    mark_stale(proj_dir, "references", char.id)
                changes["character_updates"] += 1
        except Exception:
            continue

    for char_data in data.get("character_additions") or []:
        try:
            char = ScriptCharacter.model_validate(char_data)
            if char.id not in existing_char_ids:
                bd_script.characters.append(char)
                existing_char_ids.add(char.id)
                changes["character_additions"] += 1
        except Exception:
            continue

    existing_loc_ids = {loc.id for loc in bd_script.locations}
    for loc_data in data.get("location_updates") or []:
        try:
            loc = ScriptLocation.model_validate(loc_data)
            idx = next((i for i, l in enumerate(bd_script.locations) if l.id == loc.id), None)
            if idx is not None:
                bd_script.locations[idx] = loc
                ref_img = proj_dir / "references" / "locations" / f"{loc.id}.png"
                if ref_img.exists():
                    mark_stale(proj_dir, "references", loc.id)
                changes["location_updates"] += 1
        except Exception:
            continue

    for loc_data in data.get("location_additions") or []:
        try:
            loc = ScriptLocation.model_validate(loc_data)
            if loc.id not in existing_loc_ids:
                bd_script.locations.append(loc)
                existing_loc_ids.add(loc.id)
                changes["location_additions"] += 1
        except Exception:
            continue

    existing_obj_ids = {o.id for o in bd_script.objects}
    for obj_data in data.get("object_updates") or []:
        try:
            obj = ScriptObject.model_validate(obj_data)
            idx = next((i for i, o in enumerate(bd_script.objects) if o.id == obj.id), None)
            if idx is not None:
                bd_script.objects[idx] = obj
                ref_img = proj_dir / "references" / "objects" / f"{obj.id}.png"
                if ref_img.exists():
                    mark_stale(proj_dir, "references", obj.id)
                changes["object_updates"] += 1
        except Exception:
            continue

    for obj_data in data.get("object_additions") or []:
        try:
            obj = ScriptObject.model_validate(obj_data)
            if obj.id not in existing_obj_ids:
                bd_script.objects.append(obj)
                existing_obj_ids.add(obj.id)
                changes["object_additions"] += 1
        except Exception:
            continue

    bd_script.save(script_path)
    coh_idx = read_coherence_index(proj_dir)
    coh_idx["dirty"] = True
    coh_idx["suggestions"] = [s for s in coh_idx.get("suggestions", []) if s.get("message") != suggestion]
    write_coherence_index(proj_dir, coh_idx)
    return {"applied": True, "changes": changes}
