"""Command-line interface: ``flicker record``, ``render``, ``info`` and ``doctor``."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__
from .capture import capture, default_shell, format_command
from .cast import CastError, Recording
from .cast import read as read_cast
from .cast import write as write_cast
from .core import RenderOptions, RenderResult, plan, render_recording, with_command_line
from .encoder import FORMATS, WEBM_CODECS, EncodeError, infer_format
from .ffmpeg import FFmpegError, check_ffmpeg, has_encoder, probe, version
from .fonts import FontError, load_fonts
from .pty import PtyError
from .theme import THEMES, ThemeError, get_theme

COMMANDS = ("record", "render", "info", "doctor")
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


class CliError(Exception):
    """A usage problem to report on one line, without a traceback."""


def _add_render_options(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("video options")
    g.add_argument("--format", choices=FORMATS, help="container (default: from the file name)")
    g.add_argument("--fps", type=int, default=20, help="frames per second (default 20)")
    g.add_argument("--theme", default="dark", help=f"one of {', '.join(THEMES)} (default dark)")
    g.add_argument("--font", metavar="FILE", help="monospaced .ttf/.otf/.ttc file")
    g.add_argument("--font-size", type=int, default=16, help="pixels (default 16)")
    g.add_argument("--padding", type=int, default=16, help="border in pixels (default 16)")
    g.add_argument("--no-cursor", action="store_true", help="do not draw the cursor")
    g.add_argument(
        "--max-idle", type=float, metavar="SECONDS", help="shorten every pause longer than this"
    )
    g.add_argument("--speed", type=float, default=1.0, help="playback speed (default 1.0)")
    g.add_argument(
        "--hold", type=float, default=1.0, help="seconds to hold the last frame (default 1)"
    )
    g.add_argument("--crf", type=int, help="constant quality, lower is better (mp4/webm)")
    g.add_argument("--webm-codec", choices=WEBM_CODECS, default="vp9", help="default vp9")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flicker",
        description="Record a terminal session straight to an MP4, WebM or GIF.",
        epilog="Shortcut: 'flicker demo.mp4 -- ls -l' is the same as 'flicker record ...'.",
    )
    parser.add_argument("--version", action="version", version=f"flicker {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    rec = sub.add_parser(
        "record",
        help="run a command (or a shell) and write the video",
        usage="flicker record [options] output [-- COMMAND [ARGS...]]",
        description="Run COMMAND in a pseudo-terminal and encode what it prints. "
        "Without COMMAND your shell starts and you type into it; exit it to stop.",
    )
    rec.add_argument("output", help="video file (.mp4, .webm, .gif) or a .cast file")
    rec.add_argument("--cols", type=int, help="terminal width (default: your terminal or 80)")
    rec.add_argument("--rows", type=int, help="terminal height (default: your terminal or 24)")
    rec.add_argument("--save-cast", metavar="FILE", help="also keep the recording as .cast")
    rec.add_argument("--max-duration", type=float, metavar="SECONDS", help="stop after this long")
    rec.add_argument(
        "--show-command", action="store_true", help="draw '$ COMMAND' above the output"
    )
    rec.add_argument("--quiet", "-q", action="store_true", help="do not mirror the session")
    _add_render_options(rec)

    ren = sub.add_parser("render", help="turn an asciicast (.cast) file into a video")
    ren.add_argument("input", help="asciicast v2 or v3 file")
    ren.add_argument("output", help="video file (.mp4, .webm, .gif)")
    ren.add_argument("--quiet", "-q", action="store_true", help="no progress output")
    _add_render_options(ren)

    info = sub.add_parser("info", help="describe a .cast recording or a finished video")
    info.add_argument("file")

    sub.add_parser("doctor", help="check ffmpeg, encoders and fonts")
    return parser


def _options(args: argparse.Namespace) -> RenderOptions:
    opts = RenderOptions(
        fmt=args.format,
        fps=args.fps,
        theme=args.theme,
        font=args.font,
        font_size=args.font_size,
        padding=args.padding,
        cursor=not args.no_cursor,
        max_idle=args.max_idle,
        speed=args.speed,
        hold=args.hold,
        crf=args.crf,
        webm_codec=args.webm_codec,
    )
    try:
        opts.validate()
        get_theme(opts.theme)
    except (ValueError, ThemeError) as exc:
        raise CliError(str(exc)) from None
    return opts


def _progress(quiet: bool) -> Callable[[int, int], None] | None:
    if quiet or not sys.stderr.isatty():
        return None

    def show(done: int, total: int) -> None:
        pct = 100 * done // total if total else 100
        sys.stderr.write(f"\rencoding {done}/{total} frames ({pct}%)")
        if done >= total:
            sys.stderr.write("\r" + " " * 40 + "\r")
        sys.stderr.flush()

    return show


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 * 1024):.1f} MiB"


def _report(result: RenderResult) -> None:
    print(f"wrote {result.output}")
    print(
        f"  {result.fmt}  {result.width}x{result.height}  {result.fps} fps  "
        f"{result.frames} frames  {result.seconds:.1f} s  {_format_bytes(result.size_bytes)}"
    )
    if result.skipped_events:
        print(f"  note: {result.skipped_events} unsupported terminal sequences were ignored")


def _check_output_dir(output: str) -> None:
    parent = Path(output).resolve().parent
    if not parent.is_dir():
        raise CliError(f"output directory does not exist: {parent}")


def _terminal_size(args: argparse.Namespace) -> tuple[int, int]:
    size = shutil.get_terminal_size((80, 24))
    live = sys.stdout.isatty()
    cols = args.cols or (size.columns if live else 80)
    rows = args.rows or (size.lines if live else 24)
    if not (10 <= cols <= 500 and 2 <= rows <= 200):
        raise CliError(f"unreasonable terminal size {cols}x{rows} (cols 10-500, rows 2-200)")
    return cols, rows


def _echo(text: str) -> None:
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except (UnicodeEncodeError, OSError):
        pass  # mirroring is a convenience; the recording itself is unaffected


def _exit_status(interrupted: bool, code: int | None) -> int:
    if interrupted:
        return EXIT_INTERRUPTED
    return 0 if code in (0, None) else EXIT_FAILED


def cmd_record(args: argparse.Namespace) -> int:
    cmd = list(args.cmd)
    cast_only = Path(args.output).suffix.lower() == ".cast"
    if not cast_only:
        infer_format(args.output, args.format)  # fail early on a bad extension
    opts = _options(args)
    _check_output_dir(args.output)
    if args.save_cast:
        _check_output_dir(args.save_cast)
    if not cast_only:
        check_ffmpeg()  # before recording, so a missing ffmpeg never costs a session
    cols, rows = _terminal_size(args)

    interactive = not cmd
    if interactive:
        if not sys.stdin.isatty():
            raise CliError("no command given and standard input is not a terminal; use -- CMD")
        cmd = default_shell()
        print(f"recording {format_command(cmd)}; exit the shell to finish", file=sys.stderr)

    result = capture(
        cmd,
        cols,
        rows,
        echo=None if args.quiet else _echo,
        interactive=interactive,
        max_duration=args.max_duration,
    )
    rec = result.recording
    if not args.quiet and not rec.output_text().endswith("\n"):
        print()
    if result.interrupted:
        print("interrupted; keeping what was recorded so far", file=sys.stderr)
    if result.timed_out:
        print(f"stopped after --max-duration {args.max_duration:g} s", file=sys.stderr)
    if not rec.events:
        raise CliError("the command printed nothing, so there is nothing to record")

    if args.save_cast:
        write_cast(args.save_cast, rec)
        print(f"saved recording to {args.save_cast}", file=sys.stderr)
    status = _exit_status(result.interrupted, result.exit_code)
    if cast_only:
        write_cast(args.output, rec)
        print(f"wrote {args.output} ({len(rec.events)} events, {rec.duration:.1f} s)")
        return status

    if args.show_command and not interactive:
        rec = with_command_line(rec, format_command(cmd))
    _report(render_recording(rec, args.output, opts, _progress(args.quiet)))
    return status


def cmd_render(args: argparse.Namespace) -> int:
    infer_format(args.output, args.format)
    opts = _options(args)
    _check_output_dir(args.output)
    rec = read_cast(args.input)
    if not rec.events:
        raise CliError(f"{args.input} has no output events")
    check_ffmpeg()
    _report(render_recording(rec, args.output, opts, _progress(args.quiet)))
    return 0


def _describe_cast(rec: Recording, path: str, opts: RenderOptions) -> None:
    frames, seconds = plan(rec, opts)
    print(f"{path}: asciicast recording")
    print(f"  terminal   {rec.cols}x{rec.rows}")
    print(f"  events     {len(rec.events)}")
    print(f"  duration   {rec.duration:.2f} s")
    if rec.command:
        print(f"  command    {rec.command}")
    if rec.title:
        print(f"  title      {rec.title}")
    print(f"  as video   {frames} frames, {seconds:.1f} s at {opts.fps} fps")


def cmd_info(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise CliError(f"no such file: {path}")
    if path.suffix.lower() == ".cast":
        _describe_cast(read_cast(path), str(path), RenderOptions())
        return 0
    check_ffmpeg()
    info = probe(path)
    print(f"{path}: video")
    print(f"  codec      {info.codec}")
    print(f"  size       {info.width}x{info.height}")
    print(f"  duration   {info.duration:.2f} s")
    if info.frames is not None:
        print(f"  frames     {info.frames}")
    print(f"  file size  {_format_bytes(info.size_bytes)}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    ok = True
    try:
        check_ffmpeg()
        print(f"ffmpeg     ok       {version()}")
        for name, label, needed in (
            ("libx264", "mp4", True),
            ("libvpx-vp9", "webm", False),
            ("gif", "gif", False),
        ):
            found = has_encoder(name)
            ok = ok and (found or not needed)
            print(f"{label:<10} {'ok' if found else 'missing':<8} encoder {name}")
    except FFmpegError as exc:
        ok = False
        print(f"ffmpeg     missing  {exc}")
    try:
        print(f"font       ok       {load_fonts().path}")
    except FontError as exc:
        ok = False
        print(f"font       missing  {exc}")
    return 0 if ok else EXIT_FAILED


HANDLERS = {"record": cmd_record, "render": cmd_render, "info": cmd_info, "doctor": cmd_doctor}


def _normalise(argv: list[str]) -> list[str]:
    """Allow ``flicker out.mp4 -- cmd`` as shorthand for ``flicker record out.mp4 -- cmd``."""
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        return ["record", *argv]
    return argv


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``flicker`` command."""
    parser = build_parser()
    tokens = _normalise(list(sys.argv[1:] if argv is None else argv))
    command: list[str] = []
    if "--" in tokens:
        cut = tokens.index("--")
        tokens, command = tokens[:cut], tokens[cut + 1 :]
    args = parser.parse_args(tokens)
    args.cmd = command
    if command and args.command != "record":
        parser.error("a command after -- only makes sense with 'record'")
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return HANDLERS[args.command](args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except (CastError, FFmpegError, EncodeError, FontError, PtyError) as exc:
        print(f"flicker: error: {exc}", file=sys.stderr)
        return EXIT_FAILED  # checked first: CastError is also a ValueError
    except (CliError, ValueError) as exc:
        print(f"flicker: error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
