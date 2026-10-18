"""Tests for monospaced font discovery."""

import pytest

from flicker.fonts import FontError, load_fonts

from .conftest import requires_font


@requires_font
def test_finds_a_system_font_with_sane_geometry(no_font_env) -> None:
    fonts = load_fonts(size=16)
    assert fonts.cell_width >= 5
    assert fonts.cell_height > fonts.cell_width
    assert fonts.ascent > 0
    assert fonts.path


@requires_font
def test_cell_size_grows_with_font_size(no_font_env) -> None:
    small, large = load_fonts(size=12), load_fonts(size=24)
    assert large.cell_width > small.cell_width
    assert large.cell_height > small.cell_height


@requires_font
def test_face_falls_back_to_regular(no_font_env) -> None:
    fonts = load_fonts(size=14)
    fonts.bold = fonts.italic = fonts.bold_italic = None
    assert fonts.face(True, True) is fonts.regular
    assert not fonts.has_real_bold()


@requires_font
def test_explicit_font_path_is_used(no_font_env) -> None:
    base = load_fonts(size=14)
    explicit = load_fonts(base.path, size=14)
    assert explicit.path == base.path
    assert explicit.bold is None  # an explicit file has no sibling faces


@requires_font
def test_environment_variable_selects_font(monkeypatch) -> None:
    base = load_fonts(size=14)
    monkeypatch.setenv("FLICKER_FONT", base.path)
    assert load_fonts(size=14).path == base.path


def test_missing_font_file_is_a_clear_error(tmp_path) -> None:
    with pytest.raises(FontError, match="not found"):
        load_fonts(tmp_path / "nope.ttf")


def test_non_font_file_is_rejected(tmp_path) -> None:
    junk = tmp_path / "junk.ttf"
    junk.write_text("this is not a font")
    with pytest.raises(FontError, match="cannot load"):
        load_fonts(junk)


def test_tiny_size_is_rejected() -> None:
    with pytest.raises(FontError, match="too small"):
        load_fonts(size=2)
