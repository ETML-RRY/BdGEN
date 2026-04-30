"""User feedback storage for iterative refinement of generation outputs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Step = Literal["script", "references", "compose"]


class FeedbackItem(BaseModel):
    step: Step
    target: str | None = None
    timestamp: str
    feedback: str


class FeedbackStore(BaseModel):
    items: list[FeedbackItem] = Field(default_factory=list)

    @classmethod
    def load_or_empty(cls, path: Path) -> "FeedbackStore":
        if not path.exists():
            return cls()
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def add(self, step: Step, target: str | None, feedback: str) -> None:
        self.items.append(
            FeedbackItem(
                step=step,
                target=target,
                timestamp=datetime.now(timezone.utc).isoformat(),
                feedback=feedback,
            )
        )

    def get_for(self, step: Step, target: str | None = None) -> list[str]:
        """Return all feedback texts for a (step, target) pair, oldest first."""
        return [
            item.feedback
            for item in self.items
            if item.step == step and item.target == target
        ]


def feedback_path_for(script_path: Path) -> Path:
    """Default location of the feedback file: alongside the script."""
    return script_path.parent / "bdgen-feedback.json"


def feedback_block(feedback: list[str]) -> str:
    """Render a list of feedback entries as a prompt-appendable block."""
    items = "\n".join(f"- {f}" for f in feedback)
    return (
        "\n\nUSER FEEDBACK FROM PREVIOUS ITERATIONS"
        " (apply these refinements while keeping the rest consistent):\n"
        + items
    )
