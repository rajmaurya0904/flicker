# flicker

**Record a terminal command straight to an MP4, WebM or GIF, from one command line, for READMEs and bug reports.**

Putting a terminal demo in a README usually means an asciinema recording, a player to host, and a converter that never quite fits. flicker runs your command in a pseudo-terminal, draws the screen itself, and pipes the frames into ffmpeg. You end up with a small video file you can drop into an issue.

```console
$ flicker demo.mp4 --show-command --max-idle 0.3 --save-cast demo.cast -- python demo.py
PASS test_1
PASS test_2
PASS test_3
3 passed in 4.5s
saved recording to demo.cast
wrote demo.mp4
  mp4  752x488  20 fps  44 frames  2.2 s  7.8 KiB

$ flicker info demo.cast
demo.cast: asciicast recording
  terminal   80x24
  events     4
  duration   4.72 s
  command    python demo.py
  as video   116 frames, 5.8 s at 20 fps

$ flicker info demo.mp4
demo.mp4: video
  codec      h264
  size       752x488
  duration   2.20 s
  frames     44
  file size  7.8 KiB

$ flicker render demo.cast demo.webm --theme dracula --speed 2
wrote demo.webm
  webm  752x488  20 fps  69 frames  3.5 s  5.7 KiB
```

The run above took 4.7 seconds of real time. `--max-idle 0.3` cut the 1.5 second pauses between tests, so the video is 2.2 seconds long.

## Install

Not on PyPI yet, so install from a clone. It needs Python 3.11 or newer and `ffmpeg` and `ffprobe` on your PATH.

```bash
pip install -e .
flicker doctor    # confirms ffmpeg, the encoders and a monospaced font are found
```

## Usage

```bash
flicker demo.mp4 -- ls -l                       # run a command, write the video (mp4, webm or gif by extension)
flicker demo.gif --show-command -- make test    # draw "$ make test" above the output
flicker session.mp4                             # no command: records your shell until you exit it
flicker render demo.cast demo.webm --fps 30     # re-render a saved .cast (flicker's or asciinema's) with other settings
```

`flicker record --help` and `flicker render --help` list every option: `--cols/--rows`, `--theme` (dark, light, dracula, solarized), `--font`, `--font-size`, `--max-idle`, `--speed`, `--hold`, `--crf`, `--webm-codec`, `--no-cursor`, `--max-duration`. Writing to a `.cast` file skips ffmpeg entirely. The exit status is the recorded command's (0 or 1), 2 for bad usage, and 130 after Ctrl+C.

## How it works

- `capture` starts the command in a pseudo-terminal of a fixed size (the `pty` module on Linux and macOS, ConPTY through pywinpty on Windows) and timestamps each chunk of output.
- Recordings are stored as asciicast v2, and v2 and v3 files can be read, so a `.cast` from asciinema renders too.
- `screen` replays the output through pyte, a VT100 emulator, to get the grid of styled cells at each moment.
- `render` draws each grid with Pillow using a monospaced font found on the system, with 16 ANSI colours from the chosen theme, 256 and true colour, bold, italic, underline, a cursor, and hand-drawn box and block characters so lines join up.
- `timeline` samples that sequence at a fixed frame rate, after idle compression and speed changes have rewritten the timestamps.
- `encoder` pipes the raw frames to an ffmpeg subprocess (libx264, libvpx-vp9 or libvpx, or the GIF encoder). The output is written to a temporary file and moved into place when ffmpeg succeeds, so a failed run never leaves a half-written video.

## Limitations

- ffmpeg and ffprobe are required for video output. flicker never bundles them; `flicker doctor` tells you what is missing.
- It records what a command prints, not what you type, and not graphical windows. Full-screen programs such as vim or htop are redrawn through the emulator and look right in simple cases, but pyte does not implement every escape sequence. Unsupported ones are skipped and counted in the output.
- Interactive shell recording forwards the keyboard in raw mode. It needs a real terminal on standard input, so the automated tests do not cover it.
- On Windows without pywinpty the command runs over plain pipes, so programs that check for a terminal will not print colour.
- GIFs are capped at 20 fps and a 128-colour palette. Emoji and other wide glyphs depend on the font that is installed.
- The font is whichever well-known monospaced font flicker finds, or the one you pass with `--font`. If none is found it stops with an error.
- The terminal size is your current window, or 80x24 when output is redirected. Resizing during a recording is not tracked.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Tests that need ffmpeg or a font skip themselves when it is not installed.

## Licence

MIT, see [LICENSE](LICENSE).
