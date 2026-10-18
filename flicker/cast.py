"""Recording model and asciicast reader/writer.

A :class:`Recording` is a terminal size plus a list of timestamped output events. It is
stored on disk as an asciicast file (the format used by asciinema), so a recording made by
flicker can be replayed by other tools and a ``.cast`` made elsewhere can be rendered to
video by flicker. Version 2 is written; versions 2 and 3 are read.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


class CastError(ValueError):
    """Raised when a recording file cannot be parsed."""


@dataclass(frozen=True)
class Event:
    """One thing that happened at ``time`` seconds after the recording started.

    ``kind`` is ``"o"`` for output written to the terminal, or ``"r"`` for a resize, in
    which case ``data`` is ``"COLSxROWS"``.
    """

    time: float
    kind: str
    data: str

    def resize(self) -> tuple[int, int]:
        """Return ``(cols, rows)`` for a resize event."""
        try:
            cols, rows = self.data.lower().split("x", 1)
            return int(cols), int(rows)
        except ValueError as exc:
            raise CastError(f"bad resize event data: {self.data!r}") from exc


@dataclass
class Recording:
    """Terminal dimensions plus the ordered events that happened in it."""

    cols: int
    rows: int
    events: list[Event] = field(default_factory=list)
    command: str | None = None
    title: str | None = None
    timestamp: int | None = None
    env: dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Time of the last event, or 0.0 for an empty recording."""
        return self.events[-1].time if self.events else 0.0

    def output_text(self) -> str:
        """All output concatenated, escape sequences included."""
        return "".join(e.data for e in self.events if e.kind == "o")

    def with_events(self, events: list[Event]) -> Recording:
        """Copy of this recording carrying a different event list."""
        return Recording(
            cols=self.cols,
            rows=self.rows,
            events=events,
            command=self.command,
            title=self.title,
            timestamp=self.timestamp,
            env=dict(self.env),
        )


def _check_size(cols: object, rows: object) -> tuple[int, int]:
    if not isinstance(cols, int) or not isinstance(rows, int) or cols < 1 or rows < 1:
        raise CastError(f"invalid terminal size: {cols!r}x{rows!r}")
    return cols, rows


def dumps(rec: Recording) -> str:
    """Serialise ``rec`` as an asciicast v2 document."""
    header: dict[str, object] = {"version": 2, "width": rec.cols, "height": rec.rows}
    header["timestamp"] = rec.timestamp if rec.timestamp is not None else int(time.time())
    if rec.command:
        header["command"] = rec.command
    if rec.title:
        header["title"] = rec.title
    if rec.env:
        header["env"] = rec.env
    lines = [json.dumps(header, ensure_ascii=False)]
    for ev in rec.events:
        lines.append(json.dumps([round(ev.time, 6), ev.kind, ev.data], ensure_ascii=False))
    return "\n".join(lines) + "\n"


def loads(text: str) -> Recording:
    """Parse an asciicast v2 or v3 document."""
    rows_iter = [ln for ln in text.splitlines() if ln.strip()]
    if not rows_iter:
        raise CastError("empty recording file")
    try:
        header = json.loads(rows_iter[0])
    except json.JSONDecodeError as exc:
        raise CastError(f"first line is not a JSON header: {exc}") from exc
    if not isinstance(header, dict):
        raise CastError("header must be a JSON object")

    version = header.get("version")
    if version == 2:
        cols, rows = _check_size(header.get("width"), header.get("height"))
        relative = False
    elif version == 3:
        term = header.get("term")
        if not isinstance(term, dict):
            raise CastError("v3 header is missing the 'term' object")
        cols, rows = _check_size(term.get("cols"), term.get("rows"))
        relative = True
    else:
        raise CastError(f"unsupported asciicast version: {version!r}")

    events: list[Event] = []
    clock = 0.0
    for lineno, raw in enumerate(rows_iter[1:], start=2):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CastError(f"line {lineno}: invalid JSON: {exc}") from exc
        if not (isinstance(item, list) and len(item) == 3):
            raise CastError(f"line {lineno}: event must be [time, code, data]")
        stamp, kind, data = item
        if isinstance(stamp, bool) or not isinstance(stamp, int | float) or stamp < 0:
            raise CastError(f"line {lineno}: bad event time {stamp!r}")
        if not isinstance(kind, str) or not isinstance(data, str):
            raise CastError(f"line {lineno}: event code and data must be strings")
        clock = clock + float(stamp) if relative else float(stamp)
        if kind in ("o", "r"):
            events.append(Event(clock, kind, data))
        # input ("i"), markers ("m") and exit ("x") events do not change what is drawn

    for prev, cur in zip(events, events[1:], strict=False):
        if cur.time < prev.time:
            raise CastError(f"event times go backwards ({prev.time} then {cur.time})")

    env = header.get("env")
    title = header.get("title")
    command = header.get("command")
    stamp = header.get("timestamp")
    return Recording(
        cols=cols,
        rows=rows,
        events=events,
        command=command if isinstance(command, str) else None,
        title=title if isinstance(title, str) else None,
        timestamp=stamp if isinstance(stamp, int) else None,
        env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
    )


def write(path: str | Path, rec: Recording) -> None:
    """Write ``rec`` to ``path`` as UTF-8 asciicast v2."""
    Path(path).write_text(dumps(rec), encoding="utf-8", newline="\n")


def read(path: str | Path) -> Recording:
    """Read a recording from ``path``."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise CastError(f"cannot read {p}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise CastError(f"{p} is not valid UTF-8 text") from exc
    return loads(text)
