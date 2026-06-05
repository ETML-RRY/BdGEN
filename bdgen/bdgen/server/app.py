"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Request,
    UploadFile,
    File,
    Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import secret_store
from .. import style_from_image as style_module
from .. import trace as trace_module
from .. import upscale as upscale_module
from .. import versioning as versioning_module
from ..service import (
    cascades,
    coherence,
    feedback_ops,
    import_export,
    indices,
    inpaint,
    lifecycle,
    manual_edits,
    photos,
    pipeline,
    stale_detection,
    style_refs,
)
from ..service import config as svc_config
from ..service import constants as svc_const
from ..service import state as svc_state
from ..models import BackCover, BdGenInput, Cover, Page, ScriptCharacter, ScriptLocation, ScriptObject
from .jobs import JobManager


load_dotenv()
logger = logging.getLogger(__name__)


def _output_root() -> Path:
    return Path(os.environ.get("BDGEN_OUTPUT_ROOT", "./output")).resolve()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.jobs = JobManager()
    app.state.jobs.attach_loop(asyncio.get_running_loop())
    try:
        lifecycle.seed_example_project(_output_root())
    except Exception:
        logger.exception("Unable to seed bundled example project.")
    yield


def create_app(static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="BdGEN Web", lifespan=_lifespan)

    # Permissive CORS in dev; in production the Vite build is served from the
    # same origin so CORS is irrelevant.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_api(app)

    if static_dir is not None and static_dir.exists():
        # Mount the bundled JS/CSS assets at /assets, then add an SPA fallback
        # that serves index.html for every other non-API path so React Router
        # works on hard refresh.
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )
        index_html = static_dir / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):  # noqa: ARG001
            file = static_dir / full_path
            if file.is_file():
                return FileResponse(file)
            if index_html.exists():
                return FileResponse(index_html)
            raise HTTPException(404, "Frontend not built.")

    return app


# --- API ---


class FeedbackPayload(BaseModel):
    feedback: str


class PageFeedbackPayload(BaseModel):
    feedback: str
    cascade: bool = False


class ImageFeedbackPayload(BaseModel):
    step: str  # "references" | "compose"
    target: str
    feedback: str


class StartStepPayload(BaseModel):
    preview_pages: int | None = None
    force_ids: list[str] | None = None
    force_all: bool = False


class SecretCreatePayload(BaseModel):
    password: str
    secrets: dict[str, str] = {}
    overwrite: bool = False


class SecretUnlockPayload(BaseModel):
    password: str


class SecretUpdatePayload(BaseModel):
    value: str | None = None
    password: str | None = None


