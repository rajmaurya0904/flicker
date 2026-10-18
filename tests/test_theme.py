"""Tests for colour resolution and theme lookup."""

import pytest

from flicker.theme import THEMES, ThemeError, get_theme, hex_to_rgb


def test_hex_parsing_with_and_without_hash() -> None:
    assert hex_to_rgb("ff8000") == (255, 128, 0)
    assert hex_to_rgb("#0a141e") == (10, 20, 30)


@pytest.mark.parametrize("bad", ["fff", "gggggg", "", "12345"])
def test_bad_hex_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        hex_to_rgb(bad)


def test_every_theme_has_sixteen_colours() -> None:
    assert set(THEMES) >= {"dark", "light", "dracula", "solarized"}
    for theme in THEMES.values():
        assert len(theme.ansi) == 16


def test_default_colours_follow_the_theme() -> None:
    t = get_theme("dark")
    assert t.color("default", background=True) == t.background
    assert t.color("default", background=False) == t.foreground


def test_named_colours_map_to_the_palette() -> None:
    t = get_theme("dracula")
    assert t.color("red", background=False) == t.ansi[1]
    assert t.color("brown", background=False) == t.ansi[3]  # pyte's name for yellow
    assert t.color("brightgreen", background=False) == t.ansi[10]
    assert t.color("brightbrown", background=True) == t.ansi[11]


def test_hex_colours_pass_through() -> None:
    assert get_theme("dark").color("ff00d7", background=False) == (255, 0, 215)


def test_unknown_colour_falls_back_to_defaults() -> None:
    t = get_theme("light")
    assert t.color("chartreuse-ish", background=False) == t.foreground
    assert t.color("chartreuse-ish", background=True) == t.background


def test_theme_lookup_is_case_insensitive() -> None:
    assert get_theme("DRACULA").name == "dracula"


def test_unknown_theme_lists_choices() -> None:
    with pytest.raises(ThemeError, match="dark"):
        get_theme("neon")


def test_light_and_dark_backgrounds_differ_in_brightness() -> None:
    assert sum(get_theme("light").background) > sum(get_theme("dark").background)
