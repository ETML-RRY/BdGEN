"""Helpers building canonical paths for composed and upscaled image targets."""

from __future__ import annotations

from pathlib import Path


def _composed_path(pages_dir: Path, target: str) -> Path | None:
    if target == "cover":
        return pages_dir / "cover.png"
    if target == "back":
        return pages_dir / "back.png"
    if target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except ValueError:
            return None
        return pages_dir / f"page_{n:02d}.png"
    return None


def _upscaled_path(output_dir: Path, target: str, suffix: str = ".png") -> Path | None:
    if target == "cover":
        return output_dir / f"cover{suffix}"
    if target == "back":
        return output_dir / f"back{suffix}"
    if target.startswith("page_"):
        try:
            n = int(target.split("_", 1)[1])
        except ValueError:
            return None
        return output_dir / f"page_{n:02d}{suffix}"
    return None
