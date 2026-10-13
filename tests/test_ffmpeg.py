"""Tests for FFmpeg dependency checker."""

from unittest.mock import patch

import pytest

from flicker.ffmpeg import check_ffmpeg


def test_check_ffmpeg_success() -> None:
    """Check that ffmpeg and ffprobe are found."""
    with patch("flicker.ffmpeg.shutil.which") as mock_which:
        # Simulate both executables being found
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        assert check_ffmpeg() is True


def test_check_ffmpeg_missing_ffmpeg() -> None:
    """Check that RuntimeError is raised when ffmpeg is missing."""
    with patch("flicker.ffmpeg.shutil.which") as mock_which:
        # Simulate ffmpeg missing, ffprobe present
        mock_which.side_effect = lambda cmd: None if cmd == "ffmpeg" else "/usr/bin/ffprobe"
        with pytest.raises(RuntimeError) as excinfo:
            check_ffmpeg()
        assert "Missing executables: ffmpeg" in str(excinfo.value)


def test_check_ffmpeg_missing_ffprobe() -> None:
    """Check that RuntimeError is raised when ffprobe is missing."""
    with patch("flicker.ffmpeg.shutil.which") as mock_which:
        # Simulate ffprobe missing, ffmpeg present
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None
        with pytest.raises(RuntimeError) as excinfo:
            check_ffmpeg()
        assert "Missing executables: ffprobe" in str(excinfo.value)


def test_check_ffmpeg_missing_both() -> None:
    """Check that RuntimeError is raised when both are missing."""
    with patch("flicker.ffmpeg.shutil.which") as mock_which:
        mock_which.return_value = None
        with pytest.raises(RuntimeError) as excinfo:
            check_ffmpeg()
        assert "Missing executables: ffmpeg, ffprobe" in str(excinfo.value)