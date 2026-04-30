"""Per-project generation statistics and cost estimates."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATS_NAME = "bdgen-stats.json"


@dataclass
class TimedCall:
    started_at: str
    elapsed_seconds: float


def start_timer() -> tuple[str, float]:
    return datetime.now(timezone.utc).isoformat(), time.monotonic()


def stop_timer(started_at: str, started_monotonic: float) -> TimedCall:
    return TimedCall(
        started_at=started_at,
        elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
    )


def record_event(
    project_dir: Path | None,
    *,
    step: str,
    target_id: str,
    target_kind: str,
    operation: str,
    provider: str,
    model: str,
    timer: TimedCall,
    status: str = "success",
    usage: dict[str, Any] | None = None,
    prompt: str | None = None,
    input_images: int = 0,
    artifact: Path | str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if project_dir is None:
        return
    usage_payload = normalise_usage(usage)
    event = {
        "id": uuid.uuid4().hex,
        "started_at": timer.started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": timer.elapsed_seconds,
        "step": step,
        "target_id": target_id,
        "target_kind": target_kind,
        "operation": operation,
        "provider": provider,
        "model": model,
        "status": status,
        "usage": usage_payload,
        "prompt_chars": len(prompt or ""),
        "prompt_words": word_count(prompt or ""),
        "input_images": input_images,
        "artifact": str(artifact) if artifact is not None else None,
        "cost_usd": estimate_cost_usd(provider, model, usage_payload),
        "cost_is_estimate": True,
        "extra": extra or {},
    }
    path = project_dir / STATS_NAME
    payload = load_stats(project_dir)
    payload.setdefault("events", []).append(event)
    payload["version"] = 1
    payload["updated_at"] = event["ended_at"]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_stats(project_dir: Path) -> dict[str, Any]:
    path = project_dir / STATS_NAME
    if not path.exists():
        return {"version": 1, "updated_at": None, "events": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": None, "events": []}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": None, "events": []}
    data.setdefault("version", 1)
    data.setdefault("events", [])
    return data


def normalise_usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    elif not isinstance(usage, dict):
        usage = {
            key: getattr(usage, key)
            for key in dir(usage)
            if not key.startswith("_") and not callable(getattr(usage, key))
        }

    out: dict[str, int] = {}

    def pick(*names: str) -> int:
        for name in names:
            value = _dig(usage, name)
            if isinstance(value, int):
                return value
        return 0

    out["input_tokens"] = pick("input_tokens", "prompt_tokens")
    out["output_tokens"] = pick("output_tokens", "completion_tokens")
    out["total_tokens"] = pick("total_tokens")
    out["cached_input_tokens"] = pick(
        "cached_input_tokens",
        "prompt_tokens_details.cached_tokens",
        "input_tokens_details.cached_tokens",
        "cache_read_input_tokens",
    )
    out["cache_creation_input_tokens"] = pick("cache_creation_input_tokens")
    out["image_input_tokens"] = pick("image_input_tokens", "input_tokens_details.image_tokens")
    out["image_output_tokens"] = pick("image_output_tokens", "output_tokens_details.image_tokens")
    return {k: v for k, v in out.items() if v}


def _dig(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def estimate_cost_usd(provider: str, model: str, usage: dict[str, int]) -> float | None:
    if not usage:
        return None
    rates = _rates(provider, model)
    if rates is None:
        return None
    cached = usage.get("cached_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    image_input = usage.get("image_input_tokens", 0)
    image_output = usage.get("image_output_tokens", 0)
    input_tokens = max(0, usage.get("input_tokens", 0) - cached - cache_creation - image_input)
    output_tokens = max(0, usage.get("output_tokens", 0) - image_output)
    cost = (
        input_tokens * rates.get("input", 0)
        + cached * rates.get("cached_input", rates.get("input", 0))
        + cache_creation * rates.get("cache_creation", rates.get("input", 0))
        + output_tokens * rates.get("output", 0)
        + image_input * rates.get("image_input", rates.get("input", 0))
        + image_output * rates.get("image_output", rates.get("output", 0))
    ) / 1_000_000
    return round(cost, 6)


def _rates(provider: str, model: str) -> dict[str, float] | None:
    p = provider.lower()
    m = model.lower()
    if p == "openai":
        if "gpt-image-2" in m:
            return {"input": 5.0, "cached_input": 1.25, "image_input": 8.0, "image_output": 30.0, "output": 30.0}
        if "gpt-image-1" in m:
            return {"input": 5.0, "cached_input": 1.25, "output": 0.0}
        if "gpt-5.5" in m:
            return {"input": 5.0, "cached_input": 0.5, "output": 30.0}
        if "gpt-5.4-mini" in m:
            return {"input": 0.75, "cached_input": 0.075, "output": 4.5}
        if "gpt-5.4" in m:
            return {"input": 2.5, "cached_input": 0.25, "output": 15.0}
        if "gpt-5" in m:
            return {"input": 1.25, "cached_input": 0.125, "output": 10.0}
        if "gpt-4o-mini" in m:
            return {"input": 0.15, "cached_input": 0.075, "output": 0.6}
        if "gpt-4o" in m:
            return {"input": 2.5, "cached_input": 1.25, "output": 10.0}
    if p == "anthropic":
        if "opus" in m:
            return {"input": 15.0, "cache_creation": 18.75, "cached_input": 1.5, "output": 75.0}
        if "sonnet" in m:
            return {"input": 3.0, "cache_creation": 3.75, "cached_input": 0.3, "output": 15.0}
        if "haiku-3-5" in m or "haiku-3.5" in m:
            return {"input": 0.8, "cache_creation": 1.0, "cached_input": 0.08, "output": 4.0}
        if "haiku" in m:
            return {"input": 0.25, "cache_creation": 0.30, "cached_input": 0.03, "output": 1.25}
    return None


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def aggregate_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    total_cost = 0.0
    known_cost = False
    total_seconds = 0.0
    by_step: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for event in events:
        total_seconds += float(event.get("elapsed_seconds") or 0)
        cost = event.get("cost_usd")
        if isinstance(cost, (int, float)):
            known_cost = True
            total_cost += float(cost)
        step = event.get("step") or "unknown"
        model_key = f"{event.get('provider') or 'unknown'}/{event.get('model') or 'unknown'}"
        _add_bucket(by_step.setdefault(step, _bucket()), event)
        _add_bucket(by_model.setdefault(model_key, _bucket()), event)
    return {
        "event_count": len(events),
        "total_seconds": round(total_seconds, 3),
        "total_cost_usd": round(total_cost, 6) if known_cost else None,
        "by_step": by_step,
        "by_model": by_model,
    }


def _bucket() -> dict[str, Any]:
    return {
        "events": 0,
        "seconds": 0.0,
        "cost_usd": 0.0,
        "known_cost_events": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "image_input_tokens": 0,
        "image_output_tokens": 0,
    }


def _add_bucket(bucket: dict[str, Any], event: dict[str, Any]) -> None:
    bucket["events"] += 1
    bucket["seconds"] = round(bucket["seconds"] + float(event.get("elapsed_seconds") or 0), 3)
    cost = event.get("cost_usd")
    if isinstance(cost, (int, float)):
        bucket["cost_usd"] = round(bucket["cost_usd"] + float(cost), 6)
        bucket["known_cost_events"] += 1
    usage = event.get("usage") or {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_creation_input_tokens",
        "image_input_tokens",
        "image_output_tokens",
    ):
        bucket[key] += int(usage.get(key) or 0)
