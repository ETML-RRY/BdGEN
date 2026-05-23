"""Developer-only execution trace for the BdGEN pipeline.

The pipeline is a chain of prompt-building + LLM/image calls; when scenarios
or pages drift between runs it is hard to tell *which* prompt actually fed
*which* call. This module captures the data flow as a JSONL timeline so a
developer can replay the run after the fact (and, later, render it as a graph
in the web UI).

Activation: set ``BDGEN_DEBUG=1``. When unset, every entry point in this
module returns immediately — there is no overhead in production.

Output: ``<project_dir>/.bdgen-trace/timeline.jsonl`` — one node per line,
grouped by ``session_id`` (one session per process-lifetime per project).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

TRACE_DIR_NAME = ".bdgen-trace"
TIMELINE_NAME = "timeline.jsonl"

_UNSET: Any = object()

_session_ids: dict[str, str] = {}
_file_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

_current_project_dir: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "bdgen_trace_project_dir", default=None
)
_current_parent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bdgen_trace_parent_id", default=None
)


def enabled() -> bool:
    return os.environ.get("BDGEN_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def _resolved_project_dir(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    return _current_project_dir.get()


def _session_id_for(project_dir: Path) -> str:
    key = str(project_dir)
    sid = _session_ids.get(key)
    if sid is None:
        sid = uuid.uuid4().hex[:12]
        _session_ids[key] = sid
    return sid


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _locks_lock:
        lock = _file_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _file_locks[key] = lock
        return lock


@contextmanager
def project_session(project_dir: Path | None) -> Iterator[None]:
    """Bind a project_dir for all trace calls inside the block.

    Top-level callers (CLI command, HTTP endpoint) wrap their work in this so
    deep call sites don't need to forward project_dir explicitly.
    """
    if project_dir is None or not enabled():
        yield
        return
    token = _current_project_dir.set(project_dir)
    try:
        yield
    finally:
        _current_project_dir.reset(token)


def push_project_dir(project_dir: Path | None) -> Any:
    """Bind a project_dir without using a ``with`` block.

    Returns an opaque token (or None when tracing is disabled). Use this when
    re-indenting a long function body would be too invasive — pair with
    ``pop_project_dir(token)`` in a try/finally.
    """
    if project_dir is None or not enabled():
        return None
    return _current_project_dir.set(project_dir)


def pop_project_dir(token: Any) -> None:
    if token is None:
        return
    try:
        _current_project_dir.reset(token)
    except Exception:
        pass


def _path_ref(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(path)}
    try:
        if path.is_file():
            data = path.read_bytes()
            info["bytes"] = len(data)
            info["sha256_12"] = hashlib.sha256(data).hexdigest()[:12]
        else:
            info["exists"] = path.exists()
    except Exception:
        pass
    return info


def _safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return _path_ref(value)
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            pass
    return f"<{type(value).__name__}>"


def record_node(
    *,
    name: str,
    kind: str,
    project_dir: Path | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    prompt: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    usage: dict[str, Any] | None = None,
    started_at: str | None = None,
    elapsed_seconds: float | None = None,
    status: str = "success",
    error: str | None = None,
    extra: dict[str, Any] | None = None,
    node_id: str | None = None,
    parent_id: Any = _UNSET,
) -> str | None:
    """Append one node entry to the project's timeline JSONL.

    Returns the node id, or None when tracing is disabled / no project bound.
    """
    if not enabled():
        return None
    pd = _resolved_project_dir(project_dir)
    if pd is None:
        return None
    nid = node_id or uuid.uuid4().hex[:12]
    pid = parent_id if parent_id is not _UNSET else _current_parent_id.get()
    now = datetime.now(timezone.utc).isoformat()
    entry: dict[str, Any] = {
        "session_id": _session_id_for(pd),
        "node_id": nid,
        "parent_id": pid,
        "name": name,
        "kind": kind,
        "ts": now,
        "started_at": started_at or now,
        "elapsed_seconds": elapsed_seconds,
        "status": status,
        "provider": provider,
        "model": model,
        "prompt": prompt,
        "inputs": _safe_json(inputs or {}),
        "outputs": _safe_json(outputs or {}),
        "usage": usage or {},
        "error": error,
        "extra": extra or {},
    }
    trace_dir = pd / TRACE_DIR_NAME
    target = trace_dir / TIMELINE_NAME
    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        with _lock_for(target):
            with target.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return nid


@dataclass
class NodeRecorder:
    """Mutable handle yielded by ``node()`` so the block can attach data."""

    name: str
    kind: str
    node_id: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    prompt: str | None = None
    model: str | None = None
    provider: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def set_output(self, key: str, value: Any) -> None:
        self.outputs[key] = value

    def set_outputs(self, mapping: dict[str, Any]) -> None:
        self.outputs.update(mapping)

    def set_usage(self, usage: dict[str, Any]) -> None:
        if usage:
            self.usage = dict(usage)

    def set_prompt(self, prompt: str) -> None:
        self.prompt = prompt

    def set_model(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    def set_extra(self, **kwargs: Any) -> None:
        self.extra.update(kwargs)


@contextmanager
def node(
    name: str,
    kind: str,
    *,
    project_dir: Path | None = None,
    inputs: dict[str, Any] | None = None,
) -> Iterator[NodeRecorder]:
    """Auto-timed node context manager.

    Inside the block, the yielded ``NodeRecorder`` can be enriched with
    prompt/outputs/usage. The node is committed to the timeline on exit
    (or on exception, with status="error").
    """
    recorder = NodeRecorder(name=name, kind=kind)
    pd = _resolved_project_dir(project_dir)
    if not enabled() or pd is None:
        yield recorder
        return
    nid = uuid.uuid4().hex[:12]
    recorder.node_id = nid
    parent_id_before = _current_parent_id.get()
    started_at = datetime.now(timezone.utc).isoformat()
    started_monotonic = time.monotonic()
    parent_token = _current_parent_id.set(nid)
    try:
        try:
            yield recorder
        except BaseException as exc:
            record_node(
                name=name, kind=kind, project_dir=pd,
                inputs=inputs, outputs=recorder.outputs,
                prompt=recorder.prompt, model=recorder.model, provider=recorder.provider,
                usage=recorder.usage,
                started_at=started_at,
                elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                extra=recorder.extra,
                node_id=nid,
                parent_id=parent_id_before,
            )
            raise
        record_node(
            name=name, kind=kind, project_dir=pd,
            inputs=inputs, outputs=recorder.outputs,
            prompt=recorder.prompt, model=recorder.model, provider=recorder.provider,
            usage=recorder.usage,
            started_at=started_at,
            elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
            status="success",
            extra=recorder.extra,
            node_id=nid,
            parent_id=parent_id_before,
        )
    finally:
        _current_parent_id.reset(parent_token)


def read_timeline(project_dir: Path) -> list[dict[str, Any]]:
    """Read all timeline entries for a project (every session, in file order)."""
    path = project_dir / TRACE_DIR_NAME / TIMELINE_NAME
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


def list_sessions(project_dir: Path) -> list[dict[str, Any]]:
    """Aggregate the timeline into a per-session summary."""
    by_sid: dict[str, dict[str, Any]] = {}
    for entry in read_timeline(project_dir):
        sid = entry.get("session_id")
        if not sid:
            continue
        bucket = by_sid.setdefault(sid, {
            "session_id": sid,
            "started_at": entry.get("ts"),
            "ended_at": entry.get("ts"),
            "node_count": 0,
            "kinds": {},
        })
        bucket["node_count"] += 1
        ts = entry.get("ts")
        if ts:
            if ts < bucket["started_at"]:
                bucket["started_at"] = ts
            if ts > bucket["ended_at"]:
                bucket["ended_at"] = ts
        k = entry.get("kind") or "unknown"
        bucket["kinds"][k] = bucket["kinds"].get(k, 0) + 1
    return sorted(by_sid.values(), key=lambda s: s["started_at"], reverse=True)


def session_nodes(project_dir: Path, session_id: str) -> list[dict[str, Any]]:
    """Return all nodes belonging to a given session, in chronological order."""
    nodes = [e for e in read_timeline(project_dir) if e.get("session_id") == session_id]
    nodes.sort(key=lambda e: (e.get("started_at") or "", e.get("ts") or ""))
    return nodes
