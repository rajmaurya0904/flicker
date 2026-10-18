"""Tests for the terminal emulator wrapper."""

import pytest

from flicker.cast import Event, Recording
from flicker.screen import Terminal, final_screen


def test_plain_text_and_newlines() -> None:
    t = Terminal(20, 5)
    t.feed("hello\r\nworld")
    assert t.lines()[:2] == ["hello", "world"]
    assert t.text() == "hello\nworld"


def test_colour_attributes_are_tracked() -> None:
    t = Terminal(20, 3)
    t.feed("\x1b[1;31mX\x1b[0mY")
    x, y = t.screen.buffer[0][0], t.screen.buffer[0][1]
    assert x.fg == "red" and x.bold
    assert y.fg == "default" and not y.bold


def test_truecolour_is_hex() -> None:
    t = Terminal(20, 3)
    t.feed("\x1b[38;2;10;20;30mZ")
    assert t.screen.buffer[0][0].fg == "0a141e"


def test_cursor_movement_overwrites_text() -> None:
    t = Terminal(20, 3)
    t.feed("abcdef\r\x1b[2CXY")
    assert t.lines()[0] == "abXYef"


def test_carriage_return_progress_line() -> None:
    t = Terminal(20, 3)
    for pct in (10, 50, 100):
        t.feed(f"\rprogress {pct}%   ")
    assert t.lines()[0] == "progress 100%"


def test_clear_screen_empties_everything() -> None:
    t = Terminal(20, 3)
    t.feed("junk\r\nmore")
    t.feed("\x1b[2J\x1b[H")
    assert t.text() == ""


def test_wrapping_at_the_right_edge() -> None:
    t = Terminal(5, 3)
    t.feed("abcdefgh")
    assert t.lines()[:2] == ["abcde", "fgh"]


def test_scrolling_drops_the_top_line() -> None:
    t = Terminal(10, 3)
    t.feed("1\r\n2\r\n3\r\n4")
    assert t.lines() == ["2", "3", "4"]


def test_wide_characters_take_two_cells() -> None:
    t = Terminal(10, 2)
    t.feed("中X")
    assert t.screen.buffer[0][0].data == "中"
    assert t.screen.buffer[0][2].data == "X"


def test_take_changes_reports_text_and_then_quiet() -> None:
    t = Terminal(10, 2)
    assert t.take_changes() is True  # first call always reports the initial state
    assert t.take_changes() is False
    t.feed("a")
    assert t.take_changes() is True
    assert t.take_changes() is False


def test_cursor_only_move_counts_as_a_change() -> None:
    t = Terminal(10, 3)
    t.feed("abc")
    t.take_changes()
    t.feed("\x1b[1;1H")
    assert t.take_changes() is True


def test_hiding_the_cursor_counts_as_a_change() -> None:
    t = Terminal(10, 3)
    t.take_changes()
    t.feed("\x1b[?25l")
    assert t.take_changes() is True
    assert t.screen.cursor.hidden


def test_title_and_unknown_sequences_do_not_break_rendering() -> None:
    t = Terminal(20, 3)
    t.feed("\x1b]0;a window title\x07ok\x1b[?2004h\x1b[?1049h more")
    assert t.lines()[0].startswith("ok")


def test_apply_resize_event() -> None:
    t = Terminal(10, 3)
    t.apply(Event(0.1, "r", "30x6"))
    assert (t.cols, t.rows) == (30, 6)


def test_apply_output_event() -> None:
    t = Terminal(10, 3)
    t.apply(Event(0.0, "o", "hi"))
    assert t.text() == "hi"


def test_final_screen_replays_all_events() -> None:
    rec = Recording(10, 3, [Event(0, "o", "one\r\n"), Event(1, "o", "two")])
    assert final_screen(rec).text() == "one\ntwo"


def test_invalid_size_rejected() -> None:
    with pytest.raises(ValueError):
        Terminal(0, 5)
