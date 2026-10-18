"""Draw a terminal screen as a picture."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from PIL import Image, ImageDraw

from .fonts import FontSet
from .screen import Terminal
from .theme import RGB, Theme

# Box-drawing characters as (left, right, up, down) stroke weights:
# 0 none, 1 light, 2 heavy, 3 double. Drawn by hand so lines join across cell edges
# even though the text cell is taller than the font's glyphs.
_BOX: dict[str, tuple[int, int, int, int]] = {
    "─": (1, 1, 0, 0), "━": (2, 2, 0, 0), "│": (0, 0, 1, 1), "┃": (0, 0, 2, 2),
    "┄": (1, 1, 0, 0), "┅": (2, 2, 0, 0), "┆": (0, 0, 1, 1), "┇": (0, 0, 2, 2),
    "┈": (1, 1, 0, 0), "┉": (2, 2, 0, 0), "┊": (0, 0, 1, 1), "┋": (0, 0, 2, 2),
    "┌": (0, 1, 0, 1), "┏": (0, 2, 0, 2), "┐": (1, 0, 0, 1), "┓": (2, 0, 0, 2),
    "└": (0, 1, 1, 0), "┗": (0, 2, 2, 0), "┘": (1, 0, 1, 0), "┛": (2, 0, 2, 0),
    "├": (0, 1, 1, 1), "┣": (0, 2, 2, 2), "┤": (1, 0, 1, 1), "┫": (2, 0, 2, 2),
    "┬": (1, 1, 0, 1), "┳": (2, 2, 0, 2), "┴": (1, 1, 1, 0), "┻": (2, 2, 2, 0),
    "┼": (1, 1, 1, 1), "╋": (2, 2, 2, 2),
    "═": (3, 3, 0, 0), "║": (0, 0, 3, 3), "╔": (0, 3, 0, 3), "╗": (3, 0, 0, 3),
    "╚": (0, 3, 3, 0), "╝": (3, 0, 3, 0), "╠": (0, 3, 3, 3), "╣": (3, 0, 3, 3),
    "╦": (3, 3, 0, 3), "╩": (3, 3, 3, 0), "╬": (3, 3, 3, 3),
    "╭": (0, 1, 0, 1), "╮": (1, 0, 0, 1), "╯": (1, 0, 1, 0), "╰": (0, 1, 1, 0),
    "╌": (1, 1, 0, 0), "╍": (2, 2, 0, 0), "╎": (0, 0, 1, 1), "╏": (0, 0, 2, 2),
}  # fmt: skip

# Block elements as fractions (x0, y0, x1, y1) of the cell that are filled.
_BLOCKS: dict[str, tuple[tuple[float, float, float, float], ...]] = {
    "▀": ((0, 0, 1, 0.5),),
    "█": ((0, 0, 1, 1),),
    "▌": ((0, 0, 0.5, 1),),
    "▐": ((0.5, 0, 1, 1),),
    "▔": ((0, 0, 1, 0.125),),
    "▕": ((0.875, 0, 1, 1),),
    "▖": ((0, 0.5, 0.5, 1),),
    "▗": ((0.5, 0.5, 1, 1),),
    "▘": ((0, 0, 0.5, 0.5),),
    "▙": ((0, 0, 0.5, 1), (0.5, 0.5, 1, 1)),
    "▚": ((0, 0, 0.5, 0.5), (0.5, 0.5, 1, 1)),
    "▛": ((0, 0, 1, 0.5), (0, 0.5, 0.5, 1)),
    "▜": ((0, 0, 1, 0.5), (0.5, 0.5, 1, 1)),
    "▝": ((0.5, 0, 1, 0.5),),
    "▞": ((0.5, 0, 1, 0.5), (0, 0.5, 0.5, 1)),
    "▟": ((0.5, 0, 1, 1), (0, 0.5, 0.5, 1)),
}
for _i in range(1, 8):
    _BLOCKS[chr(0x2580 + _i)] = ((0, 1 - _i / 8, 1, 1),)  # lower n/8 blocks
    _BLOCKS[chr(0x2590 - _i)] = ((0, 0, _i / 8, 1),)  # left n/8 blocks
_SHADES = {"░": 64, "▒": 128, "▓": 192}

# Braille dot bit -> (column, row) inside the 2x4 dot grid.
_BRAILLE = {0x01: (0, 0), 0x02: (0, 1), 0x04: (0, 2), 0x08: (1, 0),
            0x10: (1, 1), 0x20: (1, 2), 0x40: (0, 3), 0x80: (1, 3)}  # fmt: skip


def is_wide(ch: str) -> bool:
    """True if ``ch`` occupies two terminal cells."""
    return bool(ch) and unicodedata.east_asian_width(ch[0]) in ("W", "F")


class Renderer:
    """Draws :class:`Terminal` contents onto a persistent RGB image."""

    def __init__(
        self,
        cols: int,
        rows: int,
        fonts: FontSet,
        theme: Theme,
        *,
        padding: int = 16,
        show_cursor: bool = True,
    ) -> None:
        self.cols, self.rows = cols, rows
        self.fonts, self.theme = fonts, theme
        self.padding = padding
        self.show_cursor = show_cursor
        self.cell_w, self.cell_h = fonts.cell_width, fonts.cell_height
        # H.264 and VP9 in yuv420p need even dimensions.
        self.width = cols * self.cell_w + 2 * padding
        self.height = rows * self.cell_h + 2 * padding
        self.width += self.width % 2
        self.height += self.height % 2
        self.image = Image.new("RGB", (self.width, self.height), theme.background)
        self._draw = ImageDraw.Draw(self.image)
        self._tiles: dict[tuple[str, bool, bool, bool], Image.Image] = {}
        self._stroke = max(1, round(self.cell_w / 8))

    # -- glyph tiles --------------------------------------------------------------

    def _tile(self, ch: str, bold: bool, italic: bool, wide: bool) -> Image.Image:
        key = (ch, bold, italic, wide)
        tile = self._tiles.get(key)
        if tile is None:
            tile = self._make_tile(ch, bold, italic, wide)
            self._tiles[key] = tile
        return tile

    def _make_tile(self, ch: str, bold: bool, italic: bool, wide: bool) -> Image.Image:
        w = self.cell_w * (2 if wide else 1)
        h = self.cell_h
        tile = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(tile)
        if ch in _BOX:
            self._draw_box(d, _BOX[ch], w, h)
        elif ch in _BLOCKS:
            for x0, y0, x1, y1 in _BLOCKS[ch]:
                left, top = round(x0 * w), round(y0 * h)
                right, bottom = max(round(x1 * w) - 1, 0), max(round(y1 * h) - 1, 0)
                d.rectangle((left, top, right, bottom), fill=255)
        elif ch in _SHADES:
            d.rectangle((0, 0, w - 1, h - 1), fill=_SHADES[ch])
        elif len(ch) == 1 and 0x2800 <= ord(ch) <= 0x28FF:
            self._draw_braille(d, ord(ch) - 0x2800, w, h)
        else:
            face = self.fonts.face(bold, italic)
            d.text((0, 0), ch, font=face, fill=255)
            if bold and not self.fonts.has_real_bold():
                d.text((1, 0), ch, font=face, fill=255)
        return tile

    def _draw_box(
        self, d: ImageDraw.ImageDraw, weights: tuple[int, int, int, int], w: int, h: int
    ) -> None:
        t = self._stroke
        cx, cy = w // 2, h // 2
        left, right, up, down = weights

        def stroke(weight: int) -> list[tuple[int, int]]:
            """(offset, thickness) pairs for one logical stroke."""
            if weight == 1:
                return [(0, t)]
            if weight == 2:
                return [(0, t * 2)]
            return [(-t, t), (t, t)]

        for weight, horizontal, toward_start in (
            (left, True, True),
            (right, True, False),
            (up, False, True),
            (down, False, False),
        ):
            if not weight:
                continue
            for off, thick in stroke(weight):
                lo = cy + off - thick // 2 if horizontal else cx + off - thick // 2
                hi = lo + thick - 1
                if horizontal:
                    x0, x1 = (0, cx + t) if toward_start else (cx - t, w - 1)
                    d.rectangle((x0, lo, x1, hi), fill=255)
                else:
                    y0, y1 = (0, cy + t) if toward_start else (cy - t, h - 1)
                    d.rectangle((lo, y0, hi, y1), fill=255)

    def _draw_braille(self, d: ImageDraw.ImageDraw, bits: int, w: int, h: int) -> None:
        radius = max(1, min(w, h) // 8)
        for bit, (col, row) in _BRAILLE.items():
            if bits & bit:
                cx = round(w * (0.3 + 0.4 * col))
                cy = round(h * (0.15 + 0.7 * row / 3))
                d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)

    # -- drawing ------------------------------------------------------------------

    def _origin(self, x: int, y: int) -> tuple[int, int]:
        return self.padding + x * self.cell_w, self.padding + y * self.cell_h

    def draw_rows(self, term: Terminal, rows: Iterable[int] | None = None) -> Image.Image:
        """Redraw ``rows`` (default: all) from ``term`` and return the image."""
        screen = term.screen
        theme = self.theme
        cursor = screen.cursor
        show_cursor = self.show_cursor and not cursor.hidden
        for y in sorted(range(self.rows) if rows is None else rows):
            if not 0 <= y < self.rows:
                continue
            line = screen.buffer[y]
            _, oy = self._origin(0, y)
            # clear the row to the theme background
            self._draw.rectangle(
                (0, oy, self.width - 1, oy + self.cell_h - 1), fill=theme.background
            )
            self._draw_row_backgrounds(line, y)
            for x in range(self.cols):
                cell = line[x]
                is_cursor = show_cursor and cursor.y == y and cursor.x == x
                fg, _bg = self._colours(cell)
                if is_cursor:
                    px, py = self._origin(x, y)
                    self._draw.rectangle(
                        (px, py, px + self.cell_w - 1, py + self.cell_h - 1), fill=theme.cursor
                    )
                    fg = theme.background
                ch = cell.data
                if ch and ch != " ":
                    wide = is_wide(ch)
                    tile = self._tile(ch, bool(cell.bold), bool(cell.italics), wide)
                    px, py = self._origin(x, y)
                    self.image.paste(fg, (px, py), tile)
                if cell.underscore or cell.strikethrough:
                    self._draw_lines(cell, x, y, fg)
        return self.image

    def _colours(self, cell) -> tuple[RGB, RGB]:
        fg = self.theme.color(cell.fg, background=False)
        bg = self.theme.color(cell.bg, background=True)
        if cell.reverse:
            fg, bg = bg, fg
        return fg, bg

    def _draw_row_backgrounds(self, line, y: int) -> None:
        """Fill runs of cells whose background differs from the theme background."""
        x = 0
        cols = self.cols
        while x < cols:
            _fg, bg = self._colours(line[x])
            if bg == self.theme.background:
                x += 1
                continue
            start = x
            while x < cols and self._colours(line[x])[1] == bg:
                x += 1
            px0, py = self._origin(start, y)
            px1, _ = self._origin(x, y)
            self._draw.rectangle((px0, py, px1 - 1, py + self.cell_h - 1), fill=bg)

    def _draw_lines(self, cell, x: int, y: int, colour: RGB) -> None:
        px, py = self._origin(x, y)
        thick = max(1, round(self.fonts.regular.size / 14))
        if cell.underscore:
            ly = py + min(self.fonts.ascent + 2, self.cell_h - thick)
            self._draw.rectangle((px, ly, px + self.cell_w - 1, ly + thick - 1), fill=colour)
        if cell.strikethrough:
            ly = py + self.cell_h // 2
            self._draw.rectangle((px, ly, px + self.cell_w - 1, ly + thick - 1), fill=colour)

    def render(self, term: Terminal) -> Image.Image:
        """Draw the whole screen."""
        return self.draw_rows(term, None)

    def frame_bytes(self) -> bytes:
        """Raw RGB24 pixels of the current image."""
        return self.image.tobytes()
