"""Pixel fonts and the layer rasterizer shared by the panel and every preview."""

from __future__ import annotations

import math
from functools import lru_cache

WIDTH = 32
HEIGHT = 16
BLACK = (0, 0, 0)
Pixel = tuple[int, int, int]

# 5x7 letters and digits (rows, "1" = lit), shared with the original flightboard font.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00001", "00010", "00100", "01000", "10000", "10000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}

# 5x7 punctuation from the design: column masks, bit 0 = top row.
FONT_EXTRA = {
    "°": (0x06, 0x09, 0x06), "%": (0x23, 0x13, 0x08, 0x64, 0x62), "+": (0x08, 0x1C, 0x08),
    ">": (0x41, 0x22, 0x14, 0x08), "<": (0x08, 0x14, 0x22, 0x41), "!": (0x5F,), "'": (0x03,),
    "?": (0x02, 0x01, 0x51, 0x09, 0x06), ",": (0x40, 0x30),
}

# 3x5 glyphs from the design: row masks, bit 2 = left column.
FONT3 = {
    "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 3, 1, 7),
    "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 2, 2),
    "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
    "A": (2, 5, 7, 5, 5), "B": (6, 5, 6, 5, 6), "C": (3, 4, 4, 4, 3), "D": (6, 5, 5, 5, 6),
    "E": (7, 4, 6, 4, 7), "F": (7, 4, 6, 4, 4), "G": (3, 4, 5, 5, 3), "H": (5, 5, 7, 5, 5),
    "I": (7, 2, 2, 2, 7), "J": (1, 1, 1, 5, 2), "K": (5, 5, 6, 5, 5), "L": (4, 4, 4, 4, 7),
    "M": (5, 7, 7, 5, 5), "N": (6, 5, 5, 5, 5), "O": (2, 5, 5, 5, 2), "P": (6, 5, 6, 4, 4),
    "Q": (2, 5, 5, 6, 3), "R": (6, 5, 6, 5, 5), "S": (3, 4, 2, 1, 6), "T": (7, 2, 2, 2, 2),
    "U": (5, 5, 5, 5, 7), "V": (5, 5, 5, 5, 2), "W": (5, 5, 7, 7, 5), "X": (5, 5, 2, 5, 5),
    "Y": (5, 5, 2, 2, 2), "Z": (7, 1, 2, 4, 7),
    ":": (0, 2, 0, 2, 0), ".": (0, 0, 0, 0, 2), "-": (0, 0, 7, 0, 0), "/": (1, 1, 2, 4, 4),
    "°": (2, 5, 2, 0, 0), "%": (5, 1, 2, 4, 5), "+": (0, 2, 7, 2, 0), "!": (2, 2, 2, 0, 2),
    "'": (2, 2, 0, 0, 0), ">": (4, 2, 1, 2, 4), "<": (1, 2, 4, 2, 1), "?": (6, 1, 2, 0, 2),
    ",": (0, 0, 0, 2, 4),
}

ICONS = {
    "plane": ("...#...", "...##..", "#..##..", "#######", "#..##..", "...##..", "...#..."),
    "sun": ("#..#..#", ".#...#.", "..###..", "#.###.#", "..###..", ".#...#.", "#..#..#"),
    "cloud": (".......", "...##..", ".######", "#######", "#######", ".#####.", "......."),
    "rain": ("..###..", ".#####.", "#######", ".......", ".#.#.#.", "#.#.#..", "......."),
    "snow": ("#..#..#", ".#.#.#.", "..###..", "#######", "..###..", ".#.#.#.", "#..#..#"),
    "storm": ("..###..", ".#####.", "#######", "...##..", "..##...", "...##..", "..#...."),
    "fog": (".......", "######.", ".......", ".######", ".......", "######.", "......."),
    "moon": ("..###..", ".##....", "##.....", "##.....", "##.....", ".##....", "..###.."),
    "heart": (".##.##.", "#######", "#######", ".#####.", "..###..", "...#...", "......."),
    "bus": (".#####.", "#.#.#.#", "#######", "#######", "#.###.#", ".#...#."),
    "iss": ("##.#.##", "##.#.##", "#######", "##.#.##", "##.#.##"),
    "note": ("..#####", "..#...#", "..#...#", ".##..##", "###.###", ".#...#."),
    "wind": ("...#...", "....#..", ".....#.", "#######", ".....#.", "....#..", "...#..."),
    "bolt": ("...##..", "..##...", ".##....", "#####..", "..##...", ".##....", "##....."),
    "timer": ("#######", ".#...#.", "..#.#..", "...#...", "..#.#..", ".#.#.#.", "#######"),
    "cup": (".#..#..", "..#..#.", ".......", "######.", "#####.#", "#####.#", ".####.."),
    "star": ("...#...", "...#...", "#######", ".#####.", "..###..", ".##.##.", "##...##"),
    "check": (".......", "......#", ".....##", "#...##.", "##.##..", ".###...", "..#...."),
    "maple": ("..#.#..", ".#####.", "#######", ".#####.", "..###..", "..#.#..", "...#..."),
    "westjet": ("#.....#", "#.....#", "#.#.#.#", "#.#.#.#", "#.#.#.#", "##...##", "#.....#"),
    "delta": ("...#...", "..###..", "..###..", ".##.##.", ".##.##.", "#######", "#######"),
}

