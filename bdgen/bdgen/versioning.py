"""Per-file versioning for generated artefacts.

Whenever the pipeline is about to overwrite an existing artefact (a composed
page, a reference image, the script JSON, an inpainted region…), we archive
the previous content under ``<parent>/.versions/<filename>/`` first. Each
archive entry is a side-by-side pair of files:

- ``<ISO-timestamp>.<ext>`` — the bytes as they were before being overwritten
- ``<ISO-timestamp>.meta.json`` — a small sidecar with ``{kind, sha256,
  bytes, archived_at}`` so the UI can label each version (regen / inpaint /
  refine / manual / pre-restore).

The module is intentionally light: no compaction, no GC, no version IDs
embedded in the artefact itself. Callers wrap each write with::

    archive_before_write(target, kind="regen")
    # … now write the new content to target …

and the UI walks the ``.versions/`` directory to display the history.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSIONS_DIR_NAME = ".versions"
META_SUFFIX = ".meta.json"
DEFAULT_KIND = "regen"


_PROJECT_MARKERS = ("bdgen.json", "bdgen-script.json")


def _project_root(target: Path) -> Path | None:
    """Walk up from *target* until a directory containing a project marker
    file (bdgen.json or bdgen-script.json) is found, or None."""
    for parent in [target.parent, *target.parent.parents]:
        for marker in _PROJECT_MARKERS:
            if (parent / marker).exists():
                return parent
    return None


def _versions_dir(target: Path) -> Path:
    """Return the directory where versions of *target* are stored.

    When *target* lives inside a recognisable project (detected by walking
    up until a ``bdgen.json``/``bdgen-script.json`` marker), versions are
    centralised under ``<project_root>/.versions/<relpath>/``. This keeps
    the history alive when an entire subdirectory (e.g. ``pages/``) is
    wiped — typical of restyle workflows that rmtree the downstream
    artefacts and regenerate everything.

    Falls back to the legacy ``<parent>/.versions/<filename>/`` layout when
    no project root is found, so the module remains usable in isolation.
    """
    proj = _project_root(target)
    if proj is None:
        return target.parent / VERSIONS_DIR_NAME / target.name
    try:
        rel = target.relative_to(proj)
    except ValueError:
        return target.parent / VERSIONS_DIR_NAME / target.name
    return proj / VERSIONS_DIR_NAME / rel


def archived_path(target: Path, filename: str) -> Path:
    """Public accessor: full path to an archived file for *target*.

    The caller passes the ``filename`` value returned by ``list_versions``;
    this is the only place that knows where ``_versions_dir`` puts archives.
    """
    return _versions_dir(Path(target)) / filename


def _now_id() -> str:
    """Filesystem-safe ISO timestamp with millisecond precision."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except Exception:
        return None


def _latest_version_sha(target: Path) -> str | None:
    """Return the sha256 stored on the most recent archived version, or None."""
    versions = list_versions(target)
    if not versions:
        return None
    return versions[0].get("sha256")


def archive_before_write(
    target: Path,
    kind: str = DEFAULT_KIND,
    extra: dict[str, Any] | None = None,
    *,
    dedup: bool = False,
) -> Path | None:
    """Snapshot *target* under ``<parent>/.versions/<filename>/`` if it exists.

    Returns the archived file path, or None when nothing was archived
    (target absent, dedup hit, or an unexpected I/O error). Callers should
    invoke this immediately before replacing the file with new content.

    - ``kind``: free-form label persisted in the sidecar (``regen`` /
      ``inpaint`` / ``refine`` / ``manual`` / ``pre-restore``…).
    - ``extra``: arbitrary key/value pairs merged into the sidecar
      (e.g. job_id, session_id, prompt sha).
    - ``dedup``: when True, the archive is skipped if the file's sha256
      matches the most recent archived version. Useful for the script JSON,
      which is saved repeatedly without necessarily changing.
    """
    try:
        target = Path(target)
    except Exception:
        return None
    if not target.exists() or not target.is_file():
        return None

    try:
        data = target.read_bytes()
    except Exception:
        return None
    sha = _sha256_bytes(data)
    if dedup and sha == _latest_version_sha(target):
        return None

    vdir = _versions_dir(target)
    try:
        vdir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    version_id = _now_id()
    ext = target.suffix or ""
    archived = vdir / f"{version_id}{ext}"
    meta_path = vdir / f"{version_id}{META_SUFFIX}"

    try:
        shutil.copy2(target, archived)
    except Exception:
        return None

    meta: dict[str, Any] = {
        "version_id": version_id,
        "kind": kind,
        "sha256": sha,
        "bytes": len(data),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "original_name": target.name,
    }
    if extra:
        meta["extra"] = extra
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # The archive exists even if the sidecar failed; that's OK — the
        # listing code tolerates missing sidecars.
        pass
    return archived


_VERSION_FILE_RE = re.compile(r"^(?P<id>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)\.(?P<ext>.+)$")


def list_versions(target: Path) -> list[dict[str, Any]]:
    """Return all archived versions of *target* (newest first).

    Each entry includes the metadata from the sidecar plus a ``relpath``
    relative to the project root so the UI can request the binary via the
    existing /api/projects/{name}/files/{path:path} endpoint.
    """
    target = Path(target)
    vdir = _versions_dir(target)
    if not vdir.exists() or not vdir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for entry in vdir.iterdir():
        if entry.suffix == ".json" and entry.name.endswith(META_SUFFIX):
            continue
        if not entry.is_file():
            continue
        m = _VERSION_FILE_RE.match(entry.name)
        if not m:
            continue
        version_id = m.group("id")
        meta_path = vdir / f"{version_id}{META_SUFFIX}"
        meta: dict[str, Any] = {
            "version_id": version_id,
            "kind": DEFAULT_KIND,
            "archived_at": None,
            "sha256": None,
            "bytes": entry.stat().st_size,
        }
        if meta_path.exists():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        meta["filename"] = entry.name
        entries.append(meta)
    entries.sort(key=lambda e: e["version_id"], reverse=True)
    return entries


def current_info(target: Path) -> dict[str, Any] | None:
    """Lightweight descriptor of the live file at *target* (or None)."""
    target = Path(target)
    if not target.exists() or not target.is_file():
        return None
    try:
        data = target.read_bytes()
    except Exception:
        return None
    return {
        "filename": target.name,
        "bytes": len(data),
        "sha256": _sha256_bytes(data),
        "modified_at": datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
    }


def restore_version(target: Path, version_id: str) -> dict[str, Any]:
    """Restore an archived version as the current file at *target*.

    Workflow:
    1. Archive whatever is currently at *target* (kind="pre-restore") so the
       restore is lossless — the about-to-be-replaced state stays in history.
    2. Copy the archived bytes over *target*.

    Raises FileNotFoundError if the version isn't archived, ValueError if the
    target path is invalid.
    """
    target = Path(target)
    if not target.parent.exists():
        raise ValueError(f"Parent directory missing for {target}.")
    vdir = _versions_dir(target)
    candidates = list(vdir.glob(f"{version_id}.*")) if vdir.exists() else []
    candidates = [c for c in candidates if not c.name.endswith(META_SUFFIX)]
    if not candidates:
        raise FileNotFoundError(f"Version {version_id} not archived for {target.name}.")
    archived = candidates[0]

    archive_before_write(target, kind="pre-restore", extra={"restored_from": version_id})
    shutil.copy2(archived, target)
    return {
        "restored_version_id": version_id,
        "target": str(target),
    }
