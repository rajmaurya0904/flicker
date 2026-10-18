"""Run a command in a pseudo-terminal and record what it prints, with timestamps."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass

from .cast import Event, Recording
from .keyboard import StdinForwarder
from .pty import IS_WINDOWS, PtySession


@dataclass
class CaptureResult:
    """What a capture produced and how it ended."""

    recording: Recording
    exit_code: int | None
    interrupted: bool = False
    timed_out: bool = False
    uses_tty: bool = True


def format_command(cmd: Sequence[str]) -> str:
    """Render ``cmd`` the way a user would type it."""
    return subprocess.list2cmdline(list(cmd)) if IS_WINDOWS else shlex.join(cmd)


def default_shell() -> list[str]:
    """The user's interactive shell, used when no command is given."""
    if IS_WINDOWS:
        return [os.environ.get("COMSPEC", "cmd.exe")]
    return [os.environ.get("SHELL", "/bin/sh")]


def capture(
    cmd: Sequence[str],
    cols: int = 80,
    rows: int = 24,
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    echo: Callable[[str], None] | None = None,
    interactive: bool = False,
    max_duration: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CaptureResult:
    """Run ``cmd`` to completion and return everything it printed, timestamped.

    ``echo`` is called with each chunk as it arrives so the caller can mirror the session
    to a real terminal. With ``interactive`` the caller's keyboard is forwarded to the
    child. ``max_duration`` kills the command after that many seconds. Ctrl+C (in
    non-interactive mode) stops the command but keeps what was captured so far.
    """
    events: list[Event] = []
    interrupted = False
    timed_out = False

    session = PtySession(cmd, cols=cols, rows=rows, env=env, cwd=cwd)
    started = clock()
    forwarder = StdinForwarder(session) if interactive else nullcontext()
    try:
        with forwarder:
            try:
                while True:
                    chunk = session.read(0.05)
                    if chunk is None:
                        break
                    if chunk:
                        events.append(Event(clock() - started, "o", chunk))
                        if echo is not None:
                            echo(chunk)
                    if max_duration is not None and clock() - started > max_duration:
                        timed_out = True
                        session.terminate()
                        break
            except KeyboardInterrupt:
                interrupted = True
                session.terminate()
        # Pick up anything the child wrote just before it stopped.
        while (chunk := session.read(0.05)) is not None:
            if chunk:
                events.append(Event(clock() - started, "o", chunk))
                if echo is not None:
                    echo(chunk)
            elif session.poll() is not None:
                break
        exit_code = session.wait(5.0)
        if exit_code is None:
            session.terminate()
            exit_code = session.wait(2.0)
        uses_tty = session.uses_tty
    finally:
        session.close()

    recording = Recording(
        cols=cols,
        rows=rows,
        events=events,
        command=format_command(cmd),
        timestamp=int(time.time()),
        env={"TERM": session_term(env)},
    )
    return CaptureResult(
        recording=recording,
        exit_code=exit_code,
        interrupted=interrupted,
        timed_out=timed_out,
        uses_tty=uses_tty,
    )


def session_term(env: Mapping[str, str] | None) -> str:
    """The TERM value the child was started with."""
    return (env or os.environ).get("TERM", "xterm-256color")