SPACE = {"5x7": 2, "3x5": 1}
FONTS = {"big": ("3x5", 2, 10), "5x7": ("5x7", 1, 7), "3x5": ("3x5", 1, 5)}
AUTO_ORDER = ("big", "5x7", "3x5")
SCROLL_HOLD = 2.0
SCROLL_SPEED = 8.0


def _trim(cols: tuple[int, ...], char: str) -> tuple[int, ...]:
    if char.isdigit():
        return cols
    start, end = 0, len(cols)
    while start < end and not cols[start]:
        start += 1
    while end > start and not cols[end - 1]:
        end -= 1
    return cols[start:end]


def _build_glyphs() -> dict[str, dict[str, tuple[int, ...]]]:
    five = {}
    for char, rows in FONT.items():
        if char == " ":
            continue
        cols = tuple(sum(1 << r for r, row in enumerate(rows) if row[c] == "1") for c in range(5))
        five[char] = _trim(cols, char)
    for char, cols in FONT_EXTRA.items():
        five[char] = _trim(cols, char)
    three = {}
    for char, rows in FONT3.items():
        cols = tuple(sum(1 << r for r in range(5) if (rows[r] >> (2 - c)) & 1) for c in range(3))
        three[char] = _trim(cols, char)
    return {"5x7": five, "3x5": three}


GLYPHS = _build_glyphs()


@lru_cache(maxsize=2048)
def _shape(text: str, font: str) -> tuple[tuple[tuple[tuple[int, ...] | None, int], ...], int, int, int]:
    base, scale, height = FONTS.get(font, FONTS["5x7"])
    table = GLYPHS[base]
    glyphs = []
    for char in str(text).upper():
        if char == " ":
            glyphs.append((None, SPACE[base] * scale))
        elif char in table:
            glyphs.append((table[char], len(table[char]) * scale))
    width = sum(w for _, w in glyphs) + max(0, len(glyphs) - 1)
    return tuple(glyphs), width, height, scale


def measure(text: str, font: str) -> tuple[int, int]:
    """Return the (width, height) in pixels of text drawn in a font."""
    _, width, height, _ = _shape(text, font)
    return width, height


def fit_text(strings, width: int, height: int = HEIGHT) -> tuple[str, str, bool]:
    """Pick (font, string, scroll) the way `auto` text does."""
    candidates = [strings] if isinstance(strings, str) else [str(s) for s in strings] or [""]
    for font in AUTO_ORDER:
        if FONTS[font][2] > height:
            continue
        for text in candidates:
            if measure(text, font)[0] <= width:
                return font, text, False
    return "3x5", candidates[-1], True


def jround(value: float) -> int:
    """Round half up, like JavaScript's Math.round."""
    return math.floor(value + 0.5)


@lru_cache(maxsize=1024)
def parse_color(value) -> Pixel | None:
    if isinstance(value, tuple):
        return value
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return None
    try:
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    except ValueError:
        return None


def mix(a, b, t: float) -> Pixel:
    """Blend two colors; t is clamped to 0..1."""
    ca, cb = parse_color(a) or BLACK, parse_color(b) or BLACK
    t = max(0.0, min(1.0, t))
    return tuple(jround(x + (y - x) * t) for x, y in zip(ca, cb))


def hex_color(color: Pixel) -> str:
    return "#%02X%02X%02X" % color