def _register_api(app: FastAPI) -> None:

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    # --- Local encrypted API-key vault ---

    @app.get("/api/secrets/status")
    def secrets_status() -> dict:
        return secret_store.status()

    @app.post("/api/secrets/create")
    def secrets_create(payload: SecretCreatePayload) -> dict:
        try:
            return secret_store.create_vault(
                payload.password,
                payload.secrets,
                overwrite=payload.overwrite,
            )
        except secret_store.VaultError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/secrets/unlock")
    def secrets_unlock(payload: SecretUnlockPayload) -> dict:
        try:
            return secret_store.unlock_vault(payload.password)
        except secret_store.VaultError as e:
            raise HTTPException(401, str(e))

    @app.post("/api/secrets/lock")
    def secrets_lock() -> dict:
        secret_store.lock_vault()
        return secret_store.status()

    @app.put("/api/secrets/providers/{provider}")
    def secrets_update(provider: str, payload: SecretUpdatePayload) -> dict:
        secret_name = secret_store.PROVIDERS.get(provider)
        if secret_name is None:
            raise HTTPException(404, "Provider inconnu.")
        try:
            secret_store.update_secret(secret_name, payload.value)
            if payload.password:
                return secret_store.save_unlocked(payload.password)
            return secret_store.status()
        except secret_store.VaultLocked as e:
            raise HTTPException(423, str(e))
        except secret_store.VaultError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/secrets/providers/{provider}")
    def secrets_delete(provider: str, payload: SecretUpdatePayload = Body(default=SecretUpdatePayload())) -> dict:
        secret_name = secret_store.PROVIDERS.get(provider)
        if secret_name is None:
            raise HTTPException(404, "Provider inconnu.")
        try:
            secret_store.update_secret(secret_name, None)
            if payload.password:
                return secret_store.save_unlocked(payload.password)
            return secret_store.status()
        except secret_store.VaultLocked as e:
            raise HTTPException(423, str(e))
        except secret_store.VaultError as e:
            raise HTTPException(400, str(e))

    # --- Projects ---

    @app.get("/api/projects")
    def list_projects() -> dict:
        root = _output_root()
        items = []
        for s in lifecycle.list_projects(root):
            d = s.to_dict()
            rel = d.pop("thumbnail_rel", None)
            d["thumbnail_url"] = _file_url(s.name, rel, lifecycle.get_project_dir(s.name, root) / rel) if rel else None
            items.append(d)
        return {"projects": items}

    @app.get("/api/projects/{name}")
    def get_project(name: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        cfg_path = proj_dir / svc_const.PROJECT_CONFIG_NAME
        script_path = proj_dir / "bdgen-script.json"
        cfg = None
        try:
            cfg = svc_config.load_config(name, _output_root())
            cfg_dict = cfg.to_portable_dict(cfg_path)
        except FileNotFoundError:
            cfg_dict = None
        bd_script = svc_config.load_script_if_present(name, _output_root())
        script_dict = bd_script.to_portable_dict(script_path) if bd_script else None
        state = svc_state.derive_state(proj_dir)
        stale_idx = indices.read_stale_index(proj_dir)
        coherence_idx = indices.read_coherence_index(proj_dir)
        # Per-step asset listings the frontend uses to flip through items.
        refs = {"characters": [], "locations": [], "objects": []}
        composed = []
        upscaled = []
        stale_refs = set(stale_idx.get("references", []))
        stale_compose = set(stale_idx.get("compose", []))
        upscale_dir = photos.get_upscale_output_dir(proj_dir, bd_script, cfg)
        upscale_ext = (cfg_dict or {}).get("generation_options", {}).get("upscale", {}).get("output_format", "png")
        if bd_script is not None:
            for c in bd_script.characters:
                ref_path = proj_dir / "references" / "characters" / f"{c.id}.png"
                refs["characters"].append(
                    {
                        "id": c.id,
                        "name": c.name,
                        "physical_description": c.physical_description,
                        "outfit": c.outfit,
                        "image_url": _file_url(name, f"references/characters/{c.id}.png", ref_path),
                        "stale": c.id in stale_refs and ref_path.exists(),
                    }
                )
            for l in bd_script.locations:
                ref_path = proj_dir / "references" / "locations" / f"{l.id}.png"
                refs["locations"].append(
                    {
                        "id": l.id,
                        "name": l.name,
                        "description": l.description,
                        "image_url": _file_url(name, f"references/locations/{l.id}.png", ref_path),
                        "stale": l.id in stale_refs and ref_path.exists(),
                    }
                )
            for o in bd_script.objects:
                ref_path = proj_dir / "references" / "objects" / f"{o.id}.png"
                refs["objects"].append(
                    {
                        "id": o.id,
                        "name": o.name,
                        "description": o.description,
                        "image_url": _file_url(name, f"references/objects/{o.id}.png", ref_path),
                        "stale": o.id in stale_refs and ref_path.exists(),
                    }
                )
            if bd_script.cover is not None:
                composed.append(_compose_entry(name, "cover", proj_dir, stale_compose))
                upscaled.append(_upscale_entry(name, "cover", proj_dir, upscale_dir, upscale_ext))
            for p in bd_script.pages:
                composed.append(_compose_entry(name, f"page_{p.page_number}", proj_dir, stale_compose))
                upscaled.append(_upscale_entry(name, f"page_{p.page_number}", proj_dir, upscale_dir, upscale_ext))
            if bd_script.back_cover is not None:
                composed.append(_compose_entry(name, "back", proj_dir, stale_compose))
                upscaled.append(_upscale_entry(name, "back", proj_dir, upscale_dir, upscale_ext))
        character_photos: dict[str, list[dict]] = {}
        for cid, slots in photos.list_character_photos_with_slots(proj_dir).items():
            character_photos[cid] = [
                {"slot": slot, "url": _file_url(name, photo_path.relative_to(proj_dir).as_posix(), photo_path)}
                for slot, photo_path in slots
            ]
        location_photos: dict[str, list[dict]] = {}
        for lid, slots in photos.list_location_photos_with_slots(proj_dir).items():
            location_photos[lid] = [
                {"slot": slot, "url": _file_url(name, photo_path.relative_to(proj_dir).as_posix(), photo_path)}
                for slot, photo_path in slots
            ]
        object_photos: dict[str, list[dict]] = {}
        for oid, slots in photos.list_object_photos_with_slots(proj_dir).items():
            object_photos[oid] = [
                {"slot": slot, "url": _file_url(name, photo_path.relative_to(proj_dir).as_posix(), photo_path)}
                for slot, photo_path in slots
            ]
        reference_images: dict[str, dict[str, str | None]] = {
            "characters": {},
            "locations": {},
            "objects": {},
        }
        for kind, items in photos.list_reference_images(proj_dir).items():
            for ref_id, ref_path in items.items():
                reference_images[kind][ref_id] = _file_url(name, f"references/{kind}/{ref_id}.png", ref_path)
        return {
            "name": name,
            "state": state,
            "config": cfg_dict,
            "script": script_dict,
            "references": refs,
            "composed": composed,
            "upscaled": upscaled,
            "upscale": (cfg_dict or {}).get("generation_options", {}).get("upscale", {}),
            "upscale_available": upscale_module.is_available(),
            "stale": stale_idx,
            "coherence": coherence_idx,
            "pdf_url": _file_url(name, f"{name}.pdf", proj_dir / f"{name}.pdf"),
            "character_photos": character_photos,
            "location_photos": location_photos,
            "object_photos": object_photos,
            "reference_images": reference_images,
        }

    @app.get("/api/projects/{name}/statistics")
    def get_project_statistics(name: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        return svc_state.project_statistics(name, _output_root())

    # --- Developer-only trace endpoints (BDGEN_DEBUG=1) ---------------------
    # Returns 404 when debug mode is off so prod surfaces no extra attack
    # surface and the frontend can't accidentally enable the panel.

    @app.get("/api/debug/enabled")
    def get_debug_enabled() -> dict:
        return {"enabled": trace_module.enabled()}

    @app.get("/api/projects/{name}/traces")
    def list_project_traces(name: str) -> dict:
        if not trace_module.enabled():
            raise HTTPException(404, "Trace endpoints disabled.")
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        project_dir = _output_root() / name
        return {"sessions": trace_module.list_sessions(project_dir)}

    @app.get("/api/projects/{name}/traces/{session_id}")
    def get_project_trace(name: str, session_id: str) -> dict:
        if not trace_module.enabled():
            raise HTTPException(404, "Trace endpoints disabled.")
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        project_dir = _output_root() / name
        nodes = trace_module.session_nodes(project_dir, session_id)
        if not nodes:
            raise HTTPException(404, "Session inconnue.")
        return {"session_id": session_id, "nodes": nodes}

    @app.post("/api/projects")
    def create_project(payload: dict = Body(...)) -> dict:
        try:
            cfg = BdGenInput.model_validate(payload)
        except Exception as e:
            raise HTTPException(400, f"Configuration invalide : {e}")
        if not cfg.project:
            raise HTTPException(400, "Le champ 'project' est obligatoire.")
        if lifecycle.project_exists(cfg.project, _output_root()):
            raise HTTPException(409, f"Un projet « {cfg.project} » existe déjà.")
        svc_config.save_config(cfg, _output_root())
        return {"name": cfg.project}

    @app.put("/api/projects/{name}")
    def update_project(name: str, payload: dict = Body(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = BdGenInput.model_validate(payload)
        except Exception as e:
            raise HTTPException(400, f"Configuration invalide : {e}")
        if cfg.project != name:
            raise HTTPException(400, "Le champ 'project' ne peut pas être renommé via cette route.")
        stale_detection.detect_and_mark_stale(name, cfg, _output_root())
        svc_config.save_config(cfg, _output_root())
        return {"name": name}

    @app.delete("/api/projects/{name}")
    def delete_project(name: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(409, "Une génération est en cours sur ce projet.")
        lifecycle.delete_project(name, _output_root())
        return {"deleted": name}

    @app.post("/api/projects/{name}/duplicate")
    def duplicate_project(name: str, payload: dict = Body(default_factory=dict)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        data = payload or {}
        new_id = data.get("new_project") or None
        new_title = data.get("new_title") or None
        include_refs = bool(data.get("include_references", False))
        include_photos = bool(data.get("include_photos", True))
        include_style_ref = bool(data.get("include_style_reference", True))
        try:
            created = lifecycle.duplicate_project(
                name,
                new_id,
                _output_root(),
                include_references=include_refs,
                include_photos=include_photos,
                include_style_reference=include_style_ref,
                new_title=new_title,
            )
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(400, f"Duplication impossible : {e}")
        return {"name": created}

    @app.post("/api/projects/{name}/restyle")
    def restyle_project(name: str, payload: dict = Body(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(409, "Une génération est en cours sur ce projet.")
        style = (payload or {}).get("style")
        if not isinstance(style, dict):
            raise HTTPException(400, "Le champ 'style' est obligatoire.")
        try:
            deleted = lifecycle.restyle_project(name, style, _output_root())
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(400, f"Re-stylage impossible : {e}")
        return {"ok": True, "deleted": deleted}

    @app.get("/api/projects/{name}/feedback")
    def list_feedback(name: str) -> dict:
        from ..feedback import FeedbackStore, feedback_path_for

        proj_dir = lifecycle.get_project_dir(name, _output_root())
        store = FeedbackStore.load_or_empty(feedback_path_for(proj_dir / "bdgen-script.json"))
        return {"items": [item.model_dump(mode="json") for item in store.items]}

    @app.get("/api/projects/{name}/files/{path:path}")
    def serve_project_file(name: str, path: str):
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        target = (proj_dir / path).resolve()
        # Path traversal guard
        try:
            target.relative_to(proj_dir.resolve())
        except ValueError:
            raise HTTPException(400, "Chemin invalide.")
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "Fichier introuvable.")
        return FileResponse(target)

    # --- Per-file version history -------------------------------------------
    # Every overwrite of a generated artefact archives the previous content
    # under <parent>/.versions/<filename>/<ISO-ts>.<ext> via
    # bdgen.versioning.archive_before_write. These endpoints expose that
    # history to the UI.

    def _resolve_within_project(name: str, path: str) -> tuple[Path, Path]:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        target = (proj_dir / path).resolve()
        try:
            target.relative_to(proj_dir.resolve())
        except ValueError:
            raise HTTPException(400, "Chemin invalide.")
        return proj_dir, target

    @app.get("/api/projects/{name}/versions/{path:path}")
    def list_file_versions(name: str, path: str) -> dict:
        proj_dir, target = _resolve_within_project(name, path)
        versions = versioning_module.list_versions(target)
        for v in versions:
            archived = versioning_module.archived_path(target, v["filename"])
            v["relpath"] = str(archived.resolve().relative_to(proj_dir.resolve()))
        current = versioning_module.current_info(target)
        if current is not None:
            current["relpath"] = path
        return {
            "current": current,
            "versions": versions,
        }

    @app.post("/api/projects/{name}/versions/{path:path}/restore")
    def restore_file_version(name: str, path: str, payload: dict = Body(...)) -> dict:
        _, target = _resolve_within_project(name, path)
        version_id = (payload or {}).get("version_id")
        if not isinstance(version_id, str) or not version_id:
            raise HTTPException(400, "Champ 'version_id' obligatoire.")
        try:
            return versioning_module.restore_version(target, version_id)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))

    # --- Import / export ---

    @app.get("/api/projects/{name}/export")
    def export_project(name: str):
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = import_export.export_zip(name, _output_root())
        return Response(
            content=blob,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.bdgen"',
            },
        )

    @app.post("/api/projects/import")
    async def import_project(
        file: UploadFile = File(...),
        new_project: str = Form(default=""),
        new_title: str = Form(default=""),
    ) -> dict:
        blob = await file.read()
        try:
            project_name = import_export.import_zip(
                blob,
                _output_root(),
                new_project_id=new_project or None,
                new_title=new_title or None,
            )
        except Exception as e:
            raise HTTPException(400, f"Archive invalide : {e}")
        return {"name": project_name}

    # --- References bundle (.bdrefs) — share a cast across projects ---

    @app.get("/api/projects/{name}/references/exportable")
    def list_exportable_refs(name: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            return import_export.list_exportable_references(name, _output_root())
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/projects/{name}/references/export")
    def export_refs_bundle(name: str, payload: dict = Body(default_factory=dict)) -> Response:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            blob = import_export.export_references_bundle(
                name,
                character_ids=list((payload or {}).get("characters") or []),
                location_ids=list((payload or {}).get("locations") or []),
                object_ids=list((payload or {}).get("objects") or []),
                output_root=_output_root(),
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        return Response(
            content=blob,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.bdrefs"',
            },
        )

    @app.post("/api/projects/{name}/references/import")
    async def import_refs_bundle(name: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            return import_export.import_references_bundle(name, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))

    # --- Jobs ---

    @app.get("/api/jobs/current")
    def current_job() -> dict:
        snap = app.state.jobs.current()
        return {"job": snap.to_dict() if snap else None}

    @app.post("/api/jobs/current/interrupt")
    def interrupt_job() -> dict:
        ok = app.state.jobs.interrupt()
        if not ok:
            raise HTTPException(409, "Aucune génération en cours.")
        return {"interrupting": True}

    @app.post("/api/jobs/current/clear")
    def clear_job() -> dict:
        app.state.jobs.clear_finished()
        return {"ok": True}

    @app.get("/api/jobs/current/events")
    async def stream_events(request: Request):
        bus = app.state.jobs.bus
        q, history = bus.subscribe()

        async def gen():
            try:
                # Replay history first so a fresh subscriber catches up.
                for payload in history:
                    yield _sse(payload)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        # keepalive
                        yield ":keepalive\n\n"
                        continue
                    yield _sse(payload)
                    if payload.get("type") == "terminal":
                        # Stream stays open so the client can choose when to close.
                        pass
            finally:
                bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    # --- Step runners ---

    def _start(step, name: str, runner) -> dict:
        try:
            snap = app.state.jobs.start(name, step, runner)
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"job": snap.to_dict()}

    @app.post("/api/projects/{name}/steps/script/start")
    def start_script(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = svc_config.load_config(name, _output_root())
        except FileNotFoundError:
            raise HTTPException(400, "Configuration du projet introuvable.")
        _check_api_key(cfg.generation_options.script_model.provider)

        if payload.force_all:
            proj_dir = lifecycle.get_project_dir(name, _output_root())
            script_path = proj_dir / "bdgen-script.json"
            if script_path.exists():
                bd_script = svc_config.load_script_if_present(name, _output_root())
                if bd_script:
                    ref_ids = (
                        [c.id for c in bd_script.characters]
                        + [l.id for l in bd_script.locations]
                        + [o.id for o in bd_script.objects]
                    )
                    compose_ids = []
                    if bd_script.cover is not None:
                        compose_ids.append("cover")
                    for p in bd_script.pages:
                        compose_ids.append(f"page_{p.page_number}")
                    if bd_script.back_cover is not None:
                        compose_ids.append("back")
                    if ref_ids:
                        indices.mark_stale(proj_dir, "references", ref_ids)
                    if compose_ids:
                        indices.mark_stale(proj_dir, "compose", compose_ids)
                script_path.unlink()

        def runner(reporter, interrupt):
            pipeline.run_step_script(
                name,
                reporter,
                interrupt,
                output_root=_output_root(),
                preview_pages=payload.preview_pages,
            )

        return _start("script", name, runner)

    @app.post("/api/projects/{name}/steps/references/start")
    def start_references(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = svc_config.load_config(name, _output_root())
        except FileNotFoundError:
            raise HTTPException(400, "Configuration du projet introuvable.")
        _check_api_key(cfg.generation_options.image_model.provider)

        force_ids = payload.force_ids
        if payload.force_all and not force_ids:
            bd_script = svc_config.load_script_if_present(name, _output_root())
            if bd_script:
                force_ids = (
                    [c.id for c in bd_script.characters]
                    + [l.id for l in bd_script.locations]
                    + [o.id for o in bd_script.objects]
                )

        def runner(reporter, interrupt):
            pipeline.run_step_references(
                name,
                reporter,
                interrupt,
                output_root=_output_root(),
                force_ids=force_ids,
            )

        return _start("references", name, runner)

    @app.post("/api/projects/{name}/steps/compose/start")
    def start_compose(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = svc_config.load_config(name, _output_root())
        except FileNotFoundError:
            raise HTTPException(400, "Configuration du projet introuvable.")
        _check_api_key(cfg.generation_options.image_model.provider)

        force_ids = payload.force_ids
        if payload.force_all and not force_ids:
            bd_script = svc_config.load_script_if_present(name, _output_root())
            if bd_script:
                ids = []
                if bd_script.cover is not None:
                    ids.append("cover")
                for p in bd_script.pages:
                    ids.append(f"page_{p.page_number}")
                if bd_script.back_cover is not None:
                    ids.append("back")
                force_ids = ids

        def runner(reporter, interrupt):
            pipeline.run_step_compose(
                name,
                reporter,
                interrupt,
                output_root=_output_root(),
                force_ids=force_ids,
            )

        return _start("compose", name, runner)

    @app.post("/api/projects/{name}/steps/upscale/start")
    def start_upscale(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = svc_config.load_config(name, _output_root())
        except FileNotFoundError:
            raise HTTPException(400, "Configuration du projet introuvable.")
        if not cfg.generation_options.upscale.enabled:
            raise HTTPException(
                400,
                "L'upscale n'est pas activé pour ce projet. Activez-le dans la section Préparation.",
            )
        if not upscale_module.is_available():
            raise HTTPException(
                400,
                "REPLICATE_API_TOKEN non défini. Ajoutez votre clé API Replicate dans le fichier .env du serveur.",
            )

        def runner(reporter, interrupt):
            pipeline.run_step_upscale(
                name,
                reporter,
                interrupt,
                output_root=_output_root(),
                force_ids=payload.force_ids,
            )

        return _start("upscale", name, runner)

    # --- Targeted refinement (synchronous) ---

    @app.post("/api/projects/{name}/refine/character/{character_id}")
    def refine_character(name: str, character_id: str, payload: FeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_character(name, character_id, payload.feedback, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/location/{location_id}")
    def refine_location(name: str, location_id: str, payload: FeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_location(name, location_id, payload.feedback, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/object/{object_id}")
    def refine_object(name: str, object_id: str, payload: FeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_object(name, object_id, payload.feedback, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/cover")
    def refine_cover(name: str, payload: FeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_cover(name, payload.feedback, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/back_cover")
    def refine_back_cover(name: str, payload: FeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_back_cover(name, payload.feedback, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/page/{page_number}")
    def refine_page(name: str, page_number: int, payload: PageFeedbackPayload) -> dict:
        try:
            feedback_ops.add_feedback_and_regenerate_page(
                name,
                page_number,
                payload.feedback,
                cascade=payload.cascade,
                output_root=_output_root(),
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.put("/api/projects/{name}/script/pages/{page_number}")
    def update_script_page(name: str, page_number: int, payload: dict = Body(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(
                    409,
                    "Une generation est en cours sur ce projet.",
                )
        try:
            page = Page.model_validate(payload)
            manual_edits.update_script_page_manual(
                name,
                page_number,
                page.model_dump(mode="json"),
                _output_root(),
            )
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Planche invalide : {e}")
        return {"ok": True}

    @app.get("/api/projects/{name}/script/config-diff")
    def get_config_script_diff(name: str) -> dict:
        """Return the diff between bdgen.json and bdgen-script.json (no LLM call)."""
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        return coherence.get_config_script_diff(name, _output_root())

    @app.post("/api/projects/{name}/script/sync-config")
    def sync_script_with_config(name: str, payload: dict | None = Body(default=None)) -> dict:
        """Integrate config changes into the existing script via LLM (no full rewrite).

        ``payload.removals`` ({characters, locations, objects} → list of ids)
        lists entities the user chose to drop from the script after removing
        them from the config; they are deleted with a cascade and the dropped
        pages are regenerated.
        """
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            cfg = svc_config.load_config(name, _output_root())
            _check_api_key(cfg.generation_options.script_model.provider)
        except FileNotFoundError:
            _check_api_key("openai")
        removals = (payload or {}).get("removals") if isinstance(payload, dict) else None
        try:
            result = coherence.sync_script_with_config(name, _output_root(), removals=removals)
        except Exception as e:
            raise HTTPException(400, str(e))
        result["job"] = _maybe_autostart_script(name, result, True)
        return result

    @app.post("/api/projects/{name}/script/coherence/check")
    def check_script_coherence(name: str) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            return coherence.check_script_coherence(name, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.post("/api/projects/{name}/script/suggestions/apply")
    def apply_script_suggestion(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        suggestion = (payload or {}).get("suggestion", "")
        if not suggestion:
            raise HTTPException(400, "suggestion manquante")
        try:
            return coherence.apply_global_suggestion(name, suggestion, _output_root())
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.put("/api/projects/{name}/script/characters/{character_id}")
    def update_script_character(name: str, character_id: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            character = ScriptCharacter.model_validate(payload)
            manual_edits.update_script_character_manual(
                name, character_id, character.model_dump(mode="json"), _output_root()
            )
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Personnage invalide : {e}")
        return {"ok": True}

    @app.post("/api/projects/{name}/script/characters")
    def add_script_character(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            character = ScriptCharacter.model_validate(payload)
            manual_edits.add_script_character_manual(name, character.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Personnage invalide : {e}")
        return {"ok": True}

    @app.put("/api/projects/{name}/script/locations/{location_id}")
    def update_script_location(name: str, location_id: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            location = ScriptLocation.model_validate(payload)
            manual_edits.update_script_location_manual(
                name, location_id, location.model_dump(mode="json"), _output_root()
            )
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Decor invalide : {e}")
        return {"ok": True}

    @app.post("/api/projects/{name}/script/locations")
    def add_script_location(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            location = ScriptLocation.model_validate(payload)
            manual_edits.add_script_location_manual(name, location.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Decor invalide : {e}")
        return {"ok": True}

    @app.put("/api/projects/{name}/script/objects/{object_id}")
    def update_script_object(name: str, object_id: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            obj = ScriptObject.model_validate(payload)
            manual_edits.update_script_object_manual(name, object_id, obj.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Objet invalide : {e}")
        return {"ok": True}

    @app.post("/api/projects/{name}/script/objects")
    def add_script_object(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            obj = ScriptObject.model_validate(payload)
            manual_edits.add_script_object_manual(name, obj.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Objet invalide : {e}")
        return {"ok": True}

    @app.put("/api/projects/{name}/script/cover")
    def update_script_cover(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            cover = Cover.model_validate(payload)
            manual_edits.update_script_cover_manual(name, cover.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Couverture invalide : {e}")
        return {"ok": True}

    @app.put("/api/projects/{name}/script/back-cover")
    def update_script_back_cover(name: str, payload: dict = Body(...)) -> dict:
        _ensure_manual_script_edit_allowed(app, name, _output_root())
        try:
            back_cover = BackCover.model_validate(payload)
            manual_edits.update_script_back_cover_manual(name, back_cover.model_dump(mode="json"), _output_root())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"4e de couverture invalide : {e}")
        return {"ok": True}

    @app.post("/api/projects/{name}/inpaint/{step}/{target_id}")
    async def inpaint_image_endpoint(
        name: str,
        step: str,
        target_id: str,
        prompt: str = Form(...),
        mask: UploadFile = File(...),
    ) -> dict:
        if step not in ("references", "compose"):
            raise HTTPException(400, "Étape invalide (references ou compose).")
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(
                    409, "Une génération est en cours. Interrompez-la avant de lancer une retouche ciblée."
                )
        mask_bytes = await mask.read()
        try:
            new_path = await asyncio.to_thread(
                inpaint.inpaint_image,
                name,
                step,
                target_id,
                mask_bytes,
                prompt,
                _output_root(),
            )
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except NotImplementedError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Retouche échouée : {e}")
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        try:
            rel = new_path.relative_to(proj_dir).as_posix()
        except ValueError:
            raise HTTPException(500, "Chemin de résultat invalide.")
        return {
            "ok": True,
            "image_url": _file_url(name, rel, new_path),
        }

    @app.post("/api/projects/{name}/feedback/image")
    def add_image_feedback(name: str, payload: ImageFeedbackPayload) -> dict:
        if payload.step not in ("references", "compose"):
            raise HTTPException(400, "Étape invalide.")
        inpaint.record_image_feedback(
            name,
            payload.step,
            payload.target,
            payload.feedback,
            _output_root(),  # type: ignore[arg-type]
        )
        return {"ok": True}

    # --- Delete a character / location (cascades to script) ---

    @app.get("/api/projects/{name}/characters/{character_id}/delete-preview")
    def preview_delete_char(name: str, character_id: str) -> dict:
        try:
            return cascades.preview_delete_character(name, character_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{name}/locations/{location_id}/delete-preview")
    def preview_delete_loc(name: str, location_id: str) -> dict:
        try:
            return cascades.preview_delete_location(name, location_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{name}/objects/{object_id}/delete-preview")
    def preview_delete_obj(name: str, object_id: str) -> dict:
        try:
            return cascades.preview_delete_object(name, object_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.delete("/api/projects/{name}/characters/{character_id}")
    def delete_character(
        name: str,
        character_id: str,
        auto_regenerate: bool = True,
    ) -> dict:
        try:
            info = cascades.delete_character_and_cascade(name, character_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))
        info["job"] = _maybe_autostart_script(name, info, auto_regenerate)
        return info

    @app.delete("/api/projects/{name}/locations/{location_id}")
    def delete_location(
        name: str,
        location_id: str,
        auto_regenerate: bool = True,
    ) -> dict:
        try:
            info = cascades.delete_location_and_cascade(name, location_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))
        info["job"] = _maybe_autostart_script(name, info, auto_regenerate)
        return info

    @app.delete("/api/projects/{name}/objects/{object_id}")
    def delete_object(
        name: str,
        object_id: str,
        auto_regenerate: bool = True,
    ) -> dict:
        try:
            info = cascades.delete_object_and_cascade(name, object_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))
        info["job"] = _maybe_autostart_script(name, info, auto_regenerate)
        return info

    def _maybe_autostart_script(name: str, info: dict, auto: bool) -> dict | None:
        """Auto-launch the script step when the deletion truncated pages.

        Returns the job snapshot (dict) on success, None otherwise. A 409 from
        the JobManager (another job running) is swallowed: the deletion
        already happened on disk, the user can relaunch from the UI.
        """
        if not auto or info.get("pages_dropped", 0) <= 0:
            return None

        def runner(reporter, interrupt):
            pipeline.run_step_script(name, reporter, interrupt, output_root=_output_root())

        try:
            snap = app.state.jobs.start(name, "script", runner)
            return snap.to_dict()
        except RuntimeError:
            return None

    # --- Style-from-image tool (Préparation step assistant) ---

    @app.put("/api/projects/{name}/style-reference")
    async def set_style_reference(name: str, file: UploadFile = File(...)) -> dict:
        """Upload an image as the project's style reference (bdgen-style-ref.png).

        Subsequent image-generation runs (references, compose) will inject this
        image as the first input to every images.edit call so gpt-image-2 can
        *see* the target style rather than only reading a text description.
        """
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        p = style_refs.save_style_reference(name, blob, _output_root())
        return {
            "ok": True,
            "path": str(p),
            "url": _file_url(name, svc_const.STYLE_REF_NAME, p),
        }

    @app.get("/api/projects/{name}/style-reference")
    def get_style_reference_info(name: str) -> dict:
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        ref = style_refs.get_style_reference_path(proj_dir)
        return {
            "exists": ref is not None,
            "url": _file_url(name, svc_const.STYLE_REF_NAME, ref) if ref else None,
        }

    @app.post("/api/style-from-image")
    async def style_from_image_endpoint(
        file: UploadFile = File(...),
        language: str = Form("fr"),
    ) -> dict:
        """Turn an uploaded image into a style description AND a list of
        characters usable in the Préparation form. Output:
        ``{style: {...}, characters: [...]}``.
        """
        _check_api_key("openai")
        blob = await file.read()
        mime = file.content_type or "image/jpeg"
        try:
            result = style_module.extract(blob, mime, language=language)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"L'extraction a échoué : {e}")
        return result.model_dump(mode="json")

    @app.post("/api/character-from-photo")
    async def character_from_photo_endpoint(
        file: UploadFile = File(...),
        language: str = Form("fr"),
    ) -> dict:
        """Turn a portrait photo into a single character pre-fill payload:
        ``{name, physical_description, outfit, personality}``. The photo
        itself is NOT stored by this endpoint — the caller persists it via
        the per-character photo endpoint after the project exists.
        """
        _check_api_key("openai")
        blob = await file.read()
        mime = file.content_type or "image/jpeg"
        try:
            result = style_module.extract_character(blob, mime, language=language)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"L'extraction a échoué : {e}")
        return result.model_dump(mode="json")

    @app.post("/api/object-from-photo")
    async def object_from_photo_endpoint(
        file: UploadFile = File(...),
        language: str = Form("fr"),
    ) -> dict:
        """Turn a product/object photo into a single object pre-fill payload:
        ``{name, description}``. The photo itself is NOT stored by this
        endpoint — the caller persists it via the per-object photo endpoint
        after the project exists.
        """
        _check_api_key("openai")
        blob = await file.read()
        mime = file.content_type or "image/jpeg"
        try:
            result = style_module.extract_object(blob, mime, language=language)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"L'extraction a échoué : {e}")
        return result.model_dump(mode="json")

    @app.post("/api/location-from-photo")
    async def location_from_photo_endpoint(
        file: UploadFile = File(...),
        language: str = Form("fr"),
    ) -> dict:
        """Turn a place photo into a single location pre-fill payload:
        ``{name, description}``. The photo itself is NOT stored by this
        endpoint — the caller persists it via the per-location photo endpoint
        after the project exists.
        """
        _check_api_key("openai")
        blob = await file.read()
        mime = file.content_type or "image/jpeg"
        try:
            result = style_module.extract_location(blob, mime, language=language)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"L'extraction a échoué : {e}")
        return result.model_dump(mode="json")

    # --- Per-character reference photos ---

    @app.put("/api/projects/{name}/characters/{character_id}/photo")
    async def set_character_photo(name: str, character_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = photos.save_character_photo(name, character_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": 1,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/characters/{character_id}/photo")
    def remove_character_photo(name: str, character_id: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_character_photo(name, character_id, _output_root())
        return {"ok": True, "removed": removed}

    @app.post("/api/projects/{name}/characters/{character_id}/photos")
    async def add_character_photo(name: str, character_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            slot, p = photos.add_character_photo(name, character_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": slot,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/characters/{character_id}/photos/{slot}")
    def remove_character_photo_slot(name: str, character_id: str, slot: int) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_character_photo_slot(name, character_id, slot, _output_root())
        return {"ok": True, "removed": removed}

    # --- Per-object reference photos ---

    @app.put("/api/projects/{name}/objects/{object_id}/photo")
    async def set_object_photo(name: str, object_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = photos.save_object_photo(name, object_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": 1,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/objects/{object_id}/photo")
    def remove_object_photo(name: str, object_id: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_object_photo(name, object_id, _output_root())
        return {"ok": True, "removed": removed}

    @app.post("/api/projects/{name}/objects/{object_id}/photos")
    async def add_object_photo(name: str, object_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            slot, p = photos.add_object_photo(name, object_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": slot,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/objects/{object_id}/photos/{slot}")
    def remove_object_photo_slot(name: str, object_id: str, slot: int) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_object_photo_slot(name, object_id, slot, _output_root())
        return {"ok": True, "removed": removed}

    # --- Per-location reference photos ---

    @app.put("/api/projects/{name}/locations/{location_id}/photo")
    async def set_location_photo(name: str, location_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = photos.save_location_photo(name, location_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": 1,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/locations/{location_id}/photo")
    def remove_location_photo(name: str, location_id: str) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_location_photo(name, location_id, _output_root())
        return {"ok": True, "removed": removed}

    @app.post("/api/projects/{name}/locations/{location_id}/photos")
    async def add_location_photo(name: str, location_id: str, file: UploadFile = File(...)) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            slot, p = photos.add_location_photo(name, location_id, blob, _output_root())
        except ValueError as e:
            raise HTTPException(400, str(e))
        proj_dir = lifecycle.get_project_dir(name, _output_root())
        return {
            "ok": True,
            "slot": slot,
            "url": _file_url(name, p.relative_to(proj_dir).as_posix(), p),
        }

    @app.delete("/api/projects/{name}/locations/{location_id}/photos/{slot}")
    def remove_location_photo_slot(name: str, location_id: str, slot: int) -> dict:
        if not lifecycle.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = photos.delete_location_photo_slot(name, location_id, slot, _output_root())
        return {"ok": True, "removed": removed}


def _check_api_key(provider: str) -> None:
    secret_name = secret_store.PROVIDERS.get(provider)
    if secret_name is None:
        raise HTTPException(400, f"Provider '{provider}' inconnu.")
    if not secret_store.get_secret(secret_name):
        raise HTTPException(
            400,
            f"Clé API manquante : {secret_name} est requis pour le provider '{provider}'. "
            "Configurez-la dans le coffre BdGEN.",
        )


def _file_url(project: str, rel: str, full_path: Path) -> str | None:
    """Build a cache-busted URL for a project file, or None if missing.

    Browsers cache image URLs aggressively. Without the ``?v=<mtime>`` suffix,
    a regenerated file (same URL, new bytes) keeps showing the old image until
    the user hits F5. Appending the file's mtime makes the URL change every
    time the file is rewritten, so the browser fetches the fresh bytes.
    """
    if not full_path.exists():
        return None
    try:
        v = int(full_path.stat().st_mtime)
    except OSError:
        v = 0
    return f"/api/projects/{project}/files/{rel}?v={v}"


def _target_relpath(target: str, kind: str) -> str | None:
    if target == "cover":
        return f"{kind}/cover.png"
    if target == "back":
        return f"{kind}/back.png"
    if target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except (ValueError, IndexError):
            return None
        return f"{kind}/page_{n:02d}.png"
    return None


def _compose_entry(
    project: str,
    target: str,
    proj_dir: Path,
    stale_set: set[str] | None = None,
) -> dict:
    """Build {id, image_url, stale} for a composed page target."""
    rel = _target_relpath(target, "pages")
    if rel is None:
        return {"id": target, "image_url": None, "stale": False}
    full = proj_dir / rel
    exists = full.exists()
    return {
        "id": target,
        "image_url": _file_url(project, rel, full),
        "stale": bool(stale_set and target in stale_set and exists),
    }


def _ensure_manual_script_edit_allowed(app: FastAPI, name: str, output_root: Path) -> None:
    if not lifecycle.project_exists(name, output_root):
        raise HTTPException(404, "Projet inconnu.")
    if app.state.jobs.is_running():
        current = app.state.jobs.current()
        if current and current.project == name:
            raise HTTPException(
                409,
                "Une generation est en cours sur ce projet.",
            )


def _upscale_entry(
    project: str,
    target: str,
    proj_dir: Path,
    upscale_dir: Path,
    output_format: str,
) -> dict:
    src_rel = _target_relpath(target, "pages")
    if src_rel is None:
        return {"id": target, "image_url": None, "stale": False}
    suffix = output_format if output_format.startswith(".") else f".{output_format}"
    if target == "cover":
        full = upscale_dir / f"cover{suffix}"
    elif target == "back":
        full = upscale_dir / f"back{suffix}"
    elif target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except (ValueError, IndexError):
            return {"id": target, "image_url": None, "stale": False}
        full = upscale_dir / f"page_{n:02d}{suffix}"
    else:
        return {"id": target, "image_url": None, "stale": False}
    try:
        rel = full.relative_to(proj_dir).as_posix()
    except ValueError:
        rel = None
    source = proj_dir / src_rel
    return {
        "id": target,
        "image_url": _file_url(project, rel, full) if rel is not None else None,
        "stale": photos.is_upscaled_stale(source, full),
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
