import json
import unittest
from datetime import datetime, timedelta, timezone

import blocks
import catalog
from blocks import RenderContext, data_needs, frame, render_screen, sample_context
from render import rasterize

PLAN_IDS = {
    "time-big", "time-classic", "time-analog", "time-words", "time-daybar", "sky-nearby",
    "sky-follow", "sky-radar", "sky-iss", "sky-sun", "weather-now", "weather-hourly",
    "weather-rain", "weather-metar", "focus-pomodoro", "focus-countdown", "focus-streak",
    "focus-nextup", "play-message", "play-pet", "play-life", "play-fire", "play-music",
    "data-market", "data-score", "data-transit", "data-health", "night-clock",
}
MDT = timezone(timedelta(hours=-6))


def lit(pixels):
    return {(i % 32, i // 32) for i, p in enumerate(pixels) if any(p)}


def screen(layout, *slots, palette=None, sid="custom-test"):
    return {"id": sid, "name": "Test", "layout": layout, "style": {"palette": palette, "motion": "still"},
            "slots": [{"block": b, "color": c, "options": o} for b, c, o in slots]}


def one(block, color="#FFFFFF", **options):
    return screen("full", (block, color, options))


def texts(layers):
    return [layer["s"] for layer in layers if layer["t"] == "text"]


class CatalogTests(unittest.TestCase):
    def test_ascii_preview_shape(self):
        # CONTRIBUTING.md asks for this preview when a screen is added to catalog.py.
        screen = next(s for s in catalog.BUILTIN_SCREENS if s["id"] == "time-classic")
        lines = blocks.ascii_preview(screen).splitlines()
        self.assertEqual(len(lines), 16)
        self.assertTrue(all(len(line) == 32 and set(line) <= {"#", "."} for line in lines))
        self.assertIn("#", "".join(lines))

    def test_builtins_are_valid_screens(self):
        self.assertTrue(PLAN_IDS <= set(catalog.BUILTINS))
        for item in catalog.BUILTIN_SCREENS:
            layout = catalog.LAYOUTS[item["layout"]]
            self.assertEqual(len(item["slots"]), len(layout["slots"]), item["id"])
            for key in ("name", "family", "tag", "source", "style"):
                self.assertIn(key, item)
            for slot in item["slots"]:
                options = catalog.BLOCKS[slot["block"]]["options"]
                self.assertTrue(set(slot["options"]) <= set(options), (item["id"], slot))
            self.assertIn(item["style"]["motion"], catalog.MOTIONS)
            self.assertTrue(item["style"]["palette"] is None or item["style"]["palette"] in catalog.PALETTES)

    def test_block_option_defaults_are_valid(self):
        for block, meta in catalog.BLOCKS.items():
            self.assertIn(block, blocks.RENDERERS)
            for name, spec in meta["options"].items():
                if spec["type"] == "enum":
                    self.assertIn(spec["default"], spec["choices"], (block, name))

    def test_shelves_and_legacy_ids(self):
        shelved = [sid for shelf in catalog.SHELVES for sid in shelf["items"]]
        self.assertEqual([s["id"] for s in catalog.SHELVES], ["time", "sky", "weather", "focus", "play", "data"])
        self.assertTrue(set(shelved) <= set(catalog.BUILTINS))
        self.assertTrue(PLAN_IDS <= set(shelved))
        self.assertEqual(catalog.LEGACY_IDS["clock-classic"], "time-classic")
        for target in catalog.LEGACY_IDS.values():
            self.assertIn(target, catalog.BUILTINS)
        self.assertEqual([s["block"] for s in catalog.BUILTINS["time-simple"]["slots"]], ["time"])
        self.assertEqual([s["block"] for s in catalog.BUILTINS["time-weekday"]["slots"]], ["time", "weekday"])

    def test_catalog_json(self):
        body = catalog.catalog_json()
        for key in ("layouts", "palettes", "blocks", "icons", "motions", "transitions", "builtins", "shelves"):
            self.assertIn(key, body)
        json.dumps(body)
        body["builtins"][0]["name"] = "changed"
        self.assertNotEqual(catalog.BUILTIN_SCREENS[0]["name"], "changed")

    def test_sample_art_frames_match_size(self):
        for art in catalog.BUILTIN_ART.values():
            self.assertTrue(all(len(f) == art["w"] * art["h"] for f in art["frames"]))


class BuiltinRenderTests(unittest.TestCase):
    def test_every_builtin_renders_with_sample_and_empty_data(self):
        sample = sample_context()
        for item in catalog.BUILTIN_SCREENS:
            for ctx in (sample, RenderContext(now=sample.now), RenderContext(now=sample.now, elapsed=33.3)):
                pixels = rasterize(render_screen(item, ctx, strict=True), ctx.elapsed)
                self.assertEqual(len(pixels), 512)
                self.assertTrue(lit(pixels), item["id"])

    def test_design_previews(self):
        ctx = sample_context()
        self.assertEqual(texts(render_screen(catalog.BUILTINS["time-classic"], ctx)), [["10:24"], ["FRI 9", "OCT 9", "9"]])
        big = render_screen(catalog.BUILTINS["time-big"], ctx)
        self.assertEqual(big[0]["grad"], ["#FFD23F", "#FF5A36"])
        self.assertEqual(big[1]["c"], "#8C8A84")
        words = texts(render_screen(catalog.BUILTINS["time-words"], ctx))
        self.assertEqual([w[0] for w in words], ["NEARLY", "HALF", "PAST TEN"])
        nearby = texts(render_screen(catalog.BUILTINS["sky-nearby"], ctx))
        self.assertEqual(nearby, [["WJA123", "WJA"], ["YYC>YVR"]])
        self.assertEqual(texts(render_screen(catalog.BUILTINS["focus-countdown"], ctx))[1][-1], "12D")
        self.assertEqual(texts(render_screen(catalog.BUILTINS["focus-pomodoro"], ctx))[0], ["18:42"])
        self.assertEqual(texts(render_screen(catalog.BUILTINS["focus-nextup"], ctx))[0][0], "NEXT 9:30")
        self.assertEqual(texts(render_screen(catalog.BUILTINS["sky-sun"], ctx))[0][0], "SET 6:51")
        sun = [l for l in render_screen(catalog.BUILTINS["sky-sun"], ctx) if l["t"] == "rect" and l["w"] == 2]
        self.assertEqual((sun[0]["x"], sun[0]["y"]), (21, 3))

    def test_everything_fits_its_slot(self):
        contexts = (sample_context(), RenderContext(now=sample_context().now))
        for block in catalog.BLOCKS:
            options = {"metar": {"station": "CYYC"}, "feed": {"feed_id": "feed-market", "label": "TSX"},
                       "countdown": {"date": "2026-10-21", "label": "TOKYO"}}.get(block, {})
            for layout_id, layout in catalog.LAYOUTS.items():
                for index, rect in enumerate(layout["slots"]):
                    slots = [("none", None, {})] * len(layout["slots"])
                    slots[index] = (block, "#FFB23F", options)
                    for ctx in contexts:
                        pixels = rasterize(render_screen(screen(layout_id, *slots), ctx, strict=True), 4.2)
                        for x, y in lit(pixels):
                            self.assertTrue(rect["x"] <= x < rect["x"] + rect["w"]
                                            and rect["y"] <= y < rect["y"] + rect["h"],
                                            (block, layout_id, index, x, y))

    def test_bad_screens_do_not_raise(self):
        ctx = sample_context()
        for bad in ({}, {"layout": "nope", "slots": "x"}, {"layout": "two", "slots": [None, {"block": "zzz"}]},
                    {"layout": "full", "slots": [{"block": "time", "color": "red", "options": {"h24": "x", "font": 3}}]}):
            self.assertEqual(len(frame(bad, ctx)), 512)


class BlockBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.ctx = sample_context()

    def render(self, item, **changes):
        ctx = RenderContext(**{**self.ctx.__dict__, **changes})
        return render_screen(item, ctx, strict=True)

    def test_world_clock(self):
        morning = datetime(2026, 10, 9, 8, 24, tzinfo=MDT)
        london = self.render(one("world_clock", city="LDN"), now=morning)
        self.assertEqual(texts(london), [["15:24"], ["LDN"], ["+7H"]])
        self.assertEqual(london[0]["c"], "#FFFFFF")  # daytime in London
        # Half-hour zones fall back to a decimal when the label leaves no room.
        delhi = self.render(one("world_clock", city="DEL", label="mum"), now=morning)
        self.assertEqual(texts(delhi), [["19:54"], ["MUM"], ["+11:30", "+11.5"]])
        # A different date shows its weekday; night uses the accent (soft blue by default).
        tokyo = self.render(one("world_clock", city="TYO", h24=False), now=morning)
        self.assertEqual(texts(tokyo), [["11:24"], ["TYO"], ["+15H"]])
        self.assertEqual(tokyo[0]["c"], blocks.NIGHT_BLUE)  # 23:24 there
        afternoon = morning.replace(hour=16)
        tomorrow = self.render(one("world_clock", city="TYO"), now=afternoon)
        self.assertEqual(texts(tomorrow), [["07:24"], ["TYO"], ["SAT"]])
        row = self.render(screen("three", ("world_clock", "#FFFFFF", {"city": "NYC"}),
                                 ("none", None, {}), ("none", None, {})), now=morning)
        self.assertEqual(texts(row), [["NYC 10:24", "10:24"]])
        self.assertIsNone(blocks.city_time("XXX", morning))

    def test_time_options(self):
        afternoon = datetime(2026, 10, 9, 16, 24, 1, tzinfo=MDT)
        self.assertEqual(texts(self.render(one("time", h24=False), now=afternoon)), [["4:24"]])
        self.assertEqual(texts(self.render(one("time"), now=afternoon)), [["16:24"]])
        self.assertEqual(texts(self.render(one("time", colon_blink=True), now=afternoon)), [["16 24"]])
        even = afternoon.replace(second=2)
        self.assertEqual(texts(self.render(one("time", colon_blink=True), now=even)), [["16:24"]])
        self.assertEqual(self.render(one("time", font="5x7"))[0]["f"], "5x7")

    def test_units(self):
        self.assertEqual(texts(self.render(one("temp", which="hilo")))[0][0], "H18 L6")
        self.assertEqual(texts(self.render(screen("two", ("temp", None, {}), ("none", None, {})),
                                           units={"temp": "F", "distance": "nm"}))[0][0], "57°F")
        km = texts(self.render(screen("two", ("flight", None, {"field": "detail"}), ("none", None, {})),
                               units={"temp": "C", "distance": "km"}))
        self.assertEqual(km[0][0], "5.9KM 12K")
        self.assertEqual(texts(self.render(one("iss")))[-1][0], "670NM")

    def test_placeholders_are_dimmed(self):
        empty = RenderContext(now=self.ctx.now)
        layers = render_screen(one("temp", "#FFFFFF"), empty)
        self.assertTrue(all(l.get("c") != "#FFFFFF" for l in layers))
        self.assertEqual(texts(render_screen(one("feed"), empty)), [["SET UP", "SET"]])
        self.assertEqual(texts(render_screen(one("countdown"), empty)), [["SET UP", "SET"]])

    def test_countdown_and_timer(self):
        late = datetime(2026, 10, 21, 9, 0, tzinfo=MDT)
        item = one("countdown", date="2026-10-21", label="trip")
        self.assertEqual(texts(self.render(item, now=late))[1], ["TODAY", "NOW"])
        running = {"x": {"state": "running", "phase": "work", "work_min": 25, "break_min": 5,
                         "ends_at": self.ctx.now.timestamp() + 90, "remaining_s": None, "cycles": 1}}
        item = {**one("timer"), "id": "x"}
        layers = self.render(item, timers=running)
        self.assertEqual(texts(layers)[0], ["1:30"])
        self.assertAlmostEqual(layers[1]["v"], 1 - 90 / 1500)
        self.assertEqual(layers[2]["on"], [1, 0, 0, 0])
        self.assertEqual(texts(self.render(item, timers={}))[0], ["25:00"])

    def test_habit_week(self):
        layers = self.render(catalog.BUILTINS["focus-streak"])
        dots = [l for l in layers if l["t"] == "dots"][0]
        self.assertEqual(dots["on"], [1, 1, 1, 1, 1, 0, 0])
        self.assertEqual(texts(layers)[1], ["12"])
        layers = self.render(catalog.BUILTINS["focus-streak"], habits={})
        self.assertEqual(texts(layers)[1], ["0"])

    def test_flight_rotates_every_ten_seconds(self):
        item = screen("two", ("flight", None, {}), ("none", None, {}))
        first = texts(self.render(item, elapsed=0))[0][0]
        second = texts(self.render(item, elapsed=10.5))[0][0]
        self.assertEqual((first, second), ("WJA123", "ACA150"))
        follow = one("flight", source="follow", callsign="XX1")
        self.assertIn(["NOT SEEN", "--"], texts(self.render(follow)))

    def test_fuzzy_words(self):
        def words(h, m):
            prefix, middle, last = blocks.fuzzy_words(datetime(2026, 1, 1, h, m))
            return prefix, middle, last[0]
        self.assertEqual(words(10, 24), ("NEARLY", "HALF", "PAST TEN"))
        self.assertEqual(words(10, 0), ("IT'S", "TEN", "O'CLOCK"))
        self.assertEqual(words(10, 58), ("NEARLY", "ELEVEN", "O'CLOCK"))
        self.assertEqual(words(23, 47), ("AFTER", "QUARTER", "TO TWELVE"))
        self.assertEqual(blocks.fuzzy_words(datetime(2026, 1, 1, 7, 15))[2], ["PAST SEVEN", "PAST 7"])

    def test_animation(self):
        art = {"a": {"id": "a", "w": 7, "h": 7, "palette": ["#FF0000", "#00FF00"], "fps": 2,
                     "frames": ["0" * 49, "1" * 49]}}
        item = one("art", art_id="a")
        self.assertNotEqual(frame(item, RenderContext(now=self.ctx.now, art=art, elapsed=0)),
                            frame(item, RenderContext(now=self.ctx.now, art=art, elapsed=0.6)))
        for block in ("life", "fire"):
            first = frame(one(block, "#7CFF8A"), RenderContext(now=self.ctx.now, elapsed=5))
            again = frame(one(block, "#7CFF8A"), RenderContext(now=self.ctx.now, elapsed=5))
            later = frame(one(block, "#7CFF8A"), RenderContext(now=self.ctx.now, elapsed=5.6))
            self.assertEqual(first, again)
            self.assertNotEqual(first, later)
        blocks._LIFE_CACHE.clear()
        self.assertEqual(frame(one("life", "#7CFF8A"), RenderContext(now=self.ctx.now, elapsed=5)),
                         frame(one("life", "#7CFF8A"), RenderContext(now=self.ctx.now, elapsed=5)))

    def test_palettes(self):
        item = screen("two", ("time", None, {}), ("date", None, {}), palette="phosphor")
        layers = self.render(item)
        self.assertEqual((layers[0]["c"], layers[1]["c"]), ("#7CFF8A", "#2F8A48"))
        plain = self.render(screen("two", ("time", None, {}), ("date", "#123456", {})))
        self.assertEqual((plain[0]["c"], plain[1]["c"]), ("#FFFFFF", "#123456"))
        night = render_screen(catalog.BUILTINS["time-classic"], self.ctx, palette="night")
        self.assertEqual((night[0]["c"], night[1]["c"]), ("#FF3B2F", "#7A1E18"))

    def test_radar_and_sun(self):
        layers = self.render(catalog.BUILTINS["sky-radar"])
        points = [l for l in layers if l["t"] == "pts"][0]["p"]
        self.assertEqual(len(points), 8)
        self.assertTrue(all(0 <= x < 15 and 0 <= y < 15 for x, y, _ in points))
        self.assertEqual(texts(layers)[0], ["7"])


class DataNeedsTests(unittest.TestCase):
    def test_needs(self):
        needs = lambda sid: data_needs(catalog.BUILTINS[sid])
        self.assertEqual(needs("time-classic"), set())
        self.assertEqual(needs("weather-now"), {"weather"})
        self.assertEqual(needs("sky-nearby"), {"aircraft:nearby"})
        self.assertEqual(needs("sky-follow"), set())
        self.assertEqual(needs("weather-metar"), {"metar:CYYC"})
        self.assertEqual(needs("focus-pomodoro"), {"timers"})
        self.assertEqual(needs("focus-nextup"), {"calendar"})
        self.assertEqual(needs("sky-sun"), {"sun"})
        self.assertEqual(needs("sky-iss"), {"iss"})
        self.assertEqual(needs("data-health"), {"health"})
        self.assertEqual(needs("data-market"), {"feed:feed-market"})
        follow = one("flight", source="follow", callsign="ac 150")
        self.assertEqual(data_needs(follow), {"aircraft:follow:AC150"})
        mixed = screen("icon2", ("weather_icon", None, {}), ("spark", None, {"source": "feed", "feed_id": "feed-0a1b2c3d"}),
                       ("progress", None, {"source": "timer"}))
        self.assertEqual(data_needs(mixed), {"weather", "feed:feed-0a1b2c3d", "timers"})
        self.assertEqual(data_needs({"slots": [None, "x"]}), set())


if __name__ == "__main__":
    unittest.main()
