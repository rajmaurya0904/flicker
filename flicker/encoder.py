"""Pipe raw frames into ffmpeg and produce MP4, WebM or GIF files."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from .ffmpeg import FFmpegError, ffmpeg_path, require_encoder

FORMATS = ("mp4", "webm", "gif")
WEBM_CODECS = ("vp9", "vp8")
GIF_MAX_FPS = 20  # GIF frame delays are whole hundredths of a second

# (lowest, highest, default) constant-quality value for each encoder.
_CRF = {"libx264": (0, 51, 20), "libvpx-vp9": (0, 63, 32), "libvpx": (4, 63, 10)}


class EncodeError(FFmpegError):
    """Raised when ffmpeg rejects the frames or exits with an error."""


def infer_format(output: str | os.PathLike[str], explicit: str | None = None) -> str:
    """Pick the container from ``explicit`` or the output file extension."""
    if explicit is not None:
        fmt = explicit.lower().lstrip(".")
    else:
        fmt = Path(output).suffix.lower().lstrip(".")
        if not fmt:
            raise ValueError(f"cannot tell the format of {output!s}; use .mp4, .webm or .gif")
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format {fmt!r} (choose from: {', '.join(FORMATS)})")
    return fmt


def effective_fps(fmt: str, fps: int) -> int:
    """Frame rate actually written for ``fmt``."""
    return min(fps, GIF_MAX_FPS) if fmt == "gif" else fps


def video_codec(fmt: str, webm_codec: str = "vp9") -> str:
    """Name of the ffmpeg encoder used for ``fmt``."""
    if fmt == "mp4":
        return "libx264"
    if fmt == "webm":
        if webm_codec not in WEBM_CODECS:
            raise ValueError(f"unknown WebM codec {webm_codec!r} (choose vp9 or vp8)")
        return "libvpx-vp9" if webm_codec == "vp9" else "libvpx"
    if fmt == "gif":
        return "gif"
    raise ValueError(f"unsupported format {fmt!r}")


def build_command(
    ffmpeg: str,
    fmt: str,
    width: int,
    height: int,
    fps: int,
    output: str | os.PathLike[str],
    *,
    crf: int | None = None,
    webm_codec: str = "vp9",
) -> list[str]:
    """The ffmpeg argument list that reads raw RGB frames on stdin and writes ``output``."""
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise ValueError(f"frame size must be even and at least 2x2, got {width}x{height}")
    if fps < 1:
        raise ValueError("fps must be at least 1")
    codec = video_codec(fmt, webm_codec)
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-framerate", str(effective_fps(fmt, fps)), "-i", "-",
    ]  # fmt: skip
    if codec in _CRF:
        low, high, default = _CRF[codec]
        quality = default if crf is None else crf
        if not low <= quality <= high:
            raise ValueError(f"crf for {codec} must be between {low} and {high}, got {quality}")
    if fmt == "mp4":
        cmd += [
            "-c:v", "libx264", "-preset", "medium", "-crf", str(quality),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", "-f", "mp4",
        ]  # fmt: skip
    elif fmt == "webm" and codec == "libvpx-vp9":
        cmd += [
            "-c:v", "libvpx-vp9", "-crf", str(quality), "-b:v", "0", "-pix_fmt", "yuv420p",
            "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-an", "-f", "webm",
        ]  # fmt: skip
    elif fmt == "webm":
        cmd += [
            "-c:v", "libvpx", "-crf", str(quality), "-b:v", "1M", "-pix_fmt", "yuv420p",
            "-deadline", "good", "-cpu-used", "4", "-an", "-f", "webm",
        ]  # fmt: skip
    else:
        cmd += [
            "-vf",
            "split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=4",
            "-loop", "0", "-f", "gif",
        ]  # fmt: skip
    cmd.append(str(output))
    return cmd


class Encoder:
    """Writes frames into an ffmpeg process; the output appears only if encoding succeeds."""

    def __init__(
        self,
        output: str | os.PathLike[str],
        fmt: str,
        width: int,
        height: int,
        fps: int,
        *,
        crf: int | None = None,
        webm_codec: str = "vp9",
    ) -> None:
        self.output = Path(output)
        self.fmt = fmt
        self.frame_size = width * height * 3
        self._part = self.output.with_name(self.output.name + ".part")
        if not self.output.parent.is_dir():
            raise EncodeError(f"output directory does not exist: {self.output.parent}")
        codec = video_codec(fmt, webm_codec)
        if codec != "gif":
            require_encoder(codec, fmt.upper())
        self.command = build_command(
            ffmpeg_path(), fmt, width, height, fps, self._part, crf=crf, webm_codec=webm_codec
        )
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise EncodeError(f"cannot start ffmpeg: {exc.strerror or exc}") from exc
        self._stderr = bytearray()
        self._drain = threading.Thread(target=self._read_stderr, daemon=True)
        self._drain.start()
        self.frames = 0

    def _read_stderr(self) -> None:
        assert self._proc.stderr is not None
        for chunk in iter(lambda: self._proc.stderr.read(4096), b""):  # type: ignore[union-attr]
            self._stderr += chunk
            del self._stderr[:-8192]

    def _message(self) -> str:
        self._drain.join(timeout=2)
        text = bytes(self._stderr).decode("utf-8", errors="replace").strip()
        return text.splitlines()[-1] if text else "no error output"

    def write(self, frame: bytes) -> None:
        """Send one raw RGB24 frame."""
        if len(frame) != self.frame_size:
            raise ValueError(f"frame is {len(frame)} bytes, expected {self.frame_size}")
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(frame)
        except (BrokenPipeError, OSError):
            self._proc.wait()
            self._cleanup()
            raise EncodeError(f"ffmpeg stopped while encoding: {self._message()}") from None
        self.frames += 1

    def _cleanup(self) -> None:
        try:
            self._part.unlink()
        except OSError:
            pass

    def finish(self) -> Path:
        """Close the stream, wait for ffmpeg, and move the finished file into place."""
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        code = self._proc.wait()
        if code != 0:
            message = self._message()
            self._cleanup()
            raise EncodeError(f"ffmpeg exited with status {code}: {message}")
        if self.frames == 0:
            self._cleanup()
            raise EncodeError("no frames were written")
        os.replace(self._part, self.output)
        return self.output

    def abort(self) -> None:
        """Stop ffmpeg and discard the partial file."""
        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.wait()
        for stream in (self._proc.stdin, self._proc.stderr):
            try:
                stream.close()  # type: ignore[union-attr]
            except OSError:
                pass  # the buffered data is going nowhere; the process is already dead
        self._cleanup()

    def __enter__(self) -> Encoder:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
