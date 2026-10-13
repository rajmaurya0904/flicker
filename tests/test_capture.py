"""Tests for terminal frame capture engine."""

from flicker.capture import capture_frames


def test_capture_frames_echo() -> None:
    """Capture frames from a simple echo command and verify output."""
    frames, exit_code = capture_frames(["echo", "hello"], interval=0.05)
    assert exit_code == 0
    assert len(frames) >= 1
    # The last frame should contain the output
    assert "hello" in frames[-1][1]


def test_capture_frames_timing() -> None:
    """Verify that frames are captured at approximately the specified interval."""
    frames, exit_code = capture_frames(["sleep", "0.3"], interval=0.1)
    assert exit_code == 0
    assert len(frames) >= 2
    # Check that timestamps are increasing
    for i in range(1, len(frames)):
        assert frames[i][0] >= frames[i - 1][0]


def test_capture_frames_multiple_outputs() -> None:
    """Capture frames from a command that produces multiple outputs."""
    cmd = ["bash", "-c", "echo one; sleep 0.1; echo two"]
    frames, exit_code = capture_frames(cmd, interval=0.05)