def scroll_offset(overflow: int, elapsed: float) -> int:
    """Pixels to shift text that is `overflow` px too wide, holding at each end."""
    if overflow <= 0:
        return 0
    period = 2 * SCROLL_HOLD + overflow / SCROLL_SPEED
    t = elapsed % period
    return min(overflow, max(0, int((t - SCROLL_HOLD) * SCROLL_SPEED)))


class _Canvas:
    def __init__(self):
        self.buf: list[Pixel] = [BLACK] * (WIDTH * HEIGHT)

    def set(self, x: float, y: float, color, clip: tuple[int, int] | None = None) -> None:
        color = parse_color(color)
        if color is None:
            return
        x, y = jround(x), jround(y)
        if clip and not clip[0] <= x < clip[1]:
            return
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.buf[y * WIDTH + x] = color

    def rect(self, x, y, w, h, color) -> None:
        for i in range(int(w)):
            for j in range(int(h)):
                self.set(x + i, y + j, color)

    def line(self, x0, y0, x1, y1, color) -> None:
        x0, y0, x1, y1 = jround(x0), jround(y0), jround(x1), jround(y1)
        dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
        err = dx + dy
        for _ in range(256):
            self.set(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, color, top: bool = False, dotted: bool = False) -> None:
        for k in range(0, 360, 2):
            a = k * math.pi / 180
            x, y = jround(cx + r * math.cos(a)), jround(cy + r * math.sin(a))
            if (top and y > cy) or (dotted and (x + y) % 2):
                continue
            self.set(x, y, color)


