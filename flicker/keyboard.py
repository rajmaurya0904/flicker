"""Forward the user's keyboard to a pseudo-terminal session while recording interactively."""

from __future__ import annotations

import os
import sys
import threading

from .pty import IS_WINDOWS, PtySession

# Windows consoles report special keys as a prefix character followed by a scan code.
_WINDOWS_KEYS = {
    "H": "\x1b[A",  # up
    "P": "\x1b[B",  # down
    "M": "\x1b[C",  # right
    "K": "\x1b[D",  # left
    "G": "\x1b[H",  # home
    "O": "\x1b[F",  # end
    "S": "\x1b[3~",  # delete
    "I": "\x1b[5~",  # page up
    "Q": "\x1b[6~",  # page down
}


def translate_windows_key(code: str) -> str:
    """Escape sequence for the second half of a Windows special-key press, or ``""``."""
    return _WINDOWS_KEYS.get(code, "")


class StdinForwarder:
    """Context manager that puts the keyboard in raw mode and feeds ``session``.

    Raw mode means Ctrl+C and friends reach the recorded program instead of interrupting
    flicker itself. The previous terminal mode is always restored on exit.
    """

    def __init__(self, session: PtySession) -> None:
        self._session = session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._saved = None

    def __enter__(self) -> StdinForwarder:
        if not sys.stdin.isatty():
            raise RuntimeError("interactive recording needs a terminal on standard input")
        if IS_WINDOWS:
            target = self._pump_windows
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(fd)
            tty.setraw(fd)
            target = self._pump_posix
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self._saved is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)

    def _pump_posix(self) -> None:
        import select

        fd = sys.stdin.fileno()
        while not self._stop.is_set():
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            data = os.read(fd, 4096)
            if not data:
                return
            self._session.write(data.decode("utf-8", errors="replace"))

    def _pump_windows(self) -> None:  # pragma: no cover - needs a real console
        import msvcrt
        import time

        while not self._stop.is_set():
            if not msvcrt.kbhit():
                time.sleep(0.01)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                out = translate_windows_key(msvcrt.getwch())
            else:
                out = ch
            if out:
                self._session.write(out)
