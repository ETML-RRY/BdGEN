"""Shared constants for the project-oriented service package."""

from __future__ import annotations

from typing import Literal

from .. import stats as stats_module

Step = Literal["preparation", "script", "references", "compose", "done"]
Quality = Literal["low", "medium", "high"]

PROJECT_CONFIG_NAME = "bdgen.json"
QUALITY_INDEX_NAME = "bdgen-quality.json"
STALE_INDEX_NAME = "bdgen-stale.json"
COHERENCE_INDEX_NAME = "bdgen-coherence.json"
STATS_NAME = stats_module.STATS_NAME
STYLE_REF_NAME = "bdgen-style-ref.png"
UPSCALED_DIRNAME = "pages_upscaled"
CHARACTER_PHOTOS_DIRNAME = "character_photos"
LOCATION_PHOTOS_DIRNAME = "location_photos"
OBJECT_PHOTOS_DIRNAME = "object_photos"
CHARACTER_PHOTO_MAX_SIDE = 1024
LOCATION_PHOTO_MAX_SIDE = 1024
OBJECT_PHOTO_MAX_SIDE = 1024
STALE_STEPS = ("references", "compose")
THUMBNAIL_NAME = "thumbnail.jpg"
THUMB_MAX_W = 256
THUMB_MAX_H = 384
DEFAULT_IMAGE_PROVIDER = "openai"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
