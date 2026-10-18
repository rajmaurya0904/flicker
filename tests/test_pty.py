"""Tests for pseudo-terminal sessions."""

import sys

import pytest

from flicker.pty import PtyError, PtySession, spawn_pty

PY = sys.executable


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def test_output_and_zero_exit_code() -> None:
    output, code = spawn_pty(py("print('hello from the pty')"), timeout=20)
    assert "hello from the pty" in output
    assert code == 0


def test_nonzero_exit_code_is_reported() -> None:
    _, code = spawn_pty(py("raise SystemExit(7)"), timeout=20)
    assert code == 7


def test_stderr_is_merged_into_the_stream() -> None:
    output, _ = spawn_pty(py("import sys; sys.stderr.write('oops\n')"), timeout=20)
    assert "oops" in output


def test_lines_end_with_carriage_return_newline() -> None:
    output, _ = spawn_pty(py("print('a'); print('b')"), timeout=20)
    assert "a\r\nb\r\n" in output


def test_unicode_output_survives() -> None:
    code = "import sys; sys.stdout.reconfigure(encoding='utf-8'); print('caf\u00e9 \u2713')"
    output, _ = spawn_pty(py(code), timeout=20)
    assert "café ✓" in output


def test_missing_command_raises_before_starting() -> None:
    with pytest.raises(PtyError, match="command not found"):
        PtySession(["definitely-not-a-real-command-xyz"])


def test_empty_command_raises() -> None:
    with pytest.raises(PtyError, match="no command"):
        PtySession([])


def test_bad_working_directory_raises(tmp_path) -> None:
    with pytest.raises(PtyError, match="working directory"):
        PtySession(py("pass"), cwd=tmp_path / "missing")


def test_working_directory_is_honoured(tmp_path) -> None:
    output, _ = spawn_pty_in(py("import os; print(os.getcwd())"), tmp_path)
    assert tmp_path.name in output


def spawn_pty_in(cmd: list[str], cwd) -> tuple[str, int]:
    parts = []
    with PtySession(cmd, cwd=cwd) as session:
        while (chunk := session.read(0.05)) is not None:
            parts.append(chunk)
        code = session.wait(10)
    return "".join(parts), -1 if code is None else code


def test_session_reports_end_of_output_as_none() -> None:
    with PtySession(py("pass")) as session:
        seen = []
        for _ in range(400):
            chunk = session.read(0.05)
            if chunk is None:
                break
            seen.append(chunk)
        else:
            pytest.fail("session never reached end of output")
        assert session.read(0.01) is None
        assert session.wait(10) == 0


def test_read_returns_empty_string_when_nothing_arrives() -> None:
    with PtySession(py("import time; time.sleep(5)")) as session:
        chunks = [session.read(0.05) for _ in range(3)]
        assert None not in chunks  # still running, so end-of-output has not been reached


def test_terminate_stops_a_long_running_child() -> None:
    with PtySession(py("import time; time.sleep(60)")) as session:
        assert session.poll() is None
        session.terminate()
        assert session.poll() is not None


def test_timeout_kills_the_command() -> None:
    slow = py("import time; print('start', flush=True); time.sleep(60)")
    output, code = spawn_pty(slow, timeout=1)
    assert "start" in output
    assert code != 0


@pytest.mark.skipif(sys.platform == "win32", reason="signal exit codes are POSIX specific")
def test_killed_by_signal_reports_128_plus_signal() -> None:
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    _, status = spawn_pty(py(code), timeout=20)
    assert status == 128 + 15


def test_invalid_size_rejected() -> None:
    with pytest.raises(PtyError, match="positive"):
        PtySession(py("pass"), cols=0, rows=10)
