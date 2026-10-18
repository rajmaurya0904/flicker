"""Tests for the capture engine: command in, timestamped events out."""

import sys

import pytest

from flicker.capture import capture, default_shell, format_command
from flicker.keyboard import translate_windows_key
from flicker.pty import PtyError

PY = sys.executable


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def text_of(result) -> str:
    return result.recording.output_text()


def test_captures_output_and_exit_code() -> None:
    result = capture(py("print('captured line')"), 80, 24)
    assert "captured line" in text_of(result)
    assert result.exit_code == 0
    assert not result.interrupted and not result.timed_out


def test_reports_nonzero_exit_code() -> None:
    result = capture(py("print('bye'); raise SystemExit(5)"), 80, 24)
    assert result.exit_code == 5
    assert "bye" in text_of(result)


def test_events_are_ordered_and_start_near_zero() -> None:
    result = capture(py("import time; print('a', flush=True); time.sleep(0.3); print('b')"), 80, 24)
    times = [e.time for e in result.recording.events]
    assert times == sorted(times)
    assert times[0] >= 0
    assert result.recording.duration >= 0.2
    assert text_of(result).index("a") < text_of(result).index("b")


def test_recording_header_describes_the_session() -> None:
    cmd = py("pass")
    result = capture(cmd, 100, 30)
    rec = result.recording
    assert (rec.cols, rec.rows) == (100, 30)
    assert rec.command == format_command(cmd)
    assert rec.timestamp and rec.env["TERM"]


def test_echo_callback_sees_every_chunk() -> None:
    seen: list[str] = []
    result = capture(py("print('mirrored')"), 80, 24, echo=seen.append)
    assert "".join(seen) == text_of(result)
    assert "mirrored" in "".join(seen)


def test_max_duration_stops_a_runaway_command() -> None:
    cmd = py("import time; print('tick', flush=True); time.sleep(60)")
    result = capture(cmd, 80, 24, max_duration=1.5)
    assert result.timed_out
    assert "tick" in text_of(result)
    assert result.exit_code is not None and result.exit_code != 0


def test_keyboard_interrupt_keeps_partial_output() -> None:
    cmd = py("import time; print('partial', flush=True); time.sleep(60)")

    def interrupt(_chunk: str) -> None:
        raise KeyboardInterrupt

    result = capture(cmd, 80, 24, echo=interrupt)
    assert result.interrupted
    assert "partial" in text_of(result)
    assert result.exit_code is not None


def test_missing_command_raises_pty_error() -> None:
    with pytest.raises(PtyError):
        capture(["no-such-binary-for-flicker-tests"], 80, 24)


def test_command_with_no_output_gives_empty_recording() -> None:
    result = capture(py("pass"), 80, 24)
    assert text_of(result) == "" or text_of(result).strip() == ""
    assert result.exit_code == 0


def test_cwd_is_passed_through(tmp_path) -> None:
    result = capture(py("import os; print(os.getcwd())"), 120, 24, cwd=tmp_path)
    assert tmp_path.name in text_of(result)


def test_env_override_reaches_the_child() -> None:
    import os

    env = dict(os.environ, FLICKER_PROBE="sentinel-value")
    result = capture(py("import os; print(os.environ['FLICKER_PROBE'])"), 80, 24, env=env)
    assert "sentinel-value" in text_of(result)


def test_format_command_quotes_arguments_with_spaces() -> None:
    rendered = format_command(["echo", "hello world"])
    assert "hello world" in rendered
    assert rendered.startswith("echo")
    assert '"' in rendered or "'" in rendered


def test_default_shell_is_an_executable_name() -> None:
    shell = default_shell()
    assert len(shell) == 1 and shell[0]


@pytest.mark.parametrize(
    "code, expected",
    [("H", "\x1b[A"), ("P", "\x1b[B"), ("M", "\x1b[C"), ("K", "\x1b[D"), ("S", "\x1b[3~")],
)
def test_windows_special_keys_become_escape_sequences(code: str, expected: str) -> None:
    assert translate_windows_key(code) == expected


def test_unmapped_windows_key_is_dropped() -> None:
    assert translate_windows_key("\x86") == ""
