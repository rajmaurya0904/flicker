"""Tests for the flicker CLI entry point."""

from flicker.cli import main


def test_main_returns_zero() -> None:
    assert main([]) == 0


def test_main_prints_banner(capsys) -> None:
    main([])
    out = capsys.readouterr().out
    assert "Flicker" in out