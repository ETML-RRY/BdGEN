"""Single-slot job manager: one generation step runs at a time, server-wide.

The ``JobManager`` runs the engine in a worker thread, bridges its progress
events to async subscribers (SSE), and exposes the live job status via a
threadsafe snapshot. Only one job is allowed at a time — concurrent start
attempts are rejected with HTTP 409 by the routes layer.
"""
from __future__ import annotations

import asyncio
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ..progress import (
    InterruptFlag,
    Interrupted,
    ProgressEvent,
    ProgressReporter,
    StdoutReporter,
)
from .error_messages import format_user_error

JobStep = Literal["script", "references", "compose", "upscale"]
JobStatus = Literal["running", "completed", "interrupted", "failed"]


@dataclass
class JobSnapshot:
    job_id: str
    project: str
    step: JobStep
    status: JobStatus
    started_at: float
    finished_at: float | None = None
    last_message: str = ""
    last_event: dict | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    error: str | None = None
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


class _BridgeReporter:
    """Reporter that fans events out to (a) the main loop's event bus and
    (b) a stdout reporter so server logs still show progress.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_event: Callable[[ProgressEvent], None],
    ) -> None:
        self._loop = loop
        self._on_event = on_event
        self._stdout = StdoutReporter()

    def emit(self, event: ProgressEvent) -> None:
        self._stdout.emit(event)
        self._loop.call_soon_threadsafe(self._on_event, event)


class _EventBus:
    """Async fan-out for progress events. New subscribers receive the recent
    history (so reloading the page doesn't lose context) plus all live events.
    """

    def __init__(self, history_size: int = 200) -> None:
        self._history: list[dict] = []
        self._history_size = history_size
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    def publish(self, payload: dict) -> None:
        with self._lock:
            self._history.append(payload)
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size:]
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def reset(self) -> None:
        with self._lock:
            self._history.clear()

    def subscribe(self) -> tuple[asyncio.Queue, list[dict]]:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        with self._lock:
            history = list(self._history)
            self._subscribers.add(q)
        return q, history

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)


class JobManager:
    """Single-slot job manager. Threadsafe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bdgen-job")
        self._current: JobSnapshot | None = None
        self._interrupt: InterruptFlag | None = None
        self._bus = _EventBus()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def bus(self) -> _EventBus:
        return self._bus

    def current(self) -> JobSnapshot | None:
        with self._lock:
            return None if self._current is None else JobSnapshot(**self._current.__dict__)

    def is_running(self) -> bool:
        with self._lock:
            return self._current is not None and self._current.status == "running"

    def start(
        self,
        project: str,
        step: JobStep,
        runner: Callable[[ProgressReporter, InterruptFlag], Any],
    ) -> JobSnapshot:
        """Start a job. Raises RuntimeError if one is already running."""
        if self._loop is None:
            raise RuntimeError("JobManager.attach_loop() doit être appelé au démarrage.")
        with self._lock:
            if self._current is not None and self._current.status == "running":
                raise RuntimeError("Une génération est déjà en cours.")
            job_id = uuid.uuid4().hex[:12]
            snap = JobSnapshot(
                job_id=job_id,
                project=project,
                step=step,
                status="running",
                started_at=time.time(),
            )
            self._current = snap
            self._interrupt = InterruptFlag()
            self._bus.reset()

        loop = self._loop

        def _on_event(ev: ProgressEvent) -> None:
            payload = {"type": "progress", **ev.to_dict()}
            with self._lock:
                if self._current is not None:
                    self._current.last_message = ev.message
                    self._current.last_event = ev.to_dict()
                    if ev.current is not None:
                        self._current.progress_current = ev.current
                    if ev.total is not None:
                        self._current.progress_total = ev.total
            self._bus.publish(payload)

        bridge = _BridgeReporter(loop, _on_event)

        def _worker() -> None:
            try:
                runner(bridge, self._interrupt)  # type: ignore[arg-type]
                terminal = {
                    "type": "terminal",
                    "status": "completed",
                    "message": "Étape terminée.",
                }
                with self._lock:
                    if self._current is not None:
                        self._current.status = "completed"
                        self._current.finished_at = time.time()
                        self._current.last_message = "Étape terminée."
            except Interrupted:
                terminal = {
                    "type": "terminal",
                    "status": "interrupted",
                    "message": "Génération interrompue par l'utilisateur.",
                }
                with self._lock:
                    if self._current is not None:
                        self._current.status = "interrupted"
                        self._current.finished_at = time.time()
                        self._current.last_message = "Génération interrompue."
            except Exception as e:
                err = format_user_error(e)
                tb = traceback.format_exc()
                print(tb)
                terminal = {
                    "type": "terminal",
                    "status": "failed",
                    "message": err,
                    "traceback": tb,
                }
                with self._lock:
                    if self._current is not None:
                        self._current.status = "failed"
                        self._current.finished_at = time.time()
                        self._current.error = err
                        self._current.last_message = err
            finally:
                # Publish the terminal marker via the loop so SSE clients see it.
                loop.call_soon_threadsafe(self._bus.publish, terminal)

        self._executor.submit(_worker)
        return snap

    def interrupt(self) -> bool:
        with self._lock:
            if self._current is None or self._current.status != "running":
                return False
            if self._interrupt is None:
                return False
            self._interrupt.set()
            return True

    def clear_finished(self) -> None:
        with self._lock:
            if self._current is not None and self._current.status != "running":
                self._current = None
                self._interrupt = None
