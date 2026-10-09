import unittest

import flightboard
import render
from render import fit_text, from_hex, measure, rasterize, scroll_offset, to_hex


def lit(pixels):
    return {(i % 32, i // 32) for i, p in enumerate(pixels) if any(p)}


class FontTests(unittest.TestCase):
    def test_five_by_seven_matches_flightboard_font(self):
        self.assertEqual(render.FONT, flightboard.FONT)
        for name in ("maple", "westjet", "delta"):
            converted = tuple(row.replace("#", "1").replace(".", "0") for row in render.ICONS[name])
            self.assertEqual(converted, flightboard.ICONS[name])

    def test_glyph_widths(self):
        self.assertEqual(measure("1", "5x7"), (5, 7))
        self.assertEqual(measure("1", "3x5"), (3, 5))
        self.assertEqual(measure(":", "5x7"), (2, 7))
        self.assertEqual(measure(":", "3x5"), (1, 5))
        self.assertEqual(measure("10:24", "5x7"), (26, 7))
        self.assertEqual(measure("10:24", "3x5"), (17, 5))
        self.assertEqual(measure("10:24", "big"), (30, 10))
        self.assertEqual(measure("A A", "3x5"), (9, 5))
        self.assertEqual(measure("A A", "5x7"), (14, 7))
        self.assertEqual(measure("14°", "5x7"), (15, 7))
        self.assertEqual(measure("", "5x7"), (0, 7))
        self.assertEqual(measure("hi", "5x7"), measure("HI", "5x7"))

    def test_colon_and_space_share_width_for_blinking(self):
        for font in ("5x7", "3x5", "big"):
            self.assertEqual(measure("10:24", font), measure("10 24", font))

    def test_design_punctuation_exists_in_both_fonts(self):
        for char in "°%+><!'?":
            self.assertGreater(measure(char, "5x7")[0], 0, char)
            self.assertGreater(measure(char, "3x5")[0], 0, char)


class AutoFitTests(unittest.TestCase):
    def test_picks_largest_font_then_candidate(self):
        self.assertEqual(fit_text(["10:24"], 32, 16), ("big", "10:24", False))
        self.assertEqual(fit_text(["10:24"], 32, 7), ("5x7", "10:24", False))
        self.assertEqual(fit_text(["10:24"], 32, 5), ("3x5", "10:24", False))
        self.assertEqual(fit_text(["WJA123", "WJA"], 24, 7), ("5x7", "WJA", False))
        self.assertEqual(fit_text(["FRI OCT 9", "OCT 9"], 32, 5), ("3x5", "FRI OCT 9", False))

    def test_nothing_fits_scrolls_last_candidate(self):
        self.assertEqual(fit_text(["A VERY LONG MESSAGE", "STILL TOO LONG"], 10, 16),
                         ("3x5", "STILL TOO LONG", True))

    def test_auto_layer_uses_choice(self):
        pixels = rasterize([{"t": "text", "f": "auto", "s": ["10:24"], "x": 0, "y": 0, "w": 32, "h": 10,
                             "c": "#FFFFFF"}])
        self.assertEqual(max(y for _, y in lit(pixels)), 9)


class RasterTests(unittest.TestCase):
    def test_blank_frame(self):
        pixels = rasterize([])
        self.assertEqual(len(pixels), 512)
        self.assertTrue(all(p == (0, 0, 0) for p in pixels))

    def test_centering_and_alignment(self):
        layer = {"t": "text", "s": "I", "f": "5x7", "y": 0, "c": "#FFFFFF"}
        self.assertEqual(sorted(x for x, y in lit(rasterize([layer])) if y == 0), [13, 14, 15, 16, 17])
        left = lit(rasterize([{**layer, "a": "l", "x": 2, "w": 20}]))
        self.assertEqual(min(x for x, _ in left), 2)
        right = lit(rasterize([{**layer, "a": "r", "x": 0, "w": 20}]))
        self.assertEqual(max(x for x, _ in right), 19)
        middle = lit(rasterize([{**layer, "y": 4, "h": 9}]))
        self.assertEqual(min(y for _, y in middle), 5)

    def test_clipping(self):
        pixels = rasterize([{"t": "text", "s": "WIDE TEXT", "f": "5x7", "x": 28, "y": 12, "c": "#FFFFFF"},
                            {"t": "rect", "x": -3, "y": -3, "w": 5, "h": 5, "c": "#FF0000"}])
        self.assertEqual(len(pixels), 512)
        self.assertIn((0, 0), lit(pixels))
        clipped = lit(rasterize([{"t": "text", "s": "MMMMMM", "f": "5x7", "x": 4, "w": 10, "a": "l",
                                  "clip": True, "c": "#FFFFFF"}]))
        self.assertTrue(all(4 <= x < 14 for x, _ in clipped))

    def test_scroll_offset_holds_at_each_end(self):
        self.assertEqual(scroll_offset(0, 50), 0)
        self.assertEqual(scroll_offset(10, 0), 0)
        self.assertEqual(scroll_offset(10, 1.9), 0)
        self.assertEqual(scroll_offset(10, 2.5), 4)
        self.assertEqual(scroll_offset(10, 3.25), 10)
        self.assertEqual(scroll_offset(10, 5.0), 10)
        self.assertEqual(scroll_offset(10, 5.3), 0)

    def test_scrolling_text_moves_and_stays_in_region(self):
        layer = {"t": "text", "s": "HELLO WORLD", "f": "5x7", "x": 0, "w": 32, "scroll": True,
                 "c": "#FFFFFF"}
        start, later = lit(rasterize([layer], 0)), lit(rasterize([layer], 4))
        self.assertIn((0, 1), start)
        self.assertNotEqual(start, later)
        region = lit(rasterize([{**layer, "x": 8, "w": 16}], 3))
        self.assertTrue(all(8 <= x < 24 for x, _ in region))

    def test_gradient_text(self):
        pixels = rasterize([{"t": "text", "s": "I", "f": "5x7", "x": 0, "w": 5, "a": "l",
                             "grad": ["#FF0000", "#0000FF"]}])
        self.assertEqual(pixels[0], (255, 0, 0))
        self.assertEqual(pixels[4], (0, 0, 255))

    def test_shapes(self):
        pixels = rasterize([
            {"t": "bar", "x": 0, "y": 0, "w": 10, "h": 1, "v": 0.5, "c": "#FFFFFF", "bg": "#111111"},
            {"t": "line", "x1": 0, "y1": 2, "x2": 31, "y2": 2, "c": "#00FF00"},
            {"t": "dots", "x": 0, "y": 4, "n": 3, "size": 1, "gap": 1, "on": [1, 0, 1],
             "c": "#FFFFFF", "off": "#222222"},
            {"t": "px", "x": 0, "y": 6, "rows": ["a.b"], "pal": {"a": "#FF0000", "b": "#0000FF"}},
            {"t": "pts", "p": [[31, 15, "#ABCDEF"], [40, 40, "#FFFFFF"]]},
            {"t": "icon", "n": "heart", "x": 20, "y": 6, "c": "#FF0000"},
        ])
        self.assertEqual(pixels[4], (255, 255, 255))
        self.assertEqual(pixels[5], (17, 17, 17))
        self.assertTrue(all(pixels[2 * 32 + x] == (0, 255, 0) for x in range(32)))
        self.assertEqual([pixels[4 * 32 + x] for x in (0, 2, 4)],
                         [(255, 255, 255), (34, 34, 34), (255, 255, 255)])
        self.assertEqual((pixels[6 * 32], pixels[6 * 32 + 1], pixels[6 * 32 + 2]),
                         ((255, 0, 0), (0, 0, 0), (0, 0, 255)))
        self.assertEqual(pixels[15 * 32 + 31], (0xAB, 0xCD, 0xEF))
        self.assertEqual(pixels[6 * 32 + 21], (255, 0, 0))

    def test_circle_analog_spark(self):
        circle = lit(rasterize([{"t": "circle", "cx": 7, "cy": 7, "r": 7, "c": "#FFFFFF"}]))
        self.assertIn((14, 7), circle)
        self.assertIn((0, 7), circle)
        arc = lit(rasterize([{"t": "arc", "cx": 15, "cy": 9, "r": 8, "c": "#FFFFFF"}]))
        self.assertTrue(all(y <= 9 for _, y in arc))
        analog = lit(rasterize([{"t": "analog", "cx": 7, "cy": 7, "r": 7, "hr": 3, "mn": 0,
                                 "c": "#333333", "hc": "#FFFFFF", "mc": "#FFFFFF"}]))
        self.assertIn((10, 7), analog)
        self.assertIn((7, 2), analog)
        bars = lit(rasterize([{"t": "spark", "x": 0, "y": 0, "w": 32, "h": 8, "d": [1, 2, 3, 4],
                               "c": "#FFFFFF", "c2": "#FF0000"}]))
        self.assertIn((0, 7), bars)
        self.assertIn((24, 0), bars)
        line = lit(rasterize([{"t": "spark", "line": True, "x": 0, "y": 0, "w": 32, "h": 8,
                               "d": [0, 1], "c": "#FFFFFF"}]))
        self.assertIn((0, 7), line)
        self.assertIn((31, 0), line)
        self.assertEqual(lit(rasterize([{"t": "spark", "x": 0, "y": 0, "w": 8, "h": 8, "d": []}])), set())

    def test_ignores_bad_layers(self):
        pixels = rasterize([None, {"t": "unknown"}, {"t": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "c": "bad"}])
        self.assertTrue(all(p == (0, 0, 0) for p in pixels))

    def test_hex_round_trip_and_tint(self):
        pixels = rasterize([{"t": "rect", "x": 0, "y": 0, "w": 2, "h": 1, "c": "#A1B2C3"}])
        encoded = to_hex(pixels)
        self.assertEqual(len(encoded), 3072)
        self.assertEqual(encoded[:12], "a1b2c3a1b2c3")
        self.assertEqual(encoded, encoded.lower())
        self.assertEqual(from_hex(encoded), pixels)
        tinted = render.tint(pixels, "#FF0000")
        self.assertEqual(tinted[0], (195, 0, 0))
        self.assertEqual(tinted[5], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
