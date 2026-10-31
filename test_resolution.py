"""Native pixel fidelity and saved-library compatibility across the resolution upgrade."""
import copy
from pathlib import Path
import tempfile
import unittest

import blocks
import catalog
import library
import render


class NativeResolutionTests(unittest.TestCase):
    def test_individual_pixels_and_slot_clip(self):
        frame = render.rasterize([
            {"t": "pts", "p": [[63, 31, "#123456"], [62, 31, "#ABCDEF"]]},
            {"t": "rect", "x": 0, "y": 0, "w": 64, "h": 32, "c": "#FF0000",
             "_clip": (33, 10, 3, 2)},
        ])
        self.assertEqual(len(frame), 2048)
        self.assertEqual(frame[-1], (0x12, 0x34, 0x56))
        self.assertEqual(frame[-2], (0xAB, 0xCD, 0xEF))
        self.assertEqual(frame[-3], render.BLACK)
        self.assertEqual(sum(p == (255, 0, 0) for p in frame), 6)

    def test_layout_contract_and_fonts(self):
        self.assertEqual(catalog.catalog_json()["display"], {"width": 64, "height": 32})
        for layout in catalog.LAYOUTS.values():
            occupied = set()
            for r in layout["slots"]:
                cells = {(x, y) for x in range(r["x"], r["x"] + r["w"])
                         for y in range(r["y"], r["y"] + r["h"])}
                self.assertFalse(occupied & cells)
                self.assertTrue(all(0 <= x < 64 and 0 <= y < 32 for x, y in cells))
                occupied |= cells
        self.assertEqual(render.fit_text("10:24", 64, 21), ("display", "10:24", False))
        self.assertEqual(render.fit_text(["WJA123", "WJA"], 55, 10)[1], "WJA123")
        web = (Path(__file__).parent / "web" / "display.js").read_text()
        self.assertIn("COLS = 64;", web)
        self.assertIn("ROWS = 32;", web)

    def test_every_builtin_uses_lower_half(self):
        for screen in catalog.BUILTIN_SCREENS:
            with self.subTest(screen=screen["id"]):
                frame = blocks.frame(screen, blocks.sample_context())
                self.assertEqual(len(frame), 2048)
                self.assertTrue(any(any(p) for p in frame[64 * 16:]))

    def test_saved_art_and_screen_choices_survive_roundtrip(self):
        lib = library.default_library()
        custom = copy.deepcopy(catalog.BUILTINS["time-classic"])
        custom = {k: custom[k] for k in library.SCREEN_KEYS}
        custom["id"] = "custom-" + "a" * 32
        lib["screens"] = [custom]
        lib["pinned"] = {"screen_id": custom["id"], "until": None}
        lib["art"] = [
            {"id": "art-" + f"{i:016x}", "name": f"Drawing {i}", "w": w, "h": h,
             "palette": ["#FF0000", "#00FF00"], "fps": 2,
             "frames": ["0" + "." * (w * h - 2) + "1", "." * (w * h - 1) + "0"]}
            for i, (w, h) in enumerate(library.ART_SIZES)]
        expected = library.validate_library(lib)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            library.save_library(lib, path)
            actual = library.load_library(path)
        self.assertEqual(actual, expected)
        for art in actual["art"]:
            screen = {"layout": "full", "slots": [{"block": "art", "options": {"art_id": art["id"]}}]}
            ctx = blocks.sample_context()
            ctx.art = {art["id"]: art}
            frame = blocks.frame(screen, ctx)
            scale = min(64 // art["w"], 32 // art["h"])
            self.assertEqual(sum(p == (255, 0, 0) for p in frame), scale * scale)
            self.assertEqual(sum(p == (0, 255, 0) for p in frame), scale * scale)
            if (art["w"], art["h"]) == (64, 32):
                self.assertEqual(frame[-1], (0, 255, 0))
                self.assertEqual(frame[-2], render.BLACK)


if __name__ == "__main__":
    unittest.main()
