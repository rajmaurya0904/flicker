# Flicker

**A zero-config CLI tool that records terminal sessions directly to highly optimized MP4 or WebM screencasts for documentation and bug reports, without requiring heavy screen recording software.**

Recording a terminal tutorial often means firing up bulky screen recorders, wrestling with settings, and ending up with gigantic files. Flicker removes that overhead: it captures your terminal directly to a compact video, using only what's already on your system.

## Example

<!-- A real command and its REAL pasted output. Run it first. -->

## Install

```bash
pip install -e ".[dev]"
```

## Usage

<!-- The 2-4 commands people actually need, one line each. -->

## How it works

<!-- 3-6 bullets: what it checks, computes or produces. -->

## Limitations

- Requires `ffmpeg` and `ffprobe` executables to be installed and available in your PATH.
- Currently only works on Unix-like systems (Linux, macOS) due to reliance on PTY.
- Captures at a fixed interval (default 0.1 seconds), which may miss very rapid changes.
- Output video may have limited color fidelity depending on terminal emulator and ffmpeg settings.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

MIT -- see [LICENSE](LICENSE).
