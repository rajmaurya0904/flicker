"""Locate and load a monospaced font for drawing terminal cells."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

# (regular, bold, italic, bold italic) file names of well-known monospaced families.
_FAMILIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "CascadiaMono.ttf",
        "CascadiaMono-Bold.ttf",
        "CascadiaMono-Italic.ttf",
        "CascadiaMono-BoldItalic.ttf",
    ),
    ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
    (
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Bold.ttf",
        "DejaVuSansMono-Oblique.ttf",
        "DejaVuSansMono-BoldOblique.ttf",
    ),
    (
        "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf",
        "LiberationMono-Italic.ttf",
        "LiberationMono-BoldItalic.ttf",
    ),
    ("NotoSansMono-Regular.ttf", "NotoSansMono-Bold.ttf", "", ""),
    ("UbuntuMono-R.ttf", "UbuntuMono-B.ttf", "UbuntuMono-RI.ttf", "UbuntuMono-BI.ttf"),
    ("lucon.ttf", "", "", ""),
    ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    ("Menlo.ttc", "", "", ""),
    ("Monaco.ttf", "", "", ""),
    (
        "Courier New.ttf",
        "Courier New Bold.ttf",
        "Courier New Italic.ttf",
        "Courier New Bold Italic.ttf",
    ),
)


class FontError(RuntimeError):
    """Raised when no usable monospaced font can be found."""


@dataclass
class FontSet:
    """Four faces of one font plus the cell geometry derived from it."""

    regular: ImageFont.FreeTypeFont
    bold: ImageFont.FreeTypeFont | None
    italic: ImageFont.FreeTypeFont | None
    bold_italic: ImageFont.FreeTypeFont | None
    cell_width: int
    cell_height: int
    ascent: int
    path: str

    def face(self, bold: bool, italic: bool) -> ImageFont.FreeTypeFont:
        """Best available face for the style, falling back to regular."""
        if bold and italic and self.bold_italic is not None:
            return self.bold_italic
        if bold and self.bold is not None:
            return self.bold
        if italic and self.italic is not None:
            return self.italic
        return self.regular

    def has_real_bold(self) -> bool:
        return self.bold is not None


def _font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ]
    else:
        dirs += [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/usr/share/fonts/truetype/liberation2"),
            Path("/usr/share/fonts/truetype/noto"),
            Path("/usr/share/fonts/truetype/ubuntu"),
            Path("/usr/share/fonts/dejavu"),
            Path("/usr/share/fonts/TTF"),
            Path("/usr/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
        ]
    return dirs


def _find_file(name: str, dirs: list[Path], deep: bool) -> Path | None:
    if not name:
        return None
    for d in dirs:
        candidate = d / name
        if candidate.is_file():
            return candidate
    if deep:
        for d in dirs:
            if d.is_dir():
                for hit in d.rglob(name):
                    return hit
    return None


def _load(path: Path | None, size: int, index: int = 0) -> ImageFont.FreeTypeFont | None:
    if path is None:
        return None
    try:
        return ImageFont.truetype(str(path), size, index=index)
    except OSError:
        return None


def _build(
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont | None,
    italic: ImageFont.FreeTypeFont | None,
    bold_italic: ImageFont.FreeTypeFont | None,
    size: int,
    path: str,
) -> FontSet:
    ascent, descent = regular.getmetrics()
    width = max(1, round(regular.getlength("M")))
    height = ascent + descent + max(1, round(size * 0.15))
    return FontSet(regular, bold, italic, bold_italic, width, height, ascent, path)


def load_fonts(path: str | os.PathLike[str] | None = None, size: int = 16) -> FontSet:
    """Load a monospaced font.

    ``path`` (or the ``FLICKER_FONT`` environment variable) selects a specific font file.
    Otherwise the first well-known monospaced family found on the system is used.
    """
    if size < 4:
        raise FontError(f"font size too small: {size}")
    explicit = path or os.environ.get("FLICKER_FONT")
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FontError(f"font file not found: {p}")
        regular = _load(p, size)
        if regular is None:
            raise FontError(f"cannot load {p} as a font")
        return _build(regular, None, None, None, size, str(p))

    dirs = _font_dirs()
    for deep in (False, True):
        for family in _FAMILIES:
            found = _find_file(family[0], dirs, deep)
            if found is None:
                continue
            index = 0
            regular = _load(found, size, index)
            if regular is None:
                continue
            faces = []
            for i, name in enumerate(family[1:], start=1):
                if found.suffix == ".ttc":
                    faces.append(_load(found, size, i))
                else:
                    faces.append(_load(_find_file(name, [found.parent], False), size))
            return _build(regular, faces[0], faces[1], faces[2], size, str(found))
    raise FontError(
        "no monospaced font found; install one (for example DejaVu Sans Mono) "
        "or pass --font /path/to/font.ttf"
    )
