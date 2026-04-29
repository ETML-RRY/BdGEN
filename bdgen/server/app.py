"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import json
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

from .. import service
from .. import style_from_image as style_module
from ..models import BdGenInput
from .jobs import JobManager


load_dotenv()


def _output_root() -> Path:
    return Path(os.environ.get("BDGEN_OUTPUT_ROOT", "./output")).resolve()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.jobs = JobManager()
    app.state.jobs.attach_loop(asyncio.get_running_loop())
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
    # "low" | "medium" | "high" — overrides the project's image_model.quality
    # for this single run. Records the quality used per generated target so
    # the UI can flag drafts and offer a per-item upgrade.
    quality_override: str | None = None


def _register_api(app: FastAPI) -> None:

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    # --- Projects ---

    @app.get("/api/projects")
    def list_projects() -> dict:
        root = _output_root()
        items = []
        for s in service.list_projects(root):
            d = s.to_dict()
            rel = d.pop("thumbnail_rel", None)
            d["thumbnail_url"] = (
                _file_url(s.name, rel, service.get_project_dir(s.name, root) / rel)
                if rel
                else None
            )
            items.append(d)
        return {"projects": items}

    @app.get("/api/projects/{name}")
    def get_project(name: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = service.load_config(name, _output_root())
            cfg_dict = cfg.model_dump(mode="json")
        except FileNotFoundError:
            cfg_dict = None
        bd_script = service.load_script_if_present(name, _output_root())
        script_dict = bd_script.model_dump(mode="json") if bd_script else None
        proj_dir = service.get_project_dir(name, _output_root())
        state = service.derive_state(proj_dir)
        quality_idx = service.read_quality_index(proj_dir)
        stale_idx = service.read_stale_index(proj_dir)
        # Default quality to assume for items that pre-date the quality index.
        default_quality = (
            (cfg_dict or {})
            .get("generation_options", {})
            .get("image_model", {})
            .get("quality", "high")
        )
        # Per-step asset listings the frontend uses to flip through items.
        refs = {"characters": [], "locations": [], "objects": []}
        composed = []
        stale_refs = set(stale_idx.get("references", []))
        stale_compose = set(stale_idx.get("compose", []))
        if bd_script is not None:
            for c in bd_script.characters:
                ref_path = proj_dir / "references" / "characters" / f"{c.id}.png"
                refs["characters"].append({
                    "id": c.id,
                    "name": c.name,
                    "physical_description": c.physical_description,
                    "outfit": c.outfit,
                    "image_url": _file_url(
                        name, f"references/characters/{c.id}.png", ref_path
                    ),
                    "quality": _quality_for(
                        quality_idx, "references", c.id, ref_path, default_quality
                    ),
                    "stale": c.id in stale_refs and ref_path.exists(),
                })
            for l in bd_script.locations:
                ref_path = proj_dir / "references" / "locations" / f"{l.id}.png"
                refs["locations"].append({
                    "id": l.id,
                    "name": l.name,
                    "description": l.description,
                    "image_url": _file_url(
                        name, f"references/locations/{l.id}.png", ref_path
                    ),
                    "quality": _quality_for(
                        quality_idx, "references", l.id, ref_path, default_quality
                    ),
                    "stale": l.id in stale_refs and ref_path.exists(),
                })
            for o in bd_script.objects:
                ref_path = proj_dir / "references" / "objects" / f"{o.id}.png"
                refs["objects"].append({
                    "id": o.id,
                    "name": o.name,
                    "description": o.description,
                    "image_url": _file_url(
                        name, f"references/objects/{o.id}.png", ref_path
                    ),
                    "quality": _quality_for(
                        quality_idx, "references", o.id, ref_path, default_quality
                    ),
                    "stale": o.id in stale_refs and ref_path.exists(),
                })
            if bd_script.cover is not None:
                composed.append(_compose_entry(name, "cover", proj_dir, quality_idx, default_quality, stale_compose))
            for p in bd_script.pages:
                composed.append(_compose_entry(name, f"page_{p.page_number}", proj_dir, quality_idx, default_quality, stale_compose))
            if bd_script.back_cover is not None:
                composed.append(_compose_entry(name, "back", proj_dir, quality_idx, default_quality, stale_compose))
        character_photos: dict[str, str | None] = {}
        for cid, photo_path in service.list_character_photos(proj_dir).items():
            character_photos[cid] = _file_url(
                name,
                f"{service.CHARACTER_PHOTOS_DIRNAME}/{cid}.png",
                photo_path,
            )
        location_photos: dict[str, str | None] = {}
        for lid, photo_path in service.list_location_photos(proj_dir).items():
            location_photos[lid] = _file_url(
                name,
                f"{service.LOCATION_PHOTOS_DIRNAME}/{lid}.png",
                photo_path,
            )
        object_photos: dict[str, str | None] = {}
        for oid, photo_path in service.list_object_photos(proj_dir).items():
            object_photos[oid] = _file_url(
                name,
                f"{service.OBJECT_PHOTOS_DIRNAME}/{oid}.png",
                photo_path,
            )
        reference_images: dict[str, dict[str, str | None]] = {
            "characters": {},
            "locations": {},
            "objects": {},
        }
        for kind, items in service.list_reference_images(proj_dir).items():
            for ref_id, ref_path in items.items():
                reference_images[kind][ref_id] = _file_url(
                    name, f"references/{kind}/{ref_id}.png", ref_path
                )
        return {
            "name": name,
            "state": state,
            "config": cfg_dict,
            "script": script_dict,
            "references": refs,
            "composed": composed,
            "stale": stale_idx,
            "pdf_url": _file_url(name, f"{name}.pdf", proj_dir / f"{name}.pdf"),
            "default_quality": default_quality,
            "character_photos": character_photos,
            "location_photos": location_photos,
            "object_photos": object_photos,
            "reference_images": reference_images,
        }

    @app.post("/api/projects")
    def create_project(payload: dict = Body(...)) -> dict:
        try:
            cfg = BdGenInput.model_validate(payload)
        except Exception as e:
            raise HTTPException(400, f"Configuration invalide : {e}")
        if not cfg.project:
            raise HTTPException(400, "Le champ 'project' est obligatoire.")
        if service.project_exists(cfg.project, _output_root()):
            raise HTTPException(409, f"Un projet « {cfg.project} » existe déjà.")
        service.save_config(cfg, _output_root())
        return {"name": cfg.project}

    @app.put("/api/projects/{name}")
    def update_project(name: str, payload: dict = Body(...)) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            cfg = BdGenInput.model_validate(payload)
        except Exception as e:
            raise HTTPException(400, f"Configuration invalide : {e}")
        if cfg.project != name:
            raise HTTPException(
                400, "Le champ 'project' ne peut pas être renommé via cette route."
            )
        service.detect_and_mark_stale(name, cfg, _output_root())
        service.save_config(cfg, _output_root())
        return {"name": name}

    @app.delete("/api/projects/{name}")
    def delete_project(name: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(409, "Une génération est en cours sur ce projet.")
        service.delete_project(name, _output_root())
        return {"deleted": name}

    @app.post("/api/projects/{name}/duplicate")
    def duplicate_project(name: str, payload: dict = Body(default_factory=dict)) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        data = payload or {}
        new_id = data.get("new_project") or None
        include_refs = bool(data.get("include_references", False))
        include_photos = bool(data.get("include_photos", True))
        include_style_ref = bool(data.get("include_style_reference", True))
        try:
            created = service.duplicate_project(
                name,
                new_id,
                _output_root(),
                include_references=include_refs,
                include_photos=include_photos,
                include_style_reference=include_style_ref,
            )
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(400, f"Duplication impossible : {e}")
        return {"name": created}

    @app.post("/api/projects/{name}/restyle")
    def restyle_project(name: str, payload: dict = Body(...)) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        if app.state.jobs.is_running():
            current = app.state.jobs.current()
            if current and current.project == name:
                raise HTTPException(409, "Une génération est en cours sur ce projet.")
        style = (payload or {}).get("style")
        if not isinstance(style, dict):
            raise HTTPException(400, "Le champ 'style' est obligatoire.")
        try:
            deleted = service.restyle_project(name, style, _output_root())
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            raise HTTPException(400, f"Re-stylage impossible : {e}")
        return {"ok": True, "deleted": deleted}

    @app.get("/api/projects/{name}/feedback")
    def list_feedback(name: str) -> dict:
        from ..feedback import FeedbackStore, feedback_path_for
        proj_dir = service.get_project_dir(name, _output_root())
        store = FeedbackStore.load_or_empty(feedback_path_for(proj_dir / "bdgen-script.json"))
        return {"items": [item.model_dump(mode="json") for item in store.items]}

    @app.get("/api/projects/{name}/files/{path:path}")
    def serve_project_file(name: str, path: str):
        proj_dir = service.get_project_dir(name, _output_root())
        target = (proj_dir / path).resolve()
        # Path traversal guard
        try:
            target.relative_to(proj_dir.resolve())
        except ValueError:
            raise HTTPException(400, "Chemin invalide.")
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "Fichier introuvable.")
        return FileResponse(target)

    # --- Import / export ---

    @app.get("/api/projects/{name}/export")
    def export_project(name: str):
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = service.export_zip(name, _output_root())
        return Response(
            content=blob,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.bdgen"',
            },
        )

    @app.post("/api/projects/import")
    async def import_project(file: UploadFile = File(...)) -> dict:
        blob = await file.read()
        try:
            project_name = service.import_zip(blob, _output_root())
        except Exception as e:
            raise HTTPException(400, f"Archive invalide : {e}")
        return {"name": project_name}

    # --- References bundle (.bdrefs) — share a cast across projects ---

    @app.get("/api/projects/{name}/references/exportable")
    def list_exportable_refs(name: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            return service.list_exportable_references(name, _output_root())
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))

    @app.post("/api/projects/{name}/references/export")
    def export_refs_bundle(name: str, payload: dict = Body(default_factory=dict)) -> Response:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        try:
            blob = service.export_references_bundle(
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
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            return service.import_references_bundle(name, blob, _output_root())
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
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")

        def runner(reporter, interrupt):
            service.run_step_script(
                name, reporter, interrupt,
                output_root=_output_root(),
                preview_pages=payload.preview_pages,
            )

        return _start("script", name, runner)

    @app.post("/api/projects/{name}/steps/references/start")
    def start_references(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        _validate_quality(payload.quality_override)

        def runner(reporter, interrupt):
            service.run_step_references(
                name, reporter, interrupt,
                output_root=_output_root(),
                force_ids=payload.force_ids,
                quality_override=payload.quality_override,
            )

        return _start("references", name, runner)

    @app.post("/api/projects/{name}/steps/compose/start")
    def start_compose(name: str, payload: StartStepPayload = Body(default=StartStepPayload())) -> dict:
        _validate_quality(payload.quality_override)

        def runner(reporter, interrupt):
            service.run_step_compose(
                name, reporter, interrupt,
                output_root=_output_root(),
                force_ids=payload.force_ids,
                quality_override=payload.quality_override,
            )

        return _start("compose", name, runner)

    # --- Targeted refinement (synchronous) ---

    @app.post("/api/projects/{name}/refine/character/{character_id}")
    def refine_character(name: str, character_id: str, payload: FeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_character(
                name, character_id, payload.feedback, _output_root()
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/location/{location_id}")
    def refine_location(name: str, location_id: str, payload: FeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_location(
                name, location_id, payload.feedback, _output_root()
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/object/{object_id}")
    def refine_object(name: str, object_id: str, payload: FeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_object(
                name, object_id, payload.feedback, _output_root()
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/cover")
    def refine_cover(name: str, payload: FeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_cover(
                name, payload.feedback, _output_root()
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/back_cover")
    def refine_back_cover(name: str, payload: FeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_back_cover(
                name, payload.feedback, _output_root()
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/refine/page/{page_number}")
    def refine_page(name: str, page_number: int, payload: PageFeedbackPayload) -> dict:
        try:
            service.add_feedback_and_regenerate_page(
                name, page_number, payload.feedback,
                cascade=payload.cascade, output_root=_output_root(),
            )
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/projects/{name}/feedback/image")
    def add_image_feedback(name: str, payload: ImageFeedbackPayload) -> dict:
        if payload.step not in ("references", "compose"):
            raise HTTPException(400, "Étape invalide.")
        service.record_image_feedback(
            name, payload.step, payload.target, payload.feedback, _output_root()  # type: ignore[arg-type]
        )
        return {"ok": True}

    # --- Delete a character / location (cascades to script) ---

    @app.get("/api/projects/{name}/characters/{character_id}/delete-preview")
    def preview_delete_char(name: str, character_id: str) -> dict:
        try:
            return service.preview_delete_character(name, character_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{name}/locations/{location_id}/delete-preview")
    def preview_delete_loc(name: str, location_id: str) -> dict:
        try:
            return service.preview_delete_location(name, location_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/projects/{name}/objects/{object_id}/delete-preview")
    def preview_delete_obj(name: str, object_id: str) -> dict:
        try:
            return service.preview_delete_object(name, object_id, _output_root())
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.delete("/api/projects/{name}/characters/{character_id}")
    def delete_character(
        name: str,
        character_id: str,
        auto_regenerate: bool = True,
    ) -> dict:
        try:
            info = service.delete_character_and_cascade(
                name, character_id, _output_root()
            )
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
            info = service.delete_location_and_cascade(
                name, location_id, _output_root()
            )
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
            info = service.delete_object_and_cascade(
                name, object_id, _output_root()
            )
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
            service.run_step_script(
                name, reporter, interrupt, output_root=_output_root()
            )

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
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        p = service.save_style_reference(name, blob, _output_root())
        return {
            "ok": True,
            "path": str(p),
            "url": _file_url(name, service.STYLE_REF_NAME, p),
        }

    @app.get("/api/projects/{name}/style-reference")
    def get_style_reference_info(name: str) -> dict:
        proj_dir = service.get_project_dir(name, _output_root())
        ref = service.get_style_reference_path(proj_dir)
        return {
            "exists": ref is not None,
            "url": _file_url(name, service.STYLE_REF_NAME, ref) if ref else None,
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
    async def set_character_photo(
        name: str, character_id: str, file: UploadFile = File(...)
    ) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = service.save_character_photo(
                name, character_id, blob, _output_root()
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "ok": True,
            "url": _file_url(
                name,
                f"{service.CHARACTER_PHOTOS_DIRNAME}/{character_id}.png",
                p,
            ),
        }

    @app.delete("/api/projects/{name}/characters/{character_id}/photo")
    def remove_character_photo(name: str, character_id: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = service.delete_character_photo(
            name, character_id, _output_root()
        )
        return {"ok": True, "removed": removed}

    # --- Per-object reference photos ---

    @app.put("/api/projects/{name}/objects/{object_id}/photo")
    async def set_object_photo(
        name: str, object_id: str, file: UploadFile = File(...)
    ) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = service.save_object_photo(
                name, object_id, blob, _output_root()
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "ok": True,
            "url": _file_url(
                name,
                f"{service.OBJECT_PHOTOS_DIRNAME}/{object_id}.png",
                p,
            ),
        }

    @app.delete("/api/projects/{name}/objects/{object_id}/photo")
    def remove_object_photo(name: str, object_id: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = service.delete_object_photo(
            name, object_id, _output_root()
        )
        return {"ok": True, "removed": removed}

    # --- Per-location reference photos ---

    @app.put("/api/projects/{name}/locations/{location_id}/photo")
    async def set_location_photo(
        name: str, location_id: str, file: UploadFile = File(...)
    ) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        blob = await file.read()
        try:
            p = service.save_location_photo(
                name, location_id, blob, _output_root()
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {
            "ok": True,
            "url": _file_url(
                name,
                f"{service.LOCATION_PHOTOS_DIRNAME}/{location_id}.png",
                p,
            ),
        }

    @app.delete("/api/projects/{name}/locations/{location_id}/photo")
    def remove_location_photo(name: str, location_id: str) -> dict:
        if not service.project_exists(name, _output_root()):
            raise HTTPException(404, "Projet inconnu.")
        removed = service.delete_location_photo(
            name, location_id, _output_root()
        )
        return {"ok": True, "removed": removed}


def _validate_quality(q: str | None) -> None:
    if q is not None and q not in ("low", "medium", "high"):
        raise HTTPException(
            400, "quality_override doit valoir 'low', 'medium' ou 'high'."
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
    quality_idx: dict[str, dict[str, str]],
    default_quality: str,
    stale_set: set[str] | None = None,
) -> dict:
    """Build {id, image_url, quality, stale} for a composed page target."""
    rel = _target_relpath(target, "pages")
    if rel is None:
        return {"id": target, "image_url": None, "quality": None, "stale": False}
    full = proj_dir / rel
    exists = full.exists()
    return {
        "id": target,
        "image_url": _file_url(project, rel, full),
        "quality": _quality_for(
            quality_idx, "compose", target, full, default_quality
        ),
        "stale": bool(stale_set and target in stale_set and exists),
    }


def _quality_for(
    quality_idx: dict[str, dict[str, str]],
    step: str,
    target: str,
    file_path: Path | None,
    default_quality: str,
) -> str | None:
    """Look up the recorded quality for a target, or assume default if the
    file exists without a record (legacy generations). Returns None if the
    file doesn't exist yet.
    """
    if file_path is None or not file_path.exists():
        return None
    return quality_idx.get(step, {}).get(target, default_quality)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
