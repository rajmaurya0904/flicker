"""Timeline edits: idle-time compression and playback speed."""

from __future__ import annotations

from collections.abc import Sequence

from .cast import Event


def compress_idle(events: Sequence[Event], max_idle: float) -> list[Event]:
    """Shorten every pause longer than ``max_idle`` seconds down to ``max_idle``.

    The gap before the first event is treated like any other pause, measured from time
    zero. Events keep their order and relative content; only the timestamps move.
    """
    if max_idle < 0:
        raise ValueError("max_idle must not be negative")
    out: list[Event] = []
    saved = 0.0
    previous = 0.0
    for ev in events:
        gap = ev.time - previous
        if gap > max_idle:
            saved += gap - max_idle
        previous = ev.time
        out.append(Event(ev.time - saved, ev.kind, ev.data))
    return out


def scale_time(events: Sequence[Event], speed: float) -> list[Event]:
    """Play the events ``speed`` times faster (``2.0`` halves every timestamp)."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    return [Event(ev.time / speed, ev.kind, ev.data) for ev in events]


def apply_timing(
    events: Sequence[Event], *, max_idle: float | None = None, speed: float = 1.0
) -> list[Event]:
    """Apply idle compression first, then the speed factor."""
    result = list(events)
    if max_idle is not None:
        result = compress_idle(result, max_idle)
    if speed != 1.0:
        result = scale_time(result, speed)
    return result
