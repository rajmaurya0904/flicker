"""Shared test helpers: skip markers for tests that need a font or ffmpeg."""

import shutil

import pytest

from flicker.fonts import FontError, load_fonts


def _have_font() -> bool:
    try:
        load_fonts(size=14)
    except FontError:
        return False
    return True


requires_font = pytest.mark.skipif(not _have_font(), reason="no monospaced font installed")
requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are not installed",
)


@pytest.fixture
def no_font_env(monkeypatch):
    monkeypatch.delenv("FLICKER_FONT", raising=False)
