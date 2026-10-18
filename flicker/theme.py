"""Colour themes and conversion of terminal colour names to RGB."""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]

# pyte names the eight base colours with "brown" standing in for yellow.
_ANSI_ORDER = (
    "black",
    "red",
    "green",
    "brown",
    "blue",
    "magenta",
    "cyan",
    "white",
)
_ANSI_INDEX = {name: i for i, name in enumerate(_ANSI_ORDER)}
_ANSI_INDEX.update({"yellow": 3})


class ThemeError(ValueError):
    """Raised for an unknown theme name."""


def hex_to_rgb(value: str) -> RGB:
    """Parse ``rrggbb`` or ``#rrggbb``."""
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a 6-digit hex colour: {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


@dataclass(frozen=True)
class Theme:
    """Background, foreground, cursor and the 16 ANSI colours."""

    name: str
    background: RGB
    foreground: RGB
    cursor: RGB
    ansi: tuple[RGB, ...]  # 16 entries: 8 normal then 8 bright

    def color(self, name: str, *, background: bool) -> RGB:
        """Resolve a pyte colour (``default``, a name, or ``rrggbb``) to RGB."""
        if name == "default":
            return self.background if background else self.foreground
        if name in _ANSI_INDEX:
            return self.ansi[_ANSI_INDEX[name]]
        if name.startswith("bright") and name[6:] in _ANSI_INDEX:
            return self.ansi[8 + _ANSI_INDEX[name[6:]]]
        try:
            return hex_to_rgb(name)
        except ValueError:
            return self.background if background else self.foreground


def _theme(name: str, bg: str, fg: str, cursor: str, ansi: str) -> Theme:
    colours = tuple(hex_to_rgb(c) for c in ansi.split())
    assert len(colours) == 16, name
    return Theme(name, hex_to_rgb(bg), hex_to_rgb(fg), hex_to_rgb(cursor), colours)


THEMES: dict[str, Theme] = {
    t.name: t
    for t in (
        _theme(
            "dark", "21252b", "abb2bf", "528bff",
            "282c34 e06c75 98c379 e5c07b 61afef c678dd 56b6c2 abb2bf "
            "5c6370 e06c75 98c379 e5c07b 61afef c678dd 56b6c2 ffffff",
        ),
        _theme(
            "light", "fafafa", "383a42", "526fff",
            "383a42 e45649 50a14f c18401 4078f2 a626a4 0184bc a0a1a7 "
            "4f525e e06c75 98c379 e5c07b 61afef c678dd 56b6c2 ffffff",
        ),
        _theme(
            "dracula", "282a36", "f8f8f2", "f8f8f2",
            "21222c ff5555 50fa7b f1fa8c bd93f9 ff79c6 8be9fd f8f8f2 "
            "6272a4 ff6e6e 69ff94 ffffa5 d6acff ff92df a4ffff ffffff",
        ),
        _theme(
            "solarized", "002b36", "839496", "93a1a1",
            "073642 dc322f 859900 b58900 268bd2 d33682 2aa198 eee8d5 "
            "002b36 cb4b16 586e75 657b83 839496 6c71c4 93a1a1 fdf6e3",
        ),
    )
}


def get_theme(name: str) -> Theme:
    """Look a theme up by name."""
    try:
        return THEMES[name.lower()]
    except KeyError:
        raise ThemeError(f"unknown theme {name!r} (choose from: {', '.join(THEMES)})") from None
