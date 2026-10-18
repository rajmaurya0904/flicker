"""Terminal emulation: turn a stream of output events into a screen of styled cells."""

from __future__ import annotations

import pyte

from .cast import Event, Recording


class Terminal:
    """A fixed-size virtual terminal that understands ANSI/VT escape sequences."""

    def __init__(self, cols: int, rows: int) -> None:
        if cols < 1 or rows < 1:
            raise ValueError(f"terminal size must be positive, got {cols}x{rows}")
        self.screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self.screen)
        self._last_cursor: tuple[int, int, bool] | None = None
        self.skipped = 0  # events the emulator could not parse

    @property
    def cols(self) -> int:
        return self.screen.columns

    @property
    def rows(self) -> int:
        return self.screen.lines

    def feed(self, text: str) -> None:
        """Process output text. A malformed sequence is skipped rather than aborting."""
        try:
            self._stream.feed(text)
        except Exception:  # pyte raises assorted errors on sequences it half-understands
            self.skipped += 1

    def resize(self, cols: int, rows: int) -> None:
        self.screen.resize(lines=rows, columns=cols)

    def apply(self, event: Event) -> None:
        """Apply a recorded event: output text or a resize."""
        if event.kind == "o":
            self.feed(event.data)
        elif event.kind == "r":
            cols, rows = event.resize()
            self.resize(cols, rows)

    def take_changes(self) -> bool:
        """True if anything visible changed since the last call (text, style or cursor)."""
        cursor = self.screen.cursor
        state = (cursor.x, cursor.y, cursor.hidden)
        changed = bool(self.screen.dirty) or state != self._last_cursor
        self.screen.dirty.clear()
        self._last_cursor = state
        return changed

    def lines(self) -> list[str]:
        """Plain text of every row with trailing blanks removed."""
        return [line.rstrip() for line in self.screen.display]

    def text(self) -> str:
        """Plain text of the screen with trailing blank rows dropped."""
        rows = self.lines()
        while rows and not rows[-1]:
            rows.pop()
        return "\n".join(rows)


def final_screen(rec: Recording) -> Terminal:
    """Replay a whole recording and return the terminal as it ends up."""
    term = Terminal(rec.cols, rec.rows)
    for ev in rec.events:
        term.apply(ev)
    return term
