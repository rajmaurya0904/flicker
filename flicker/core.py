"""Orchestration: recording -> frames -> encoded video."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .cast import Event, Recording
from .encoder import EncodeError, Encoder, effective_fps, infer_format
from .fonts import load_fonts
from .idle import apply_timing
from .render import Renderer
from .screen import Terminal
from .theme import get_theme
from .timeline import frame_count, frames, output_events

Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class RenderOptions:
    """Everything that controls how a recording becomes a video."""

    fmt: str | None = None  # mp4, webm or gif; inferred from the output name when None
    fps: int = 20
    theme: str = "dark"
    font: str | None = None
    font_size: int = 16
    padding: int = 16
    cursor: bool = True
    max_idle: float | None = None
    speed: float = 1.0
    hold: float = 1.0
    crf: int | None = None
    webm_codec: str = "vp9"

    def validate(self) -> None:
        if not 1 <= self.fps <= 60:
            raise ValueError("fps must be between 1 and 60")
        if self.speed <= 0:
            raise ValueError("speed must be greater than 0")
        if self.hold < 0:
            raise ValueError("hold must not be negative")
        if self.max_idle is not None and self.max_idle < 0:
            raise ValueError("max-idle must not be negative")
        if self.padding < 0:
            raise ValueError("padding must not be negative")


@dataclass(frozen=True)
class RenderResult:
    """Summary of a finished render."""

    output: Path
    fmt: str
    width: int
    height: int
    fps: int
    frames: int
    seconds: float
    size_bytes: int
    skipped_events: int


def with_command_line(rec: Recording, shown: str, prompt: str = "$ ") -> Recording:
    """Prepend a synthetic ``$ command`` line, as if the command had just been typed."""
    line = Event(0.0, "o", f"{prompt}{shown}\r\n")
    return rec.with_events([line, *rec.events])


def prepare_events(rec: Recording, opts: RenderOptions) -> list[Event]:
    """Apply idle compression and speed to the output events of ``rec``."""
    return apply_timing(output_events(rec.events), max_idle=opts.max_idle, speed=opts.speed)


def plan(rec: Recording, opts: RenderOptions) -> tuple[int, float]:
    """Return ``(frame_count, seconds)`` that rendering ``rec`` would produce."""
    opts.validate()
    n = frame_count(prepare_events(rec, opts), opts.fps, opts.hold)
    return n, n / opts.fps


def render_recording(
    rec: Recording,
    output: str | os.PathLike[str],
    opts: RenderOptions | None = None,
    progress: Progress | None = None,
) -> RenderResult:
    """Render ``rec`` to a video file at ``output``."""
    opts = opts or RenderOptions()
    opts.validate()
    fmt = infer_format(output, opts.fmt)
    fps = effective_fps(fmt, opts.fps)
    opts = replace(opts, fps=fps)

    fonts = load_fonts(opts.font, opts.font_size)
    renderer = Renderer(
        rec.cols,
        rec.rows,
        fonts,
        get_theme(opts.theme),
        padding=opts.padding,
        show_cursor=opts.cursor,
    )
    events = prepare_events(rec, opts)
    term = Terminal(rec.cols, rec.rows)
    count = 0
    with Encoder(
        output, fmt, renderer.width, renderer.height, fps, crf=opts.crf, webm_codec=opts.webm_codec
    ) as enc:
        for frame in frames(
            events, renderer, fps, hold=opts.hold, on_progress=progress, terminal=term
        ):
            enc.write(frame)
            count += 1
        path = enc.finish()
    if count == 0:
        raise EncodeError("nothing was rendered")
    return RenderResult(
        output=path,
        fmt=fmt,
        width=renderer.width,
        height=renderer.height,
        fps=fps,
        frames=count,
        seconds=count / fps,
        size_bytes=path.stat().st_size,
        skipped_events=term.skipped,
    )
