import unittest
import hashlib
import json

import flightboard
import render
from render import fit_text, from_hex, measure, rasterize, scroll_offset, to_hex


def lit(pixels):
    return {(i % render.WIDTH, i // render.WIDTH) for i, p in enumerate(pixels) if any(p)}


class FontTests(unittest.TestCase):
    def test_standard_matches_the_approved_soft_classic_proposal(self):
        expected = {
            (6, 10, 1): "d377cffd21a9012dfb1665088d14d0d981744751f6906de8b1cd49379e79d7f6",
            (8, 14, 1): "1442fa9ab32ba5c995664ef6f4ad1d847c05ba9833ac536e630ddd920cdf1fee",
            (8, 14, 2): "ef262bac94e47ffd25970d9c32bfaff569b7f96c00c72fe3171b9141237d6dc9",
            (11, 20, 2): "bf6ecbe65c7ae5b6ef1d587a6ecc971a85bf95efa364cde7d98813a06bf3face",
            (14, 21, 2): "217754d7be54792a7fb26a9bf3f21e37929031c8dd9f4276d641ac330aa80f08",
            (13, 30, 3): "5ab4bd5a760e763349f879adcaf56938088fdb2e115e4f53bb6559b251602712",
            (18, 30, 3): "ca74bd07b6f1d691638e7bd2aef2a18ee1e3426b965389bb82daa6a55c9269e6",
        }
        for dims, digest in expected.items():
            table = render._standard_glyphs(*dims)
            digits = {char: table[char] for char in "0123456789"}
            self.assertEqual(hashlib.sha256(json.dumps(digits, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                             digest, dims)

    def test_standard_round_digits_have_balanced_pixel_curves_at_every_native_size(self):
        for width, height, stroke in ((6, 10, 1), (8, 14, 1), (8, 14, 2),
                                      (11, 20, 2), (14, 21, 2), (13, 30, 3), (18, 30, 3)):
            table = render._standard_glyphs(width, height, stroke)
            for digit in ("0", "8"):
                with self.subTest(size=(width, height, stroke), digit=digit):
                    points = {(x, y) for x, col in enumerate(table[digit])
                              for y in range(height) if col >> y & 1}
                    self.assertEqual(points, {(width - 1 - x, y) for x, y in points})
            six = {(x, y) for x, col in enumerate(table["6"]) for y in range(height) if col >> y & 1}
            nine = {(x, y) for x, col in enumerate(table["9"]) for y in range(height) if col >> y & 1}
            self.assertEqual(six, {(width - 1 - x, height - 1 - y) for x, y in nine})

    def test_max_outline_seven_is_one_connected_square_corner(self):
        for height in (15, 20, 32):
            with self.subTest(height=height):
                shape = render._styled_shape("7", 64, height, "outline", "max")
                cols, actual_height = shape[0][0][0], shape[2]
                self.assertTrue(all(column & 1 for column in cols))
                self.assertEqual(cols[-1], (1 << actual_height) - 1)
                points = {(x, y) for x, col in enumerate(cols) for y in range(actual_height) if col >> y & 1}
                remaining = set(points)
                pending = [remaining.pop()]
                while pending:
                    x, y = pending.pop()
                    for neighbour in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if neighbour in remaining:
                            remaining.remove(neighbour)
                            pending.append(neighbour)
                self.assertFalse(remaining, "The outlined top bar and stem must form one shape")

    def test_max_seven_keeps_its_advance_and_other_glyphs(self):
        normal = render._family_glyphs("outline", 13, 30, 3)
        maximum = render._family_glyphs("outline", 13, 30, 3, outline_max=True)
        self.assertEqual(len(normal["7"]), len(maximum["7"]))
        self.assertNotEqual(normal["7"], maximum["7"])
        for char in normal.keys() - {"7", ":"}:
            self.assertEqual(normal[char], maximum[char], char)

    def test_max_outline_colon_has_hollow_dots_and_stable_blinking(self):
        shape = render._styled_shape(":", 64, 32, "outline", "max")
        cols = shape[0][0][0]
        for top in (10, 20):
            self.assertEqual(tuple((col >> top) & 7 for col in cols), (7, 5, 7))
        layer = {"t": "text", "face": "outline", "size": "max", "s": "12:59",
                 "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FFFFFF"}
        on = lit(rasterize([layer]))
        off = lit(rasterize([{**layer, "s": "12 59"}]))
        self.assertTrue(off < on)
        self.assertEqual(len(on - off), 16)  # Two 3x3 rings, eight pixels each.
        self.assertEqual(len({x for x, _ in on - off}), 3)

    def test_other_font_colons_keep_their_solid_dots(self):
        for face, size in (("outline", "xl"), ("block", "max"), ("digital", "max")):
            with self.subTest(face=face, size=size):
                shape = render._styled_shape(":", 64, 32, face, size)
                cols = shape[0][0][0]
                self.assertEqual(len(set(cols)), 1)

    def test_max_outline_border_is_one_pixel_thick(self):
        glyph = render._family_glyphs("outline", 13, 30, 3)["0"]
        self.assertTrue(all(column & 1 for column in glyph))
        self.assertTrue(glyph[0] & (1 << 1))
        self.assertTrue(glyph[-1] & (1 << 1))
        self.assertTrue(all(not (column & (1 << 1)) for column in glyph[1:-1]))
        self.assertTrue(all(not (column & (1 << 28)) for column in glyph[1:-1]))

    def test_digital_one_and_four_share_the_other_digits_full_height(self):
        for height, width, stroke in ((10, 6, 1), (14, 8, 1), (20, 11, 2), (30, 13, 3)):
            table = render._family_glyphs("digital", width, height, stroke)
            for digit in "0123456789":
                with self.subTest(height=height, digit=digit):
                    points = {(x, y) for x, col in enumerate(table[digit])
                              for y in range(height) if col >> y & 1}
                    self.assertEqual(min(y for _, y in points), 0)
                    self.assertEqual(max(y for _, y in points), height - 1)
            # A centered, unbroken 1 avoids a floating right-aligned pair of bars.
            columns = [x for x, col in enumerate(table["1"]) if col]
            self.assertLessEqual(abs((min(columns) + max(columns)) / 2 - (width - 1) / 2), .5)
            self.assertTrue(all(table["1"][x] == (1 << height) - 1 for x in columns))
            # The 4 has a continuous right stem from cap height to baseline.
            self.assertEqual(table["4"][-1], (1 << height) - 1)

    def test_bitmap_font_frames_remain_identical(self):
        expected = {
            "block": "96793016ce9d99952f903fcb6dde89249202e130692fbd0e6c3551e9299fc073",
            "5x7": "411f6f43d133619294c113b772e50c10e698c08417a34d41596d5a51e05235ce",
            "3x5": "d2b50072424f9673cfe2a14d9ce190edd8d0b780eb95000b12dd8947e0a8f177",
        }
        for font, digest in expected.items():
            pixels = rasterize([{"t": "text", "f": font, "s": "12:59", "x": 0, "y": 0,
                                 "w": 64, "h": 32, "c": "#FFFFFF"}])
            self.assertEqual(hashlib.sha256(to_hex(pixels).encode()).hexdigest(), digest, font)

    def test_standard_digits_keep_open_counters_and_no_stray_holes(self):
        for width, height, stroke in ((6, 10, 1), (8, 14, 1), (8, 14, 2),
                                      (11, 20, 2), (14, 21, 2), (13, 30, 3), (18, 30, 3)):
            table = render._standard_glyphs(width, height, stroke)
            for digit in "0123456789":
                with self.subTest(size=(width, height, stroke), digit=digit):
                    ink = {(x, y) for x, col in enumerate(table[digit])
                           for y in range(height) if col >> y & 1}
                    self.assertEqual((min(y for _, y in ink), max(y for _, y in ink)), (0, height - 1))
                    # Flood the background; remaining components are counters.
                    blank = {(x, y) for x in range(-1, width + 1) for y in range(-1, height + 1)} - ink
                    pending, holes = [(-1, -1)], -1
                    blank.remove(pending[0])
                    while True:
                        holes += 1
                        while pending:
                            x, y = pending.pop()
                            for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                                if p in blank:
                                    blank.remove(p)
                                    pending.append(p)
                        if not blank:
                            break
                        pending = [blank.pop()]
                    self.assertEqual(holes, {"0": 1, "4": 1, "6": 1, "8": 2, "9": 1}.get(digit, 0))

    def test_standard_hinting_preserves_letters_punctuation_and_metrics(self):
        for width, height, stroke in ((6, 10, 1), (8, 14, 2), (11, 20, 2), (13, 30, 3)):
            original = render._stroke_glyphs(width, height, stroke)
            refined = render._standard_glyphs(width, height, stroke)
            self.assertEqual({key: cols for key, cols in original.items() if not key.isdigit()},
                             {key: cols for key, cols in refined.items() if not key.isdigit()})
            for digit in "0123456789":
                self.assertEqual(len(original[digit]), len(refined[digit]))

    def test_new_families_clip_to_the_slot_and_keep_gradients_and_long_text(self):
        for face in ("standard", "block", "outline", "digital"):
            for content in ("4:37", "12:59", "-12°", "HELLO WORLD THIS IS LONGER THAN THE PANEL"):
                with self.subTest(face=face, content=content):
                    pixels = rasterize([{"t": "text", "face": face, "size": "max", "s": content,
                                         "x": 33, "y": 17, "w": 31, "h": 15, "_clip": (33, 17, 31, 15),
                                         "grad": ["#FF0000", "#0000FF"]}], elapsed=3)
                    points = lit(pixels)
                    self.assertTrue(points)
                    self.assertTrue(all(33 <= x < 64 and 17 <= y < 32 for x, y in points))
                    self.assertGreater(len(set(pixels) - {(0, 0, 0)}), 2)

    def test_each_font_family_has_a_distinct_full_height_max_clock(self):
        frames = []
        for family in ("standard", "block", "outline", "digital"):
            with self.subTest(family=family):
                pixels = rasterize([{"t": "text", "s": "12:59", "face": family, "size": "max",
                                     "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FFFFFF"}])
                points = lit(pixels)
                self.assertEqual(max(y for _, y in points) - min(y for _, y in points) + 1, 30)
                # Digital 1 only lights the right-hand segments of its cell.
                self.assertGreaterEqual(max(x for x, _ in points) - min(x for x, _ in points) + 1,
                                        48 if family == "digital" else 56)
                self.assertTrue(all(1 <= x < 63 and 1 <= y < 31 for x, y in points))
                frames.append(to_hex(pixels))
        self.assertEqual(len(set(frames)), 4)

    def test_font_family_size_limits_and_blinking(self):
        for face in ("standard", "block", "outline", "digital"):
            for size, height in (("tiny", 5), ("small", 7), ("medium", 10),
                                 ("large", 14), ("xl", 20), ("max", 30), ("auto", 20)):
                with self.subTest(face=face, size=size):
                    layer = {"t": "text", "face": face, "size": size, "s": "12:59",
                             "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FFFFFF"}
                    on = lit(rasterize([layer]))
                    off = lit(rasterize([{**layer, "s": "12 59"}]))
                    self.assertTrue(off < on)
                    self.assertLessEqual(max(y for _, y in on) - min(y for _, y in on) + 1, height)

    def test_max_clock_fills_panel_for_short_and_wide_times(self):
        for text in ("4:37", "9:59", "10:00", "11:11", "12:59", "23:59"):
            with self.subTest(text=text):
                points = lit(rasterize([{"t": "text", "f": "max", "s": text,
                                         "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FFFFFF"}]))
                self.assertGreaterEqual(max(y for _, y in points) - min(y for _, y in points) + 1, 28)
                self.assertGreaterEqual(max(x for x, _ in points) - min(x for x, _ in points) + 1, 56)
                self.assertTrue(all(1 <= x < 63 and 1 <= y < 31 for x, y in points))

    def test_max_blinking_colon_does_not_move_digits(self):
        layer = {"t": "text", "f": "max", "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FFFFFF"}
        on = lit(rasterize([{**layer, "s": "12:59"}]))
        off = lit(rasterize([{**layer, "s": "12 59"}]))
        self.assertTrue(off < on)
        self.assertTrue(all(29 <= x <= 33 for x, _ in on - off))

    def test_max_fits_short_slots_and_preserves_neighboring_pixels(self):
        pixels = rasterize([
            {"t": "rect", "x": 0, "y": 0, "w": 31, "h": 32, "c": "#FF0000"},
            {"t": "text", "f": "max", "s": "12:59", "x": 33, "y": 17, "w": 31, "h": 15,
             "c": "#FFFFFF", "_clip": (33, 17, 31, 15)},
        ])
        points = {(i % 64, i // 64) for i, pixel in enumerate(pixels) if pixel == (255, 255, 255)}
        self.assertGreaterEqual(max(y for _, y in points) - min(y for _, y in points) + 1, 13)
        self.assertTrue(all(33 <= x < 64 and 17 <= y < 32 for x, y in points))
        self.assertEqual(sum(p == (255, 0, 0) for p in pixels), 31 * 32)

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
        for font in ("5x7", "3x5", "big", "large", "display"):
            self.assertEqual(measure("10:24", font), measure("10 24", font))

    def test_display_seven_has_fine_diagonal_and_full_height(self):
        pixels = lit(rasterize([{"t": "text", "f": "display", "s": "7", "x": 0, "y": 0,
                                 "a": "l", "c": "#FFFFFF"}]))
        rows = {tuple(sorted(x for x, py in pixels if py == y)) for y in range(4, 20)}
        self.assertGreater(len(rows), 5)  # Not three giant staircase positions from 3x5.
        self.assertEqual(max(y for _, y in pixels), 19)

    def test_large_degree_is_a_small_superscript_ring(self):
        for font, height in (("display", 20), ("large", 14), ("big", 10)):
            with self.subTest(font=font):
                pixels = lit(rasterize([{"t": "text", "f": font, "s": "°", "x": 0, "y": 0,
                                         "a": "l", "c": "#FFFFFF"}]))
                self.assertLess(max(y for _, y in pixels), height // 2)
                self.assertGreater(len(pixels), 4)

    def test_block_style_uses_chunky_pixels_and_adapts_to_short_slots(self):
        for height, bottom in ((21, 19), (15, 13), (10, 9), (7, 6)):
            with self.subTest(height=height):
                pixels = lit(rasterize([{"t": "text", "f": "block", "s": "10:24",
                                         "x": 0, "y": 0, "w": 64, "h": height, "c": "#FFFFFF"}]))
                self.assertEqual(max(y for _, y in pixels), bottom)
        pixels = lit(rasterize([{"t": "text", "f": "block", "s": "7", "a": "l",
                                 "x": 0, "y": 0, "w": 64, "h": 20, "c": "#FFFFFF"}]))
        self.assertEqual({(x, y) for x in range(12) for y in range(4)},
                         {(x, y) for x, y in pixels if y < 4})

    def test_design_punctuation_exists_in_both_fonts(self):
        for char in "°%+><!'?":
            self.assertGreater(measure(char, "5x7")[0], 0, char)
            self.assertGreater(measure(char, "3x5")[0], 0, char)


class AutoFitTests(unittest.TestCase):
    def test_picks_largest_font_then_candidate(self):
        self.assertEqual(fit_text(["10:24"], 32, 16), ("big", "10:24", False))
        self.assertEqual(fit_text(["10:24"], 32, 7), ("5x7", "10:24", False))
        self.assertEqual(fit_text(["10:24"], 32, 5), ("3x5", "10:24", False))
        self.assertEqual(fit_text(["WJA123", "WJA"], 24, 7), ("3x5", "WJA123", False))
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
        self.assertEqual(len(pixels), 2048)
        self.assertTrue(all(p == (0, 0, 0) for p in pixels))

    def test_centering_and_alignment(self):
        layer = {"t": "text", "s": "I", "f": "5x7", "y": 0, "c": "#FFFFFF"}
        self.assertEqual(sorted(x for x, y in lit(rasterize([layer])) if y == 0), [29, 30, 31, 32, 33])
        left = lit(rasterize([{**layer, "a": "l", "x": 2, "w": 20}]))
        self.assertEqual(min(x for x, _ in left), 2)
        right = lit(rasterize([{**layer, "a": "r", "x": 0, "w": 20}]))
        self.assertEqual(max(x for x, _ in right), 19)
        middle = lit(rasterize([{**layer, "y": 4, "h": 9}]))
        self.assertEqual(min(y for _, y in middle), 5)

    def test_clipping(self):
        pixels = rasterize([{"t": "text", "s": "WIDE TEXT", "f": "5x7", "x": 28, "y": 12, "c": "#FFFFFF"},
                            {"t": "rect", "x": -3, "y": -3, "w": 5, "h": 5, "c": "#FF0000"}])
        self.assertEqual(len(pixels), 2048)
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
        self.assertTrue(all(pixels[2 * render.WIDTH + x] == (0, 255, 0) for x in range(32)))
        self.assertEqual([pixels[4 * render.WIDTH + x] for x in (0, 2, 4)],
                         [(255, 255, 255), (34, 34, 34), (255, 255, 255)])
        self.assertEqual((pixels[6 * render.WIDTH], pixels[6 * render.WIDTH + 1], pixels[6 * render.WIDTH + 2]),
                         ((255, 0, 0), (0, 0, 0), (0, 0, 255)))
        self.assertEqual(pixels[15 * render.WIDTH + 31], (0xAB, 0xCD, 0xEF))
        self.assertEqual(pixels[6 * render.WIDTH + 21], (255, 0, 0))

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
        self.assertEqual(len(encoded), 12288)
        self.assertEqual(encoded[:12], "a1b2c3a1b2c3")
        self.assertEqual(encoded, encoded.lower())
        self.assertEqual(from_hex(encoded), pixels)
        tinted = render.tint(pixels, "#FF0000")
        self.assertEqual(tinted[0], (195, 0, 0))
        self.assertEqual(tinted[5], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
