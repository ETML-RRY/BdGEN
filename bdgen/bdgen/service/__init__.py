"""Project-oriented service package.

Boundary between the generation engine (script.py, references.py, compose.py)
and any user interface. The engine modules know nothing about projects-on-disk,
zip files, or HTTP; the service package handles all of that and dispatches to
the engine with the right reporter/interrupt/feedback wiring.

Functions are grouped by concern in dedicated submodules:

- ``constants``: file/dir names, step enums, default models.
- ``config``: load/save ``bdgen.json``, load script if present.
- ``lifecycle``: project discovery, create/delete/duplicate/restyle.
- ``state``: derive_state, project_statistics, summaries, thumbnails.
- ``indices``: quality / stale / coherence indexes.
- ``style_refs``: style-reference PNG and reference-image attachment.
- ``photos``: per-entity photo CRUD (factored).
- ``stale_detection``: detect_and_mark_stale.
- ``coherence``: LLM-driven script coherence checks.
- ``pipeline``: run_step_{script,references,compose,upscale}.
- ``feedback_ops``: targeted regeneration via feedback.
- ``cascades``: deletions that drop downstream pages.
- ``manual_edits``: manual script edits.
- ``import_export``: ``.bdgen`` and ``.bdrefs`` archives.
- ``inpaint``: masked image edits and image feedback.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import Quality, Step

__all__ = ["ProjectSummary", "Step", "Quality"]


@dataclass
class ProjectSummary:
    """Light-weight project description for listings."""

    name: str
    display_name: str | None
    title: str | None
    author: str | None
    state: Step
    page_count: int | None
    pages_written: int
    references_ready: int
    references_total: int
    pages_composed: int
    pdf_ready: bool
    updated_at: str
    thumbnail_rel: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()
