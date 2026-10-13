"""Tests for PTY session spawn utility."""

from flicker.pty import spawn_pty


def test_spawn_pty_echo_hello() -> None:
    """Run a simple echo command in a PTY and verify output and exit code."""
    output, exit_code = spawn_pty(["echo", "hello"])
    assert "hello" in output
    assert exit_code == 0


def test_spawn_pty_exit_code() -> None:
    """Verify that the process exits successfully and output is correct."""
    output, exit_code = spawn_pty(["echo", "world"])
    assert "world" in output
    assert exit_code == 0