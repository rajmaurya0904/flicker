"""Smoke test: package imports cleanly. Replace/extend as modules land."""

import flicker


def test_version_is_set() -> None:
    assert flicker.__version__
