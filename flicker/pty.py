"""Pseudo-terminal sessions for Linux, macOS and Windows.

``PtySession`` starts a command attached to a pseudo-terminal of a fixed size and hands the
text it prints back through :meth:`PtySession.read`. On POSIX systems it uses the standard
``pty`` module. On Windows it uses ConPTY through ``pywinpty``; when that package is not
installed it falls back to plain pipes, which means the child sees no terminal (programs
that check ``isatty`` will not emit colour) but everything else still works.
"""

from __future__ import annotations

import codecs
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence

IS_WINDOWS = sys.platform == "win32"

if not IS_WINDOWS:
    import fcntl
    import pty as _pty
    import struct
    import termios

try:
    import winpty as _winpty
except ImportError:
    _winpty = None

_EOF = object()
_CONPTY_GRACE = 0.3
_NEWLINE = re.compile(r"\r?\n")


class PtyError(RuntimeError):
    """Raised when a session cannot be started."""


def _resolve(cmd: Sequence[str], env: Mapping[str, str]) -> list[str]:
    """Find the executable on PATH so a missing command fails before anything is forked."""
    if not cmd:
        raise PtyError("no command given")
    exe = shutil.which(cmd[0], path=env.get("PATH"))
    if exe is None:
        raise PtyError(f"command not found: {cmd[0]}")
    return [exe, *cmd[1:]]


