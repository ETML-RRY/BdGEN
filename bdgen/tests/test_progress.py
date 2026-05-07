from __future__ import annotations

import pytest

from bdgen.progress import (
    CompositeReporter,
    InterruptFlag,
    Interrupted,
    NullReporter,
    ProgressEvent,
    StdoutReporter,
    _coerce_flag,
    _coerce_reporter,
)


def test_interrupt_flag_starts_unset() -> None:
    flag = InterruptFlag()

    assert flag.is_set() is False
    flag.check()  # does not raise


def test_interrupt_flag_set_then_check_raises() -> None:
    flag = InterruptFlag()
    flag.set()

    assert flag.is_set() is True
    with pytest.raises(Interrupted):
        flag.check()


def test_progress_event_to_dict_preserves_fields() -> None:
    event = ProgressEvent(
        step="references",
        phase="character",
        message="generating hero",
        current=2,
        total=5,
        artifact="hero.png",
        extra={"provider": "openai"},
    )

    payload = event.to_dict()

    assert payload == {
        "step": "references",
        "phase": "character",
        "message": "generating hero",
        "current": 2,
        "total": 5,
        "artifact": "hero.png",
        "extra": {"provider": "openai"},
    }


def test_progress_event_defaults() -> None:
    event = ProgressEvent(step="script", phase="setup", message="hi")

    assert event.current is None
    assert event.total is None
    assert event.artifact is None
    assert event.extra == {}


def test_null_reporter_is_silent() -> None:
    NullReporter().emit(ProgressEvent(step="x", phase="y", message="z"))


def test_stdout_reporter_prints_prefix_and_progress(capsys: pytest.CaptureFixture[str]) -> None:
    StdoutReporter().emit(
        ProgressEvent(step="references", phase="char", message="hero", current=1, total=3)
    )

    captured = capsys.readouterr().out
    assert "[references] 1/3 hero" in captured


def test_stdout_reporter_omits_count_when_missing(capsys: pytest.CaptureFixture[str]) -> None:
    StdoutReporter().emit(ProgressEvent(step="script", phase="setup", message="ready"))

    captured = capsys.readouterr().out
    assert "[script] ready" in captured
    assert "/" not in captured


def test_composite_reporter_fans_out_to_each_reporter() -> None:
    received_a: list[str] = []
    received_b: list[str] = []

    class CaptureReporter:
        def __init__(self, sink: list[str]) -> None:
            self._sink = sink

        def emit(self, event: ProgressEvent) -> None:
            self._sink.append(event.message)

    reporter = CompositeReporter(CaptureReporter(received_a), CaptureReporter(received_b))
    reporter.emit(ProgressEvent(step="s", phase="p", message="hello"))

    assert received_a == ["hello"]
    assert received_b == ["hello"]


def test_coerce_reporter_falls_back_to_null() -> None:
    assert isinstance(_coerce_reporter(None), NullReporter)

    explicit = StdoutReporter()
    assert _coerce_reporter(explicit) is explicit


def test_coerce_flag_falls_back_to_fresh_flag() -> None:
    coerced = _coerce_flag(None)

    assert isinstance(coerced, InterruptFlag)
    assert coerced.is_set() is False

    explicit = InterruptFlag()
    assert _coerce_flag(explicit) is explicit
