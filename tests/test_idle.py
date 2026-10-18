"""Tests for idle-time compression and speed scaling."""

import pytest

from flicker.cast import Event
from flicker.idle import apply_timing, compress_idle, scale_time


def evs(*times: float) -> list[Event]:
    return [Event(t, "o", str(i)) for i, t in enumerate(times)]


def times(events: list[Event]) -> list[float]:
    return [round(e.time, 6) for e in events]


def test_long_gap_is_shortened_to_max_idle() -> None:
    out = compress_idle(evs(0.0, 0.2, 10.2), 1.0)
    assert times(out) == [0.0, 0.2, 1.2]


def test_short_gaps_are_untouched() -> None:
    assert times(compress_idle(evs(0.1, 0.5, 0.9), 1.0)) == [0.1, 0.5, 0.9]


def test_savings_accumulate_across_several_gaps() -> None:
    out = compress_idle(evs(0.0, 5.0, 6.0, 20.0), 2.0)
    assert times(out) == [0.0, 2.0, 3.0, 5.0]


def test_leading_pause_is_compressed_too() -> None:
    assert times(compress_idle(evs(30.0, 30.5), 1.5)) == [1.5, 2.0]


def test_zero_max_idle_collapses_all_pauses() -> None:
    assert times(compress_idle(evs(1.0, 2.0, 3.0), 0.0)) == [0.0, 0.0, 0.0]


def test_content_and_order_are_preserved() -> None:
    src = evs(0.0, 9.0, 12.0)
    out = compress_idle(src, 1.0)
    assert [(e.kind, e.data) for e in out] == [(e.kind, e.data) for e in src]


def test_input_list_is_not_modified() -> None:
    src = evs(0.0, 9.0)
    compress_idle(src, 1.0)
    assert times(src) == [0.0, 9.0]


def test_empty_input() -> None:
    assert compress_idle([], 1.0) == []
    assert scale_time([], 2.0) == []


def test_negative_max_idle_rejected() -> None:
    with pytest.raises(ValueError):
        compress_idle(evs(1.0), -0.1)


def test_scale_time_halves_timestamps() -> None:
    assert times(scale_time(evs(0.0, 2.0, 4.0), 2.0)) == [0.0, 1.0, 2.0]


@pytest.mark.parametrize("speed", [0, -1.0])
def test_scale_time_rejects_nonpositive_speed(speed: float) -> None:
    with pytest.raises(ValueError):
        scale_time(evs(1.0), speed)


def test_apply_timing_compresses_before_scaling() -> None:
    out = apply_timing(evs(0.0, 10.0), max_idle=2.0, speed=2.0)
    assert times(out) == [0.0, 1.0]


def test_apply_timing_defaults_are_identity() -> None:
    assert times(apply_timing(evs(0.0, 3.0))) == [0.0, 3.0]