class PtySession:
    """A running command attached to a pseudo-terminal."""

    def __init__(
        self,
        cmd: Sequence[str],
        cols: int = 80,
        rows: int = 24,
        env: Mapping[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> None:
        if cols < 1 or rows < 1:
            raise PtyError(f"terminal size must be positive, got {cols}x{rows}")
        self.cols = cols
        self.rows = rows
        self.cmd = list(cmd)
        full_env = dict(os.environ if env is None else env)
        full_env.setdefault("TERM", "xterm-256color")
        full_env["COLUMNS"] = str(cols)
        full_env["LINES"] = str(rows)
        argv = _resolve(self.cmd, full_env)
        if cwd is not None and not os.path.isdir(cwd):
            raise PtyError(f"working directory does not exist: {cwd}")

        self._queue: queue.Queue[object] = queue.Queue()
        self._eof = False
        self._exit_code: int | None = None
        self._closed = False
        self._dead_since: float | None = None
        self.uses_tty = True
        self._pid = -1
        self._fd = -1
        self._proc = None
        self._popen: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread

        if IS_WINDOWS:
            if _winpty is not None:
                self._start_conpty(argv, full_env, cwd)
            else:
                self._start_pipes(argv, full_env, cwd)
        else:
            self._start_posix(argv, full_env, cwd)
        self._thread.start()

    # -- starting -----------------------------------------------------------------

    def _start_posix(self, argv: list[str], env: dict[str, str], cwd) -> None:
        pid, fd = _pty.fork()
        if pid == 0:  # pragma: no cover - runs in the child, before exec
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
                if cwd is not None:
                    os.chdir(cwd)
                os.execve(argv[0], argv, env)
            except BaseException as exc:
                os.write(2, f"flicker: cannot run {argv[0]}: {exc}\n".encode())
                os._exit(127)
        self._pid, self._fd = pid, fd
        self._thread = threading.Thread(target=self._pump_posix, daemon=True)

    def _start_conpty(self, argv: list[str], env: dict[str, str], cwd) -> None:
        try:
            self._proc = _winpty.PtyProcess.spawn(
                argv, cwd=str(cwd) if cwd else None, env=env, dimensions=(self.rows, self.cols)
            )
        except Exception as exc:  # pywinpty raises assorted types
            raise PtyError(f"cannot start {argv[0]}: {exc}") from exc
        self._thread = threading.Thread(target=self._pump_conpty, daemon=True)

    def _start_pipes(self, argv: list[str], env: dict[str, str], cwd) -> None:
        self.uses_tty = False
        try:
            self._popen = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
        except OSError as exc:
            raise PtyError(f"cannot start {argv[0]}: {exc.strerror or exc}") from exc
        self._thread = threading.Thread(target=self._pump_pipes, daemon=True)

    # -- reader threads -----------------------------------------------------------

    def _pump_posix(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            try:
                data = os.read(self._fd, 65536)
            except OSError:
                break
            if not data:
                break
            text = decoder.decode(data)
            if text:
                self._queue.put(text)
        tail = decoder.decode(b"", final=True)
        if tail:
            self._queue.put(tail)
        self._queue.put(_EOF)

    def _pump_conpty(self) -> None:
        while True:
            try:
                text = self._proc.read(65536)
            except (EOFError, OSError):
                break
            if text:
                self._queue.put(text)
        self._queue.put(_EOF)

    def _pump_pipes(self) -> None:
        assert self._popen is not None and self._popen.stdout is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            data = self._popen.stdout.read1(65536)
            if not data:
                break
            # Pipes carry bare LF; a terminal expects CR LF.
            text = _NEWLINE.sub("\r\n", decoder.decode(data))
            if text:
                self._queue.put(text)
        self._queue.put(_EOF)

    # -- public API ---------------------------------------------------------------

    def read(self, timeout: float = 0.05) -> str | None:
        """Return the next chunk of output, ``""`` if none arrived, ``None`` at end of output."""
        if self._eof:
            return None
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            if self._proc is not None and self.poll() is not None:
                # ConPTY keeps its output pipe open for several seconds after the child has
                # exited. Once the child is gone and the pipe has been quiet for a moment,
                # treat that as the end of the output.
                now = time.monotonic()
                if self._dead_since is None:
                    self._dead_since = now
                elif now - self._dead_since > _CONPTY_GRACE:
                    self._eof = True
                    return None
            return ""
        self._dead_since = None
        if item is _EOF:
            self._eof = True
            return None
        assert isinstance(item, str)
        return item

    def write(self, text: str) -> None:
        """Send keystrokes to the child."""
        if self._closed or self._eof:
            return
        try:
            if self._proc is not None:
                self._proc.write(text)
            elif self._fd >= 0:
                os.write(self._fd, text.encode("utf-8"))
        except OSError:
            pass  # child already gone

    def resize(self, cols: int, rows: int) -> None:
        """Change the terminal size the child sees."""
        if cols < 1 or rows < 1:
            raise PtyError(f"terminal size must be positive, got {cols}x{rows}")
        self.cols, self.rows = cols, rows
        if self._proc is not None:
            self._proc.setwinsize(rows, cols)
        elif self._fd >= 0:
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            try:
                os.killpg(self._pid, signal.SIGWINCH)
            except OSError:
                pass

    def poll(self) -> int | None:
        """Exit code if the child has finished, else ``None``. Never blocks."""
        if self._exit_code is not None:
            return self._exit_code
        if self._proc is not None:
            if self._proc.isalive():
                return None
            status = self._proc.exitstatus
            self._exit_code = status if isinstance(status, int) else -1
        elif self._popen is not None:
            code = self._popen.poll()
            if code is None:
                return None
            self._exit_code = code
        else:
            try:
                pid, status = os.waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                self._exit_code = -1
                return self._exit_code
            if pid == 0:
                return None
            if os.WIFEXITED(status):
                self._exit_code = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                self._exit_code = 128 + os.WTERMSIG(status)
            else:
                self._exit_code = -1
        return self._exit_code

    def wait(self, timeout: float | None = None) -> int | None:
        """Wait for the child to exit; ``None`` if ``timeout`` seconds pass first."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            code = self.poll()
            if code is not None:
                return code
            if deadline is not None and time.monotonic() >= deadline:
                return None
            time.sleep(0.01)

    def terminate(self) -> None:
        """Stop the child (and, where possible, everything it started)."""
        if self.poll() is not None:
            return
        if self._proc is not None:
            try:
                self._proc.terminate(force=True)
            except Exception:
                pass
        elif self._popen is not None:
            self._popen.kill()
        else:
            for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self._pid, sig)
                except OSError:
                    break
                if self.wait(0.5) is not None:
                    break
        self.wait(2.0)

    def close(self) -> None:
        """Release the pseudo-terminal. Safe to call more than once."""
        if self._closed:
            return
        self.terminate()
        self._closed = True
        if self._proc is not None:
            try:
                self._proc.close(force=True)
            except Exception:
                pass
        elif self._popen is not None and self._popen.stdout is not None:
            self._popen.stdout.close()
        elif self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._thread.join(timeout=0.2 if self._proc is not None else 1.0)

    def __enter__(self) -> PtySession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def spawn_pty(
    cmd: Sequence[str], cols: int = 80, rows: int = 24, timeout: float | None = None
) -> tuple[str, int]:
    """Run ``cmd`` to completion in a pseudo-terminal; return ``(output, exit_code)``.

    If ``timeout`` seconds pass first the command is killed and its exit code reflects that.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    parts: list[str] = []
    with PtySession(cmd, cols=cols, rows=rows) as session:
        while True:
            chunk = session.read(0.05)
            if chunk is None:
                break
            parts.append(chunk)
            if deadline is not None and time.monotonic() > deadline:
                session.terminate()
                break
        code = session.wait(5.0)
        if code is None:
            session.terminate()
            code = session.wait(2.0)
    return "".join(parts), -1 if code is None else code
