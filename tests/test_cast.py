"""Tests for the asciicast reader and writer."""

import json

import pytest

from flicker import cast
from flicker.cast import CastError, Event, Recording


def sample() -> Recording:
    return Recording(
        cols=80,
        rows=24,
        events=[Event(0.0, "o", "hi\r\n"), Event(0.5, "o", "café ✓"), Event(1.25, "r", "100x30")],
        command="echo hi",
        title="demo",
        timestamp=1700000000,
        env={"TERM": "xterm-256color"},
    )


def test_roundtrip_preserves_everything() -> None:
    rec = sample()
    back = cast.loads(cast.dumps(rec))
    assert back.cols == 80 and back.rows == 24
    assert back.events == rec.events
    assert back.command == "echo hi"
    assert back.title == "demo"
    assert back.timestamp == 1700000000
    assert back.env == {"TERM": "xterm-256color"}


def test_header_is_asciicast_v2() -> None:
    first = cast.dumps(sample()).splitlines()[0]
    header = json.loads(first)
    assert header["version"] == 2
    assert header["width"] == 80
    assert header["height"] == 24


def test_event_lines_are_json_triples() -> None:
    lines = cast.dumps(sample()).splitlines()
    assert json.loads(lines[1]) == [0.0, "o", "hi\r\n"]
    assert len(lines) == 4


def test_file_roundtrip(tmp_path) -> None:
    path = tmp_path / "x.cast"
    cast.write(path, sample())
    assert cast.read(path).events == sample().events
    assert path.read_bytes().count(b"\r\n") == 0  # \r only appears escaped inside JSON strings


def test_duration_and_output_text() -> None:
    rec = sample()
    assert rec.duration == 1.25
    assert rec.output_text() == "hi\r\ncafé ✓"
    assert Recording(cols=10, rows=5).duration == 0.0


def test_resize_event_parses() -> None:
    assert Event(0, "r", "100x30").resize() == (100, 30)
    with pytest.raises(CastError):
        Event(0, "r", "wide").resize()


def test_reads_v3_relative_times() -> None:
    text = "\n".join(
        [
            json.dumps({"version": 3, "term": {"cols": 90, "rows": 20}}),
            json.dumps([0.5, "o", "a"]),
            json.dumps([0.25, "o", "b"]),
            json.dumps([1.0, "x", "0"]),
        ]
    )
    rec = cast.loads(text)
    assert (rec.cols, rec.rows) == (90, 20)
    assert [e.time for e in rec.events] == [0.5, 0.75]


def test_input_and_marker_events_are_ignored() -> None:
    text = "\n".join(
        [
            json.dumps({"version": 2, "width": 10, "height": 5}),
            json.dumps([0.1, "i", "ls\n"]),
            json.dumps([0.2, "m", "chapter"]),
            json.dumps([0.3, "o", "out"]),
        ]
    )
    assert [e.data for e in cast.loads(text).events] == ["out"]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "empty"),
        ("not json", "JSON header"),
        ("[1, 2]", "JSON object"),
        (json.dumps({"version": 1, "width": 1, "height": 1}), "unsupported"),
        (json.dumps({"version": 2, "width": 0, "height": 5}), "invalid terminal size"),
        (json.dumps({"version": 2, "width": "80", "height": 5}), "invalid terminal size"),
        (json.dumps({"version": 3}), "term"),
    ],
)
def test_bad_headers_raise(text: str, fragment: str) -> None:
    with pytest.raises(CastError, match=fragment):
        cast.loads(text)


@pytest.mark.parametrize(
    "event",
    ['{"a": 1}', "[1, \"o\"]", '[-1, "o", "x"]', '["1", "o", "x"]', '[1, "o", 5]', "oops"],
)
def test_bad_events_raise(event: str) -> None:
    header = json.dumps({"version": 2, "width": 10, "height": 5})
    with pytest.raises(CastError):
        cast.loads(header + "\n" + event)


def test_backwards_times_raise() -> None:
    header = json.dumps({"version": 2, "width": 10, "height": 5})
    body = json.dumps([2.0, "o", "a"]) + "\n" + json.dumps([1.0, "o", "b"])
    with pytest.raises(CastError, match="backwards"):
        cast.loads(header + "\n" + body)


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(CastError, match="cannot read"):
        cast.read(tmp_path / "nope.cast")


def test_with_events_keeps_metadata() -> None:
    rec = sample().with_events([])
    assert rec.events == [] and rec.command == "echo hi" and rec.cols == 80
