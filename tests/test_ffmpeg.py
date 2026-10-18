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

SAMPLE_ENCODERS = """\
Encoders:
 V..... = Video
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V....D libvpx-vp9           libvpx VP9 (codec vp9)
 A....D aac                  AAC (Advanced Audio Coding)
"""


def test_error_message_tells_the_user_how_to_fix_it() -> None:
    from flicker.ffmpeg import FFmpegError

    with patch("flicker.ffmpeg.shutil.which", return_value=None):
        with pytest.raises(FFmpegError, match="on PATH"):
            check_ffmpeg()


def test_error_type_is_a_runtime_error() -> None:
    from flicker.ffmpeg import FFmpegError

    assert issubclass(FFmpegError, RuntimeError)


def test_encoder_listing_is_parsed() -> None:
    from flicker import ffmpeg

    ffmpeg._encoders.cache_clear()
    with (
        patch("flicker.ffmpeg.shutil.which", side_effect=lambda c: f"/bin/{c}"),
        patch("flicker.ffmpeg._run", return_value=SAMPLE_ENCODERS),
    ):
        assert ffmpeg.has_encoder("libx264")
        assert ffmpeg.has_encoder("libvpx-vp9")
        assert not ffmpeg.has_encoder("libvpx")
        assert not ffmpeg.has_encoder("Encoders:")
    ffmpeg._encoders.cache_clear()


def test_require_encoder_names_the_missing_codec() -> None:
    from flicker import ffmpeg

    ffmpeg._encoders.cache_clear()
    with (
        patch("flicker.ffmpeg.shutil.which", side_effect=lambda c: f"/bin/{c}"),
        patch("flicker.ffmpeg._run", return_value=SAMPLE_ENCODERS),
        pytest.raises(ffmpeg.FFmpegError, match="libvpx.*WebM"),
    ):
        ffmpeg.require_encoder("libvpx", "WebM")
    ffmpeg._encoders.cache_clear()


def test_probe_rejects_missing_file(tmp_path) -> None:
    from flicker import ffmpeg

    with (
        patch("flicker.ffmpeg.shutil.which", side_effect=lambda c: f"/bin/{c}"),
        pytest.raises(ffmpeg.FFmpegError, match="no such file"),
    ):
        ffmpeg.probe(tmp_path / "missing.mp4")
