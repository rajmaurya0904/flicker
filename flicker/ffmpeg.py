"""Locate ffmpeg and ffprobe, check their codecs, and inspect finished videos."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

INSTALL_HINT = "install ffmpeg (https://ffmpeg.org/download.html) and make sure it is on PATH"


class FFmpegError(RuntimeError):
    """Raised when ffmpeg is missing, lacks a codec, or fails."""


def check_ffmpeg() -> bool:
    """Check if ffmpeg and ffprobe are available in PATH.

    Returns:
        True if both executables are found.

    Raises:
        FFmpegError: If either ffmpeg or ffprobe is missing.
    """
    missing = [cmd for cmd in ("ffmpeg", "ffprobe") if shutil.which(cmd) is None]
    if missing:
        raise FFmpegError(f"Missing executables: {', '.join(missing)}; {INSTALL_HINT}")
    return True


def ffmpeg_path() -> str:
    """Full path of the ffmpeg executable."""
    check_ffmpeg()
    path = shutil.which("ffmpeg")
    assert path is not None
    return path


def ffprobe_path() -> str:
    """Full path of the ffprobe executable."""
    check_ffmpeg()
    path = shutil.which("ffprobe")
    assert path is not None
    return path


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        raise FFmpegError(f"cannot run {args[0]}: {exc.strerror or exc}") from exc
    if proc.returncode != 0:
        raise FFmpegError(f"{Path(args[0]).stem} failed: {proc.stderr.strip()[-400:]}")
    return proc.stdout


def version() -> str:
    """First line of ``ffmpeg -version``, e.g. ``ffmpeg version 7.1``."""
    return _run([ffmpeg_path(), "-hide_banner", "-version"]).splitlines()[0]


@cache
def _encoders(ffmpeg: str) -> frozenset[str]:
    names = set()
    for line in _run([ffmpeg, "-hide_banner", "-encoders"]).splitlines():
        parts = line.split()
        # Encoder rows look like " V....D libx264  description"; the header has no flags column.
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def has_encoder(name: str) -> bool:
    """True if this ffmpeg build can encode with ``name`` (for example ``libx264``)."""
    return name in _encoders(ffmpeg_path())


def require_encoder(name: str, container: str) -> None:
    """Raise a clear error if ``name`` is not compiled into this ffmpeg."""
    if not has_encoder(name):
        raise FFmpegError(
            f"your ffmpeg build has no {name} encoder, which {container} output needs; "
            "install a full ffmpeg build"
        )


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe reports about a finished video."""

    codec: str
    width: int
    height: int
    duration: float
    frames: int | None
    size_bytes: int


def probe(path: str | Path) -> MediaInfo:
    """Inspect a video file with ffprobe."""
    p = Path(path)
    if not p.is_file():
        raise FFmpegError(f"no such file: {p}")
    out = _run(
        [
            ffprobe_path(),
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            "-select_streams", "v:0",
            str(p),
        ]  # fmt: skip
    )
    try:
        data = json.loads(out)
        stream = data["streams"][0]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise FFmpegError(f"{p} does not contain a video stream") from exc

    def number(*values: object) -> float:
        for v in values:
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        return 0.0

    frames = stream.get("nb_frames")
    return MediaInfo(
        codec=str(stream.get("codec_name", "?")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        duration=number(stream.get("duration"), data.get("format", {}).get("duration")),
        frames=int(frames) if isinstance(frames, str) and frames.isdigit() else None,
        size_bytes=p.stat().st_size,
    )
