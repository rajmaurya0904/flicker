"""Tests for the event-to-frame clock."""

import pytest

from flicker.cast import Event
from flicker.fonts import load_fonts
from flicker.render import Renderer
from flicker.theme import get_theme
from flicker.timeline import MAX_SECONDS, frame_count, frames, output_events

from .conftest import requires_font


def ev(t: float, data: str, kind: str = "o") -> Event:
    return Event(t, kind, data)


def test_frame_count_covers_last_event_plus_hold() -> None:
    assert frame_count([ev(2.0, "x")], fps=10, hold=1.0) == 31
    assert frame_count([], fps=10, hold=0.0) == 1
    assert frame_count([], fps=10, hold=1.0) == 11


def test_frame_count_rounds_up_so_the_last_event_is_shown() -> None:
    # An event at 1.01 s needs a tick at or after 1.01 s: tick 11 (1.1 s) at 10 fps.
    assert frame_count([ev(1.01, "x")], fps=10, hold=0.0) == 12


@pytest.mark.parametrize("fps, hold", [(0, 1.0), (10, -1.0)])
def test_frame_count_rejects_bad_arguments(fps: int, hold: float) -> None:
    with pytest.raises(ValueError):
        frame_count([], fps, hold)


def test_output_events_drops_resizes() -> None:
    kept = output_events([ev(0, "a"), ev(1, "80x24", "r"), ev(2, "b")])
    assert [e.data for e in kept] == ["a", "b"]


@pytest.fixture
def renderer():
    return Renderer(10, 3, load_fonts(size=12), get_theme("dark"), padding=4, show_cursor=False)


@requires_font
def test_yields_the_expected_number_of_frames(renderer) -> None:
    out = list(frames([ev(0.5, "hi")], renderer, fps=10, hold=0.5))
    assert len(out) == frame_count([ev(0.5, "hi")], 10, 0.5)
    assert all(len(f) == renderer.width * renderer.height * 3 for f in out)


@requires_font
def test_frame_changes_exactly_when_output_arrives(renderer) -> None:
    out = list(frames([ev(0.3, "X")], renderer, fps=10, hold=0.3))
    # ticks are 0.0, 0.1, 0.2, 0.3, ... ; X arrives on tick 3
    assert out[0] == out[1] == out[2]
    assert out[3] != out[2]
    assert out[3] == out[4] == out[5]


@requires_font
def test_unchanged_ticks_reuse_the_same_buffer(renderer) -> None:
    out = list(frames([ev(0.0, "X")], renderer, fps=10, hold=0.5))
    assert out[2] is out[3]


@requires_font
def test_event_between_ticks_shows_on_the_next_tick(renderer) -> None:
    out = list(frames([ev(0.25, "X")], renderer, fps=10, hold=0.2))
    assert out[2] == out[0]  # tick at 0.2 s: not yet
    assert out[3] != out[0]  # tick at 0.3 s: drawn


@requires_font
def test_events_in_one_tick_are_applied_together(renderer) -> None:
    together = list(frames([ev(0.21, "A"), ev(0.29, "B")], renderer, fps=10, hold=0.2))
    single = list(frames([ev(0.21, "AB")], renderer, fps=10, hold=0.2))
    assert together == single


@requires_font
def test_hold_repeats_the_final_screen(renderer) -> None:
    out = list(frames([ev(0.3, "end")], renderer, fps=10, hold=1.0))
    assert len(out) == 14
    assert out[0] != out[3]
    assert all(f == out[3] for f in out[3:])


@requires_font
def test_resize_events_do_not_change_the_frame_size(renderer) -> None:
    out = list(frames([ev(0.0, "a"), ev(0.1, "40x10", "r")], renderer, fps=10, hold=0.2))
    assert all(len(f) == renderer.width * renderer.height * 3 for f in out)


@requires_font
def test_progress_callback_reports_every_frame(renderer) -> None:
    calls: list[tuple[int, int]] = []
    out = list(frames([], renderer, fps=5, hold=1.0, on_progress=lambda d, t: calls.append((d, t))))
    assert calls[-1] == (len(out), len(out))
    assert [c[0] for c in calls] == list(range(1, len(out) + 1))


@requires_font
def test_absurdly_long_recordings_are_refused(renderer) -> None:
    with pytest.raises(ValueError, match="max-idle"):
        next(frames([ev(MAX_SECONDS + 10, "x")], renderer, fps=1, hold=0.0))
