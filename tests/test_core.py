"""Tests for the record-to-video orchestration."""

import pytest

from flicker.cast import Event, Recording
from flicker.core import (
    RenderOptions,
    plan,
    prepare_events,
    render_recording,
    with_command_line,
)
from flicker.ffmpeg import probe
from flicker.fonts import FontError
from flicker.theme import ThemeError

from .conftest import requires_ffmpeg, requires_font


def rec(*events: Event, cols: int = 30, rows: int = 6) -> Recording:
    return Recording(cols=cols, rows=rows, events=list(events), command="demo")


def test_with_command_line_prepends_a_prompt_line() -> None:
    out = with_command_line(rec(Event(0.5, "o", "result")), "ls -l")
    assert out.events[0] == Event(0.0, "o", "$ ls -l\r\n")
    assert out.events[1].data == "result"
    assert out.command == "demo"


def test_prepare_events_drops_resizes_and_applies_timing() -> None:
    r = rec(Event(0.0, "o", "a"), Event(0.1, "r", "10x10"), Event(10.0, "o", "b"))
    out = prepare_events(r, RenderOptions(max_idle=1.0, speed=2.0))
    assert [e.data for e in out] == ["a", "b"]
    assert out[1].time == pytest.approx(0.5)


def test_plan_counts_frames_and_seconds() -> None:
    frames, seconds = plan(rec(Event(2.0, "o", "x")), RenderOptions(fps=10, hold=1.0))
    assert frames == 31
    assert seconds == pytest.approx(3.1)


def test_plan_reflects_idle_compression() -> None:
    r = rec(Event(0.0, "o", "a"), Event(30.0, "o", "b"))
    slow = plan(r, RenderOptions(fps=10, hold=0.0))[1]
    fast = plan(r, RenderOptions(fps=10, hold=0.0, max_idle=2.0))[1]
    assert slow > 29 and fast < 3


@pytest.mark.parametrize(
    "kw",
    [
        {"fps": 0},
        {"fps": 61},
        {"speed": 0},
        {"hold": -1},
        {"max_idle": -0.5},
        {"padding": -1},
    ],
)
def test_invalid_options_are_rejected(kw: dict) -> None:
    with pytest.raises(ValueError):
        RenderOptions(**kw).validate()


@requires_font
@requires_ffmpeg
def test_renders_an_mp4_with_the_expected_shape(tmp_path) -> None:
    out = tmp_path / "demo.mp4"
    r = rec(Event(0.0, "o", "hello\r\n"), Event(1.0, "o", "\x1b[32mworld\x1b[0m"))
    result = render_recording(r, out, RenderOptions(fps=10, hold=0.5))
    info = probe(out)
    assert result.output == out and out.exists()
    assert result.fmt == "mp4" and result.fps == 10
    assert (info.width, info.height) == (result.width, result.height)
    assert info.codec == "h264"
    assert info.duration == pytest.approx(result.seconds, abs=0.2)
    assert result.size_bytes == out.stat().st_size > 0
    assert result.skipped_events == 0


@requires_font
@requires_ffmpeg
def test_renders_webm_when_asked_by_extension(tmp_path) -> None:
    out = tmp_path / "demo.webm"
    render_recording(rec(Event(0.0, "o", "x")), out, RenderOptions(fps=5, hold=0.4))
    assert probe(out).codec == "vp9"


@requires_font
@requires_ffmpeg
def test_explicit_format_overrides_extension(tmp_path) -> None:
    out = tmp_path / "demo.bin"
    render_recording(rec(Event(0.0, "o", "x")), out, RenderOptions(fmt="gif", fps=5, hold=0.4))
    assert probe(out).codec == "gif"


@requires_font
@requires_ffmpeg
def test_gif_frame_rate_is_capped_in_the_result(tmp_path) -> None:
    out = tmp_path / "demo.gif"
    result = render_recording(rec(Event(0.0, "o", "x")), out, RenderOptions(fps=40, hold=0.5))
    assert result.fps == 20


@requires_font
@requires_ffmpeg
def test_idle_compression_shortens_the_video(tmp_path) -> None:
    r = rec(Event(0.0, "o", "a"), Event(20.0, "o", "b"))
    long_ = render_recording(r, tmp_path / "a.mp4", RenderOptions(fps=2, hold=0.0))
    short = render_recording(r, tmp_path / "b.mp4", RenderOptions(fps=2, hold=0.0, max_idle=1.0))
    assert long_.seconds > 19 and short.seconds < 3


@requires_font
@requires_ffmpeg
def test_speed_scales_the_duration(tmp_path) -> None:
    r = rec(Event(0.0, "o", "a"), Event(8.0, "o", "b"))
    normal = render_recording(r, tmp_path / "a.mp4", RenderOptions(fps=2, hold=0.0))
    double = render_recording(r, tmp_path / "b.mp4", RenderOptions(fps=2, hold=0.0, speed=2.0))
    assert double.seconds == pytest.approx(normal.seconds / 2, abs=1.0)


@requires_font
@requires_ffmpeg
def test_empty_recording_still_renders_a_blank_clip(tmp_path) -> None:
    out = tmp_path / "blank.mp4"
    result = render_recording(rec(), out, RenderOptions(fps=5, hold=0.4))
    assert result.frames >= 2 and out.exists()


@requires_font
@requires_ffmpeg
def test_progress_callback_runs_to_completion(tmp_path) -> None:
    seen: list[tuple[int, int]] = []
    result = render_recording(
        rec(Event(0.0, "o", "x")),
        tmp_path / "p.mp4",
        RenderOptions(fps=5, hold=0.4),
        progress=lambda done, total: seen.append((done, total)),
    )
    assert seen[-1] == (result.frames, result.frames)


@requires_font
@requires_ffmpeg
def test_unknown_theme_fails_before_writing_anything(tmp_path) -> None:
    with pytest.raises(ThemeError):
        render_recording(rec(), tmp_path / "x.mp4", RenderOptions(theme="neon"))
    assert list(tmp_path.iterdir()) == []


@requires_font
def test_bad_font_path_is_a_font_error(tmp_path) -> None:
    with pytest.raises(FontError):
        render_recording(rec(), tmp_path / "x.mp4", RenderOptions(font=str(tmp_path / "no.ttf")))


@requires_font
def test_unknown_extension_is_a_value_error(tmp_path) -> None:
    with pytest.raises(ValueError, match="format"):
        render_recording(rec(), tmp_path / "x.avi")
