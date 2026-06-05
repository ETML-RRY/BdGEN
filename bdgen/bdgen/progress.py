"""Progress reporting and cooperative interruption for generation steps.

The generation engine is decoupled from any UI: it emits structured
``ProgressEvent`` objects through a ``ProgressReporter`` and checks an
``InterruptFlag`` between safe-to-stop boundaries (between pages, between
references, between panels, …). The CLI plugs in a stdout reporter and a flag
that is never set; the web server plugs in an SSE-bridging reporter and a flag
controllable from an HTTP endpoint.
"""
from __future__ import annotations

import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import Protocol


Step = str  # "script" | "references" | "compose" | "upscale"


def configure_stdio_utf8() -> None:
    """Force stdout/stderr to UTF-8 so progress messages crash-proof on Windows.

    Messages such as ``"4ᵉ de couverture"`` contain non-cp1252 characters (here
    the superscript ``ᵉ`` / ``\\u1d49``). On a Windows console defaulting to the
    cp1252 (``charmap``) codec, ``print()`` raises ``UnicodeEncodeError`` and
    aborts generation. Reconfiguring the streams to UTF-8 with ``errors=replace``
    makes every print path (progress events, the script spinner, …) safe.

    Idempotent and best-effort: silently skips streams that can't be
    reconfigured (e.g. already-wrapped or redirected streams).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


class Interrupted(Exception):
    """Raised by ``InterruptFlag.check()`` when the user has requested a stop."""


class InterruptFlag:
    """Cooperative interruption signal.

    Engine code calls ``check()`` at safe points (between pages, between
    references). When the flag is set, ``check()`` raises ``Interrupted``,
    which the caller is expected to let propagate. Anything written to disk
    before the interruption stays on disk so the next run can resume.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Interrupted()


@dataclass
class ProgressEvent:
    step: Step
    phase: str
    message: str
    current: int | None = None
    total: int | None = None
    artifact: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressReporter(Protocol):
    def emit(self, event: ProgressEvent) -> None: ...


class NullReporter:
    """Discards every event. Used as the default to keep call sites tidy."""

    def emit(self, event: ProgressEvent) -> None:  # noqa: D401
        return


class StdoutReporter:
    """Default CLI reporter: one line per event."""

    def emit(self, event: ProgressEvent) -> None:
        prefix = f"[{event.step}]"
        if event.current is not None and event.total is not None:
            prefix += f" {event.current}/{event.total}"
        print(f"{prefix} {event.message}")


class CompositeReporter:
    """Fan out a single event to several reporters (e.g. stdout + SSE)."""

    def __init__(self, *reporters: ProgressReporter) -> None:
        self._reporters = tuple(reporters)

    def emit(self, event: ProgressEvent) -> None:
        for r in self._reporters:
            r.emit(event)


def _coerce_reporter(reporter: ProgressReporter | None) -> ProgressReporter:
    return reporter if reporter is not None else NullReporter()


def _coerce_flag(flag: InterruptFlag | None) -> InterruptFlag:
    return flag if flag is not None else InterruptFlag()
