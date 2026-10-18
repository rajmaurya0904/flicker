"""Turn timestamped events into a steady sequence of video frames."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Sequence

from .cast import Event
from .render import Renderer
from .screen import Terminal

MAX_SECONDS = 3600.0


def frame_count(events: Sequence[Event], fps: int, hold: float) -> int:
    """How many frames are needed to show every event and then hold the last screen."""
    if fps < 1:
        raise ValueError("fps must be at least 1")
    if hold < 0:
        raise ValueError("hold must not be negative")
    last = events[-1].time if events else 0.0
    return math.ceil((last + hold) * fps) + 1


def output_events(events: Sequence[Event]) -> list[Event]:
    """Only the events that change what is printed. Resizes are ignored: a video has one size."""
    return [e for e in events if e.kind == "o"]


def frames(
    events: Sequence[Event],
    renderer: Renderer,
    fps: int,
    *,
    hold: float = 1.0,
    on_progress: Callable[[int, int], None] | None = None,
    terminal: Terminal | None = None,
) -> Iterator[bytes]:
    """Yield one raw RGB24 frame per tick of a ``fps`` clock.

    Events that land between two ticks are applied together before the next frame is drawn.
    Only rows that changed since the previous frame are redrawn; unchanged ticks repeat the
    previous pixels.
    """
    evs = output_events(events)
    total = frame_count(evs, fps, hold)
    if total / fps > MAX_SECONDS:
        raise ValueError(
            f"recording would be {total / fps:.0f} s long (limit {MAX_SECONDS:.0f} s); "
            "shorten it with --max-idle or --speed"
        )
    term = terminal or Terminal(renderer.cols, renderer.rows)
    pending = 0
    current: bytes | None = None
    for k in range(total):
        tick = k / fps
        while pending < len(evs) and evs[pending].time <= tick + 1e-9:
            term.feed(evs[pending].data)
            pending += 1
        dirty = term.take_dirty_rows()
        if current is None:
            renderer.draw_rows(term, None)
            current = renderer.frame_bytes()
        elif dirty:
            renderer.draw_rows(term, dirty)
            current = renderer.frame_bytes()
        yield current
        if on_progress is not None:
            on_progress(k + 1, total)