def _text(canvas: _Canvas, layer: dict, elapsed: float) -> None:
    font, text = layer.get("f") or "5x7", layer.get("s", "")
    rx, ry = layer.get("x") or 0, layer.get("y") or 0
    rw = layer["w"] if layer.get("w") is not None else WIDTH - rx
    scroll, clip = bool(layer.get("scroll")), bool(layer.get("clip"))
    if font == "auto":
        font, text, forced = fit_text(text, rw, layer.get("h") or HEIGHT)
        scroll = scroll or forced
    elif not isinstance(text, str):
        text = text[0] if text else ""
    glyphs, width, height, scale = _shape(text, font)
    align = layer.get("a") or "c"
    if scroll and width > rw:
        x0, clip = rx - scroll_offset(width - rw, elapsed), True
    elif align == "l":
        x0 = rx
    elif align == "r":
        x0 = rx + rw - width
    else:
        x0 = rx + (rw - width) // 2
    y0 = ry + ((layer["h"] - height) // 2 if layer.get("h") else 0)
    grad, color = layer.get("grad"), layer.get("c")
    bounds = (rx, rx + rw) if clip else None
    cx = x0
    for index, (cols, gw) in enumerate(glyphs):
        if index:
            cx += 1
        for ci, mask in enumerate(cols or ()):
            for r in range(7):
                if not (mask >> r) & 1:
                    continue
                for dx in range(scale):
                    px = cx + ci * scale + dx
                    c = mix(grad[0], grad[1], (px - x0) / max(1, width - 1)) if grad else color
                    for dy in range(scale):
                        canvas.set(px, y0 + r * scale + dy, c, bounds)
        cx += gw


def _icon(canvas: _Canvas, layer: dict) -> None:
    rows = layer.get("rows") or ICONS.get(layer.get("n"), ())
    iw = len(rows[0]) if rows else 0
    x = (layer.get("x") or 0) + ((layer["w"] - iw) // 2 if layer.get("w") else 0)
    y = (layer.get("y") or 0) + ((layer["h"] - len(rows)) // 2 if layer.get("h") else 0)
    for j, row in enumerate(rows):
        for i, char in enumerate(row):
            if char == "#":
                canvas.set(x + i, y + j, layer.get("c"))


def _analog(canvas: _Canvas, L: dict) -> None:
    cx, cy, r = L["cx"], L["cy"], L["r"]
    canvas.circle(cx, cy, r, L.get("c"))
    for vx, vy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        canvas.set(cx + vx * (r - 1), cy + vy * (r - 1), L.get("c"))
    hr, mn = L.get("hr", 0), L.get("mn", 0)
    ha = ((hr % 12) + mn / 60) / 12 * 2 * math.pi
    ma = mn / 60 * 2 * math.pi
    canvas.line(cx, cy, cx + math.sin(ha) * (r - 3.2), cy - math.cos(ha) * (r - 3.2), L.get("hc"))
    canvas.line(cx, cy, cx + math.sin(ma) * (r - 1.6), cy - math.cos(ma) * (r - 1.6), L.get("mc"))


def _spark(canvas: _Canvas, L: dict) -> None:
    data = [float(v) for v in L.get("d") or () if isinstance(v, (int, float))]
    if not data:
        return
    x, y, w, h = L["x"], L["y"], L["w"], L["h"]
    n, low = len(data), min(data)
    span = (max(data) - low) or 1
    if L.get("line"):
        pts = [(x + jround(i * (w - 1) / max(1, n - 1)), y + h - 1 - jround((v - low) / span * (h - 1)))
               for i, v in enumerate(data)]
        if L.get("fill"):
            for px, py in pts:
                for yy in range(py + 1, y + h):
                    canvas.set(px, yy, L["fill"])
        for i in range(1, n):
            canvas.line(*pts[i - 1], *pts[i], L.get("c"))
        if n == 1:
            canvas.set(*pts[0], L.get("c"))
        return
    bw = max(1, w // n)
    for i, v in enumerate(data):
        hh = 1 + jround((v - low) / span * (h - 1))
        for k in range(hh):
            c = mix(L["c"], L["c2"], k / max(1, h - 1)) if L.get("c2") else L.get("c")
            for j in range(max(1, bw - 1)):
                canvas.set(x + i * bw + j, y + h - 1 - k, c)


def _draw(canvas: _Canvas, L: dict, elapsed: float) -> None:
    kind = L.get("t")
    if kind == "text":
        _text(canvas, L, elapsed)
    elif kind == "icon":
        _icon(canvas, L)
    elif kind == "px":
        pal = L.get("pal") or {}
        for j, row in enumerate(L.get("rows") or ()):
            for i, char in enumerate(row):
                if pal.get(char):
                    canvas.set(L["x"] + i, L["y"] + j, pal[char])
    elif kind == "pts":
        for p in L.get("p") or ():
            canvas.set(p[0], p[1], p[2])
    elif kind == "rect":
        canvas.rect(L["x"], L["y"], L["w"], L["h"], L.get("c"))
    elif kind == "line":
        canvas.line(L["x1"], L["y1"], L["x2"], L["y2"], L.get("c"))
    elif kind in ("circle", "arc"):
        canvas.circle(L["cx"], L["cy"], L["r"], L.get("c"), kind == "arc", bool(L.get("dotted")))
    elif kind == "bar":
        if L.get("bg"):
            canvas.rect(L["x"], L["y"], L["w"], L["h"], L["bg"])
        value = max(0.0, min(1.0, float(L.get("v") or 0)))
        canvas.rect(L["x"], L["y"], jround(L["w"] * value), L["h"], L.get("c"))
    elif kind == "dots":
        on = L.get("on")
        size, gap = L.get("size", 1), L.get("gap", 1)
        for i in range(L.get("n", 0)):
            lit = on[i] if on and i < len(on) else (0 if on else 1)
            canvas.rect(L["x"] + i * (size + gap), L["y"], size, size, L.get("c") if lit else L.get("off"))
    elif kind == "analog":
        _analog(canvas, L)
    elif kind == "spark":
        _spark(canvas, L)


def rasterize(layers, elapsed: float = 0.0) -> list[Pixel]:
    """Paint layer dicts onto a black 32x16 frame (row-major RGB tuples)."""
    canvas = _Canvas()
    for layer in layers or ():
        if isinstance(layer, dict):
            _draw(canvas, layer, elapsed)
    return canvas.buf


def to_hex(pixels) -> str:
    """Encode 512 pixels as 3072 lowercase hex characters."""
    return "".join("%02x%02x%02x" % tuple(p) for p in pixels)


def from_hex(value: str) -> list[Pixel]:
    return [(int(value[i:i + 2], 16), int(value[i + 2:i + 4], 16), int(value[i + 4:i + 6], 16))
            for i in range(0, len(value) - 5, 6)]


def tint(pixels, color) -> list[Pixel]:
    """Recolor a frame to one hue, keeping each pixel's brightness (night mode)."""
    target = parse_color(color) or (255, 255, 255)
    return [tuple(jround(c * max(p) / 255) for c in target) if any(p) else BLACK for p in pixels]
