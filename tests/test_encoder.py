"""Tests for the ffmpeg command line and for real encodes."""

import pytest

from flicker.encoder import (
    EncodeError,
    Encoder,
    build_command,
    effective_fps,
    infer_format,
    video_codec,
)
from flicker.ffmpeg import probe

from .conftest import requires_ffmpeg


def cmd(fmt: str, **kw) -> list[str]:
    return build_command("ffmpeg", fmt, 640, 360, 15, "out." + fmt, **kw)


def arg_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_input_is_raw_rgb_on_stdin() -> None:
    args = cmd("mp4")
    assert arg_after(args, "-f") == "rawvideo"
    assert arg_after(args, "-pix_fmt") == "rgb24"
    assert arg_after(args, "-s") == "640x360"
    assert arg_after(args, "-framerate") == "15"
    assert arg_after(args, "-i") == "-"


def test_mp4_uses_h264_yuv420_faststart() -> None:
    args = cmd("mp4")
    assert "libx264" in args
    assert "yuv420p" in args
    assert "+faststart" in args
    assert arg_after(args, "-crf") == "20"
    assert args[-1] == "out.mp4"


def test_webm_defaults_to_vp9_constant_quality() -> None:
    args = cmd("webm")
    assert "libvpx-vp9" in args
    assert arg_after(args, "-b:v") == "0"
    assert arg_after(args, "-crf") == "32"
    assert "-f" in args and args[args.index("webm") - 1] == "-f"


def test_webm_vp8_option() -> None:
    args = cmd("webm", webm_codec="vp8")
    assert "libvpx" in args and "libvpx-vp9" not in args
    assert arg_after(args, "-crf") == "10"


def test_gif_uses_a_generated_palette() -> None:
    args = cmd("gif")
    vf = arg_after(args, "-vf")
    assert "palettegen" in vf and "paletteuse" in vf
    assert arg_after(args, "-loop") == "0"


def test_gif_frame_rate_is_capped() -> None:
    assert effective_fps("gif", 30) == 20
    assert effective_fps("gif", 10) == 10
    assert effective_fps("mp4", 30) == 30
    assert arg_after(build_command("ffmpeg", "gif", 64, 64, 30, "o.gif"), "-framerate") == "20"


def test_custom_crf_is_passed_through() -> None:
    assert arg_after(cmd("mp4", crf=28), "-crf") == "28"


@pytest.mark.parametrize(
    "fmt, crf, kw",
    [("mp4", 52, {}), ("mp4", -1, {}), ("webm", 64, {}), ("webm", 3, {"webm_codec": "vp8"})],
)
def test_out_of_range_crf_rejected(fmt: str, crf: int, kw: dict) -> None:
    with pytest.raises(ValueError, match="crf"):
        cmd(fmt, crf=crf, **kw)


@pytest.mark.parametrize("w, h", [(641, 360), (640, 361), (0, 10), (1, 1)])
def test_odd_or_tiny_frame_sizes_rejected(w: int, h: int) -> None:
    with pytest.raises(ValueError, match="even"):
        build_command("ffmpeg", "mp4", w, h, 10, "o.mp4")


def test_bad_fps_rejected() -> None:
    with pytest.raises(ValueError, match="fps"):
        build_command("ffmpeg", "mp4", 64, 64, 0, "o.mp4")


def test_infer_format_from_extension_and_override() -> None:
    assert infer_format("a/b/demo.MP4") == "mp4"
    assert infer_format("demo.webm") == "webm"
    assert infer_format("demo.gif") == "gif"
    assert infer_format("demo.bin", "webm") == "webm"
    assert infer_format("demo", ".gif") == "gif"


@pytest.mark.parametrize("name", ["demo", "demo.avi", "demo.mov"])
def test_infer_format_rejects_unknown(name: str) -> None:
    with pytest.raises(ValueError):
        infer_format(name)


def test_video_codec_names() -> None:
    assert video_codec("mp4") == "libx264"
    assert video_codec("webm") == "libvpx-vp9"
    assert video_codec("webm", "vp8") == "libvpx"
    with pytest.raises(ValueError):
        video_codec("webm", "av1")


def solid(w: int, h: int, shade: int) -> bytes:
    return bytes([shade, shade, shade]) * (w * h)


def encode(path, fmt: str, frames: int = 12, fps: int = 6, **kw) -> None:
    w, h = 64, 48
    with Encoder(path, fmt, w, h, fps, **kw) as enc:
        for i in range(frames):
            enc.write(solid(w, h, (i * 20) % 256))
        enc.finish()


@requires_ffmpeg
@pytest.mark.parametrize(
    "fmt, codec", [("mp4", "h264"), ("webm", "vp9"), ("gif", "gif")]
)
def test_real_encode_produces_a_playable_file(tmp_path, fmt: str, codec: str) -> None:
    out = tmp_path / f"clip.{fmt}"
    encode(out, fmt)
    info = probe(out)
    assert info.codec == codec
    assert (info.width, info.height) == (64, 48)
    assert info.duration == pytest.approx(2.0, abs=0.3)
    assert info.size_bytes > 0


@requires_ffmpeg
def test_real_vp8_encode(tmp_path) -> None:
    out = tmp_path / "clip.webm"
    encode(out, "webm", webm_codec="vp8")
    assert probe(out).codec == "vp8"


@requires_ffmpeg
def test_wrong_frame_length_is_rejected_before_ffmpeg(tmp_path) -> None:
    out = tmp_path / "x.mp4"
    with Encoder(out, "mp4", 64, 48, 6) as enc:
        with pytest.raises(ValueError, match="expected"):
            enc.write(b"too short")
        enc.abort()
    assert not out.exists()


@requires_ffmpeg
def test_no_output_file_until_finish_and_no_partial_left_behind(tmp_path) -> None:
    out = tmp_path / "x.mp4"
    enc = Encoder(out, "mp4", 64, 48, 6)
    enc.write(solid(64, 48, 10))
    assert not out.exists()
    enc.abort()
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_finishing_with_no_frames_is_an_error(tmp_path) -> None:
    out = tmp_path / "x.mp4"
    enc = Encoder(out, "mp4", 64, 48, 6)
    with pytest.raises(EncodeError):
        enc.finish()
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_missing_output_directory_is_a_clear_error(tmp_path) -> None:
    with pytest.raises(EncodeError, match="does not exist"):
        Encoder(tmp_path / "nope" / "x.mp4", "mp4", 64, 48, 6)


@requires_ffmpeg
def test_exception_inside_with_block_discards_the_partial_file(tmp_path) -> None:
    out = tmp_path / "x.webm"
    with pytest.raises(RuntimeError, match="boom"):
        with Encoder(out, "webm", 64, 48, 6) as enc:
            enc.write(solid(64, 48, 0))
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


@requires_ffmpeg
def test_overwrites_an_existing_file(tmp_path) -> None:
    out = tmp_path / "clip.mp4"
    out.write_bytes(b"old")
    encode(out, "mp4")
    assert probe(out).codec == "h264"
