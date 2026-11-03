"""Small integer drawing canvas for native 64 × 32 clock faces (stdlib only)."""
from functools import lru_cache
import math

from render import WIDTH, HEIGHT, rasterize


@lru_cache(maxsize=256)
def rgb(color):
    return tuple(bytes.fromhex(color.lstrip('#'))) if isinstance(color, str) else tuple(color)


def shade(color, amount):
    if isinstance(color, (list, tuple)) and len(color) == 2:
        return tuple(shade(c, amount) for c in color)
    return tuple(round(v * amount) for v in rgb(color))


@lru_cache(maxsize=512)
def text_mask(value, w, h, font, face, size):
    """Cache glyph geometry independently of palette and animation position."""
    layer = {'t': 'text', 's': value, 'x': 0, 'y': 0, 'w': w, 'h': h,
             'f': font, 'c': '#FFFFFF', 'a': 'c', '_clip': (0, 0, w, h)}
    if face:
        layer.update(face=face, size=size)
    pixels = rasterize([layer])
    return tuple((i % WIDTH, i // WIDTH) for i, pixel in enumerate(pixels) if any(pixel))


class Canvas:
    def __init__(self):
        self.pixels = [(0, 0, 0)] * (WIDTH * HEIGHT)

    def point(self, x, y, color):
        x, y = round(x), round(y)
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            if isinstance(color, (list, tuple)) and len(color) == 2:
                a, b = rgb(color[0]), rgb(color[1])
                color = tuple(round(v + (b[i] - v) * x / (WIDTH - 1)) for i, v in enumerate(a))
            self.pixels[y * WIDTH + x] = rgb(color)

    def text(self, value, x, y, w, h, color, font='3x5', face=None, size='large', scale_y=1):
        for dx, dy in text_mask(str(value), w, h, font, face, size):
            self.point(x + dx, y + (h - 1) / 2 + (dy - (h - 1) / 2) * scale_y, color)

    def line(self, x1, y1, x2, y2, color, width=1):
        x1, y1, x2, y2 = map(round, (x1, y1, x2, y2))
        dx, dy = abs(x2 - x1), -abs(y2 - y1)
        sx, sy = (1 if x1 < x2 else -1), (1 if y1 < y2 else -1)
        err = dx + dy
        while True:
            for offset in range(width):
                self.point(x1 + (offset if abs(dy) > dx else 0),
                           y1 + (offset if abs(dy) <= dx else 0), color)
            if x1 == x2 and y1 == y2:
                break
            twice = 2 * err
            if twice >= dy:
                err += dy
                x1 += sx
            if twice <= dx:
                err += dx
                y1 += sy

    def rect(self, x1, y1, x2, y2, color, outline=False):
        if outline:
            self.line(x1, y1, x2, y1, color)
            self.line(x1, y2, x2, y2, color)
            self.line(x1, y1, x1, y2, color)
            self.line(x2, y1, x2, y2, color)
        else:
            for y in range(y1, y2 + 1):
                for x in range(x1, x2 + 1):
                    self.point(x, y, color)

    def arc(self, cx, cy, radius, fraction, color):
        # Sample at subpixel steps and connect raster points, including small rings.
        steps = max(1, math.ceil(radius * math.tau * max(0, min(1, fraction)) * 2))
        if fraction <= 0:
            return
        previous = (cx, cy - radius)
        for step in range(steps + 1):
            angle = -math.pi / 2 + math.tau * min(1, fraction) * step / steps
            current = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            self.line(*previous, *current, color)
            previous = current

    def hand(self, cx, cy, fraction, length, color, width=1):
        angle = fraction * math.tau - math.pi / 2
        self.line(cx, cy, cx + length * math.cos(angle), cy + length * math.sin(angle), color, width)
