"""Tests for drawing terminal screens as images."""

import pytest
from PIL import ImageChops

from flicker.fonts import load_fonts
from flicker.render import Renderer, is_wide
from flicker.screen import Terminal
from flicker.theme import get_theme

from .conftest import requires_font

pytestmark = requires_font

DARK = get_theme("dark")


def make(cols: int = 20, rows: int = 5, *, cursor: bool = False, theme=DARK) -> Renderer:
    return Renderer(cols, rows, load_fonts(size=16), theme, padding=8, show_cursor=cursor)


def cell_pixels(r: Renderer, x: int, y: int):
    """All pixel colours inside one cell."""
    ox, oy = r._origin(x, y)
    crop = r.image.crop((ox, oy, ox + r.cell_w, oy + r.cell_h))
    return {color for _count, color in crop.getcolors(maxcolors=1_000_000)}


def test_image_size_covers_grid_plus_padding_and_is_even() -> None:
    r = make(20, 5)
    assert r.width >= 20 * r.cell_w + 16
    assert r.height >= 5 * r.cell_h + 16
    assert r.width % 2 == 0 and r.height % 2 == 0
    assert r.image.size == (r.width, r.height)


def test_blank_screen_is_solid_background() -> None:
    r = make()
    r.render(Terminal(20, 5))
    colors = r.image.getcolors(maxcolors=1_000_000)
    assert [c for _n, c in colors] == [DARK.background]


def test_text_draws_foreground_pixels() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("W")
    r.render(t)
    assert DARK.foreground in cell_pixels(r, 0, 0)
    assert cell_pixels(r, 1, 0) == {DARK.background}


def test_ansi_colour_uses_theme_palette() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("\x1b[31mW")
    r.render(t)
    assert DARK.ansi[1] in cell_pixels(r, 0, 0)


def test_background_colour_fills_the_whole_cell() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("\x1b[42m \x1b[0m")
    r.render(t)
    assert cell_pixels(r, 0, 0) == {DARK.ansi[2]}


def test_reverse_video_swaps_colours() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("\x1b[7m \x1b[0m")
    r.render(t)
    assert cell_pixels(r, 0, 0) == {DARK.foreground}


def test_truecolour_text() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("\x1b[38;2;255;128;0mW")
    r.render(t)
    assert (255, 128, 0) in cell_pixels(r, 0, 0)


def test_cursor_is_a_filled_block_when_shown() -> None:
    r = make(cursor=True)
    t = Terminal(20, 5)
    t.feed("ab")
    r.render(t)
    assert DARK.cursor in cell_pixels(r, 2, 0)


def test_hidden_cursor_is_not_drawn() -> None:
    r = make(cursor=True)
    t = Terminal(20, 5)
    t.feed("ab\x1b[?25l")
    r.render(t)
    assert DARK.cursor not in cell_pixels(r, 2, 0)


def test_cursor_can_be_turned_off() -> None:
    r = make(cursor=False)
    t = Terminal(20, 5)
    r.render(t)
    assert DARK.cursor not in cell_pixels(r, 0, 0)


def test_underline_adds_pixels_below_the_glyph() -> None:
    plain, under = make(), make()
    a, b = Terminal(20, 5), Terminal(20, 5)
    a.feed(" ")
    b.feed("\x1b[4m \x1b[0m")
    plain.render(a)
    under.render(b)
    assert cell_pixels(plain, 0, 0) == {DARK.background}
    assert DARK.foreground in cell_pixels(under, 0, 0)


def test_strikethrough_adds_pixels() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("\x1b[9m \x1b[0m")
    r.render(t)
    assert DARK.foreground in cell_pixels(r, 0, 0)


def test_bold_changes_the_rendering() -> None:
    a, b = make(), make()
    t1, t2 = Terminal(20, 5), Terminal(20, 5)
    t1.feed("H")
    t2.feed("\x1b[1mH")
    a.render(t1)
    b.render(t2)
    assert ImageChops.difference(a.image, b.image).getbbox() is not None


def test_partial_redraw_matches_full_redraw() -> None:
    inc, full = make(), make()
    t = Terminal(20, 5)
    inc.render(t)
    t.take_dirty_rows()
    t.feed("first line\r\nsecond")
    inc.draw_rows(t, t.take_dirty_rows())
    t.feed("\r\x1b[31mX")
    inc.draw_rows(t, t.take_dirty_rows())
    full.render(t)
    assert ImageChops.difference(inc.image, full.image).getbbox() is None


def test_full_block_fills_the_cell() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("█")
    r.render(t)
    assert cell_pixels(r, 0, 0) == {DARK.foreground}


def test_half_block_fills_only_the_top_half() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("▀")
    r.render(t)
    ox, oy = r._origin(0, 0)
    assert r.image.getpixel((ox + 2, oy + 1)) == DARK.foreground
    assert r.image.getpixel((ox + 2, oy + r.cell_h - 2)) == DARK.background


def test_box_lines_reach_the_cell_edges_so_they_join() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("│\r\n│")
    r.render(t)
    ox, oy = r._origin(0, 0)
    mid = ox + r.cell_w // 2
    assert r.image.getpixel((mid, oy)) == DARK.foreground  # top edge of the upper cell
    assert r.image.getpixel((mid, oy + r.cell_h - 1)) == DARK.foreground  # bottom edge
    _, oy2 = r._origin(0, 1)
    assert r.image.getpixel((mid, oy2)) == DARK.foreground  # continues in the cell below


def test_braille_dots_are_drawn_without_font_support() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("⣿")
    r.render(t)
    assert DARK.foreground in cell_pixels(r, 0, 0)


def test_shade_blocks_differ_in_brightness() -> None:
    r = make()
    t = Terminal(20, 5)
    t.feed("░▒▓")
    r.render(t)
    values = []
    for x in range(3):
        px = cell_pixels(r, x, 0)
        assert len(px) == 1
        values.append(sum(next(iter(px))))
    assert values[0] < values[1] < values[2]


def test_wide_character_spans_two_cells() -> None:
    assert is_wide("中") and not is_wide("a") and not is_wide("")
    r = make()
    t = Terminal(20, 5)
    t.feed("中")
    r.render(t)
    assert DARK.foreground in cell_pixels(r, 0, 0) | cell_pixels(r, 1, 0)


def test_frame_bytes_length_is_rgb24() -> None:
    r = make()
    r.render(Terminal(20, 5))
    assert len(r.frame_bytes()) == r.width * r.height * 3


@pytest.mark.parametrize("name", ["dark", "light", "dracula", "solarized"])
def test_every_theme_renders_its_own_background(name: str) -> None:
    theme = get_theme(name)
    r = make(theme=theme)
    r.render(Terminal(20, 5))
    assert r.image.getpixel((0, 0)) == theme.background
