"""Tests for the flicker command line, run through main() with real files."""

import sys

import pytest

from flicker import __version__, cast
from flicker.cast import Event, Recording
from flicker.cli import _normalise, build_parser, main

from .conftest import requires_ffmpeg, requires_font

PY = sys.executable
HELLO = ["--", PY, "-c", "print('hello from flicker')"]


def make_cast(path, text="hello\r\n"):
    rec = Recording(cols=40, rows=6, events=[Event(0.0, "o", text), Event(0.5, "o", "bye\r\n")])
    cast.write(path, rec)
    return path


def test_no_arguments_prints_help(capsys) -> None:
    assert main([]) == 0
    assert "usage: flicker" in capsys.readouterr().out


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("sub", ["record", "render", "info", "doctor"])
def test_every_subcommand_has_help(sub, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main([sub, "--help"])
    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_normalise_inserts_record() -> None:
    assert _normalise(["a.mp4", "--", "ls"]) == ["record", "a.mp4", "--", "ls"]


def test_normalise_leaves_subcommands_and_options() -> None:
    assert _normalise(["render", "a.cast", "a.mp4"]) == ["render", "a.cast", "a.mp4"]
    assert _normalise(["--version"]) == ["--version"]
    assert _normalise([]) == []


def test_parser_collects_video_options() -> None:
    args = build_parser().parse_args(
        ["render", "a.cast", "a.webm", "--fps", "30", "--theme", "light", "--max-idle", "0.5"]
    )
    assert (args.fps, args.theme, args.max_idle, args.webm_codec) == (30, "light", 0.5, "vp9")


def test_command_after_dashes_needs_record(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["info", "x.cast", "--", "ls"])
    assert exc.value.code == 2


def test_record_to_cast_file(tmp_path, capsys) -> None:
    out = tmp_path / "run.cast"
    assert main(["record", str(out), "--quiet", "--cols", "50", "--rows", "8", *HELLO]) == 0
    rec = cast.read(out)
    assert (rec.cols, rec.rows) == (50, 8)
    assert "hello from flicker" in rec.output_text()
    assert str(out) in capsys.readouterr().out


def test_record_mirrors_output(tmp_path, capsys) -> None:
    main(["record", str(tmp_path / "a.cast"), *HELLO])
    assert "hello from flicker" in capsys.readouterr().out


def test_record_passes_through_exit_status(tmp_path) -> None:
    script = "print('x'); raise SystemExit(3)"
    assert main(["record", str(tmp_path / "a.cast"), "-q", "--", PY, "-c", script]) == 1


def test_record_save_cast_alongside_cast_output(tmp_path) -> None:
    save = tmp_path / "kept.cast"
    assert main(["record", str(tmp_path / "a.cast"), "-q", "--save-cast", str(save), *HELLO]) == 0
    assert save.is_file()


def test_record_unknown_command(tmp_path, capsys) -> None:
    assert main(["record", str(tmp_path / "a.cast"), "--", "no-such-command-zz"]) == 1
    assert "command not found" in capsys.readouterr().err


def test_record_silent_command_is_an_error(tmp_path, capsys) -> None:
    code = main(["record", str(tmp_path / "a.cast"), "-q", "--", PY, "-c", "pass"])
    assert code == 2
    assert "nothing to record" in capsys.readouterr().err


def test_record_rejects_bad_size(tmp_path, capsys) -> None:
    assert main(["record", str(tmp_path / "a.cast"), "--cols", "3", *HELLO]) == 2
    assert "unreasonable terminal size" in capsys.readouterr().err


def test_record_rejects_missing_output_directory(tmp_path, capsys) -> None:
    assert main(["record", str(tmp_path / "nope" / "a.cast"), *HELLO]) == 2
    assert "output directory does not exist" in capsys.readouterr().err


def test_unknown_extension_is_rejected_before_recording(tmp_path, capsys) -> None:
    assert main(["record", str(tmp_path / "a.xyz"), *HELLO]) == 2
    assert "unsupported format" in capsys.readouterr().err


def test_bad_option_values_are_usage_errors(tmp_path, capsys) -> None:
    src = make_cast(tmp_path / "a.cast")
    assert main(["render", str(src), str(tmp_path / "a.mp4"), "--fps", "0"]) == 2
    assert main(["render", str(src), str(tmp_path / "a.mp4"), "--theme", "neon"]) == 2
    assert main(["render", str(src), str(tmp_path / "a.mp4"), "--speed", "-1"]) == 2
    assert "unknown theme" in capsys.readouterr().err


def test_render_missing_input(tmp_path, capsys) -> None:
    assert main(["render", str(tmp_path / "gone.cast"), str(tmp_path / "a.mp4")]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_render_corrupt_cast(tmp_path, capsys) -> None:
    bad = tmp_path / "bad.cast"
    bad.write_text("not json\n", encoding="utf-8")
    code = main(["render", str(bad), str(tmp_path / "a.mp4")])
    assert code == 1


def test_info_describes_a_cast(tmp_path, capsys) -> None:
    src = make_cast(tmp_path / "a.cast")
    assert main(["info", str(src)]) == 0
    out = capsys.readouterr().out
    assert "40x6" in out and "events     2" in out and "0.50 s" in out


def test_info_missing_file(tmp_path, capsys) -> None:
    assert main(["info", str(tmp_path / "gone.mp4")]) == 2
    assert "no such file" in capsys.readouterr().err


@requires_ffmpeg
@requires_font
def test_render_mp4_end_to_end(tmp_path, capsys) -> None:
    src = make_cast(tmp_path / "a.cast")
    out = tmp_path / "a.mp4"
    assert main(["render", str(src), str(out), "--fps", "10", "--hold", "0.5"]) == 0
    assert out.stat().st_size > 0
    assert "mp4" in capsys.readouterr().out
    assert main(["info", str(out)]) == 0
    assert "h264" in capsys.readouterr().out


@requires_ffmpeg
@requires_font
def test_record_straight_to_webm(tmp_path, capsys) -> None:
    out = tmp_path / "a.webm"
    assert main([str(out), "-q", "--fps", "10", "--show-command", *HELLO]) == 0
    assert out.stat().st_size > 0


@requires_ffmpeg
@requires_font
def test_doctor_reports_ffmpeg(capsys) -> None:
    assert main(["doctor"]) == 0
    assert "libx264" in capsys.readouterr().out


def test_missing_ffmpeg_stops_before_recording(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    marker = tmp_path / "ran.txt"
    script = f"open({str(marker)!r}, 'w').write('x')"
    code = main([str(tmp_path / "a.mp4"), "--", PY, "-c", script])
    assert code == 1
    assert "Missing executables" in capsys.readouterr().err
    assert not marker.exists()


def test_missing_ffmpeg_on_render(tmp_path, monkeypatch, capsys) -> None:
    src = make_cast(tmp_path / "a.cast")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert main(["render", str(src), str(tmp_path / "a.mp4")]) == 1
    assert "ffmpeg" in capsys.readouterr().err


def test_doctor_without_ffmpeg_fails(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert main(["doctor"]) == 1
    assert "missing" in capsys.readouterr().out
