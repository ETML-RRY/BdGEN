"""Per-project JSON indexes: quality, stale, coherence."""

from __future__ import annotations

import json
from pathlib import Path

from .constants import (
    COHERENCE_INDEX_NAME,
    STALE_INDEX_NAME,
    STALE_STEPS,
)


# --- Coherence index ---


def _coherence_index_path(proj_dir: Path) -> Path:
    return proj_dir / COHERENCE_INDEX_NAME


def _empty_coherence_index(dirty: bool = False) -> dict:
    return {
        "dirty": dirty,
        "checked_at": None,
        "issues": [],
        "suggestions": [],
        "flagged_pages": [],
    }


def read_coherence_index(proj_dir: Path) -> dict:
    p = _coherence_index_path(proj_dir)
    if not p.exists():
        return _empty_coherence_index()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _empty_coherence_index(True)
    if not isinstance(data, dict):
        return _empty_coherence_index(True)
    base = _empty_coherence_index()
    base.update(data)
    base["dirty"] = bool(base.get("dirty"))
    base["issues"] = list(base.get("issues") or [])
    base["suggestions"] = list(base.get("suggestions") or [])
    base["flagged_pages"] = sorted({int(p) for p in base.get("flagged_pages") or [] if isinstance(p, (int, float))})
    return base


def write_coherence_index(proj_dir: Path, idx: dict) -> None:
    p = _coherence_index_path(proj_dir)
    p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_script_coherence_dirty(proj_dir: Path) -> None:
    idx = read_coherence_index(proj_dir)
    idx["dirty"] = True
    write_coherence_index(proj_dir, idx)


# --- Staleness index (per-target "text modified after image was generated") ---


def _stale_index_path(proj_dir: Path) -> Path:
    return proj_dir / STALE_INDEX_NAME


def read_stale_index(proj_dir: Path) -> dict[str, list[str]]:
    """Return {step: [target_id, ...]} for references / compose.

    A target appears here when its underlying script text was rewritten after
    the image was generated, so the on-disk PNG no longer matches.
    """
    p = _stale_index_path(proj_dir)
    base: dict[str, list[str]] = {s: [] for s in STALE_STEPS}
    if not p.exists():
        return base
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return base
        for s in STALE_STEPS:
            v = data.get(s)
            if isinstance(v, list):
                # de-dup, preserve order
                seen: set[str] = set()
                out: list[str] = []
                for tid in v:
                    if isinstance(tid, str) and tid not in seen:
                        seen.add(tid)
                        out.append(tid)
                base[s] = out
        return base
    except Exception:
        return base


def write_stale_index(proj_dir: Path, idx: dict[str, list[str]]) -> None:
    p = _stale_index_path(proj_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Drop empty buckets to keep the file tidy.
    cleaned = {k: v for k, v in idx.items() if v}
    if not cleaned:
        if p.exists():
            p.unlink()
        return
    p.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_stale(proj_dir: Path, step: str, target_ids: str | list[str]) -> None:
    """Flag one or more targets as obsolete for a given image step."""
    if step not in STALE_STEPS:
        return
    ids = [target_ids] if isinstance(target_ids, str) else list(target_ids)
    if not ids:
        return
    idx = read_stale_index(proj_dir)
    bucket = idx.setdefault(step, [])
    seen = set(bucket)
    for tid in ids:
        if tid and tid not in seen:
            bucket.append(tid)
            seen.add(tid)
    write_stale_index(proj_dir, idx)


def clear_stale(proj_dir: Path, step: str, target_ids: str | list[str]) -> None:
    if step not in STALE_STEPS:
        return
    ids = {target_ids} if isinstance(target_ids, str) else set(target_ids)
    if not ids:
        return
    idx = read_stale_index(proj_dir)
    bucket = idx.get(step, [])
    new_bucket = [tid for tid in bucket if tid not in ids]
    if len(new_bucket) != len(bucket):
        idx[step] = new_bucket
        write_stale_index(proj_dir, idx)
