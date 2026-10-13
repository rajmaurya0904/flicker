"""FFmpeg dependency checker."""

import shutil


def check_ffmpeg() -> bool:
    """Check if ffmpeg and ffprobe are available in PATH.

    Returns:
        True if both executables are found.

    Raises:
        RuntimeError: If either ffmpeg or ffprobe is missing.
    """
    missing = []
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            missing.append(cmd)
    if missing:
        raise RuntimeError(f"Missing executables: {', '.join(missing)}")
    return True