"""The terminal size handed to a session is the size the child sees."""

import re
import sys

import pytest

from flicker.pty import PtySession, spawn_pty

PY = sys.executable
ASK = "import os; s = os.get_terminal_size(); print('SIZE', s.columns, s.lines)"

WATCHER = """\
import os, time
print('ready', flush=True)
end = time.time() + 20
while time.time() < end:
    s = os.get_terminal_size()
    if s.columns == 100:
        print('NOW', s.columns, s.lines, flush=True)
        break
    time.sleep(0.05)
"""


def reported_size(cols: int, rows: int) -> tuple[int, int]:
    output, _ = spawn_pty([PY, "-c", ASK], cols=cols, rows=rows, timeout=20)
    m = re.search(r"SIZE (\d+) (\d+)", output)
    assert m, output
    return int(m.group(1)), int(m.group(2))


def require_tty() -> None:
    with PtySession([PY, "-c", "pass"]) as s:
        if not s.uses_tty:
            pytest.skip("no pseudo-terminal backend available (pipe fallback)")
        s.wait(10)


@pytest.mark.parametrize("cols, rows", [(80, 24), (40, 10), (132, 43)])
def test_child_sees_requested_size(cols: int, rows: int) -> None:
    require_tty()
    assert reported_size(cols, rows) == (cols, rows)


def test_columns_and_lines_environment_is_set() -> None:
    code = "import os; print('ENV', os.environ['COLUMNS'], os.environ['LINES'])"
    output, _ = spawn_pty([PY, "-c", code], cols=70, rows=20, timeout=20)
    assert "ENV 70 20" in output


def test_resize_is_visible_to_the_child(tmp_path) -> None:
    require_tty()
    script = tmp_path / "watch.py"
    script.write_text(WATCHER, encoding="utf-8")
    with PtySession([PY, str(script)], cols=60, rows=15) as session:
        seen = ""
        resized = False
        for _ in range(800):
            chunk = session.read(0.05)
            if chunk is None:
                break
            seen += chunk
            if "ready" in seen and not resized:
                session.resize(100, 30)
                resized = True
        assert "NOW 100 30" in seen
