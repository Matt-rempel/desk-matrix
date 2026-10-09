import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest

import catalog
import library as lib_mod
from library import (advance_timer, all_screen_ids, apply_action, default_library, load_library,
                     migrate_from_settings, resolve_screen, save_library, validate_art,
                     validate_feed, validate_library, validate_lineup, validate_screen)
from settings import validate_settings

CUSTOM = "custom-" + "a" * 32
NOW = 1_800_000_000.0  # 2027-01-15 UTC


def screen(**changes):
    value = {"id": CUSTOM, "name": "Morning glance", "layout": "icon2",
             "slots": [{"block": "weather_icon", "color": "#ffb23f", "options": {}},
                       {"block": "time", "color": None, "options": {"h24": False}},
                       {"block": "temp", "color": ["#FFFFFF", "#ff0000"], "options": {"which": "hilo"}}],
             "style": {"palette": "ember", "motion": "breathe"}, "based_on": "time-big"}
    value.update(changes)
    return value


def art(**changes):
    value = {"id": "art-" + "0" * 16, "name": "Dot", "w": 7, "h": 7, "palette": ["#ff0000", "#00FF00"],
             "frames": ["0" + "." * 47 + "1"], "fps": 2}
    value.update(changes)
    return value


def feed(**changes):
    value = {"id": "feed-0123abcd", "name": "Market", "url": "https://example.com/q.json",
             "path": "data.0.price", "series_path": "", "prefix": "$", "suffix": "", "interval_s": 300}
    value.update(changes)
    return value


def act(lib, action, now=NOW, **fields):
    return apply_action(lib, {"action": action, **fields}, now=lambda: now)


class ValidationTests(unittest.TestCase):
    def test_good_screen_is_normalized(self):
        clean = validate_screen(screen(name="  Morning glance "))
        self.assertEqual(clean["name"], "Morning glance")
        self.assertEqual(clean["slots"][0]["color"], "#FFB23F")
        self.assertEqual(clean["slots"][2]["color"], ["#FFFFFF", "#FF0000"])
        self.assertEqual(clean["style"], {"palette": "ember", "motion": "breathe"})

    def test_builtins_validate_as_custom_and_preview(self):
        for builtin in catalog.BUILTIN_SCREENS:
            fields = {key: builtin[key] for key in lib_mod.SCREEN_KEYS}
            validate_screen(fields, preview=True)
            validate_screen({**fields, "id": CUSTOM})
        for value in catalog.BUILTIN_ART.values():
            validate_art({**value, "id": "art-" + "1" * 16})

    def test_bad_screens(self):
        slots = screen()["slots"]
        bad = [
            screen(id="custom-123"), screen(id="time-big"), screen(id=None), screen(name=""),
            screen(name="x" * 33), screen(name="bad\nname"), screen(layout="huge"),
            screen(slots=slots[:2]), screen(extra=1),
            screen(style={"palette": "rainbow", "motion": "still"}),
            screen(style={"palette": None, "motion": "spin"}),
            screen(style={"palette": None, "motion": "still", "x": 1}),
            screen(based_on="../etc"),
            screen(slots=[{**slots[0], "block": "nope"}, *slots[1:]]),
            screen(slots=[{**slots[0], "color": "red"}, *slots[1:]]),
            screen(slots=[{**slots[0], "color": ["#FFFFFF"]}, *slots[1:]]),
            screen(slots=[{**slots[0], "size": 3}, *slots[1:]]),
            screen(slots=[slots[0], {**slots[1], "options": {"h24": "yes"}}, slots[2]]),
            screen(slots=[slots[0], {**slots[1], "options": {"seconds": True}}, slots[2]]),
            screen(slots=[slots[0], slots[1], {**slots[2], "options": {"which": "tomorrow"}}]),
            screen(slots=[slots[0], slots[1], {**slots[2], "options": {"accent": "#12345"}}]),
            screen(slots=[slots[0], slots[1], {**slots[2], "options": {"accent": ["#FFFFFF", "#FFFFFF"]}}]),
            screen(layout="full", slots=[{"block": "text", "color": None, "options": {"text": "x" * 65}}]),
            screen(layout="full", slots=[{"block": "timer", "color": None, "options": {"work_min": 0}}]),
            screen(layout="full", slots=[{"block": "timer", "color": None, "options": {"work_min": 2.5}}]),
            screen(layout="full", slots=[{"block": "countdown", "color": None, "options": {"date": "2026-02-30"}}]),
            screen(layout="full", slots=[{"block": "art", "color": None, "options": {"art_id": 5}}]),
            screen(layout="full", slots=[{"block": "spark", "color": None, "options": {"feed_id": None}}]),
            [],
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_screen(value)

    def test_preview_screen_allows_unsaved_ids(self):
        for screen_id in ("", None, "time-big", CUSTOM):
            self.assertEqual(validate_screen(screen(id=screen_id, name=""), preview=True)["name"], "Preview")
        missing = screen()
        del missing["id"], missing["name"]
        self.assertIsNone(validate_screen(missing, preview=True)["id"])
        with self.assertRaises(ValueError):
            validate_screen(screen(id="../x"), preview=True)

    def test_art(self):
        self.assertEqual(validate_art(art())["palette"], ["#FF0000", "#00FF00"])
        validate_art(art(w=32, h=16, frames=["." * 512] * 8, fps=12))
        bad = [art(w=8, h=8, frames=["." * 64]), art(frames=["." * 48]), art(frames=["2" + "." * 48]),
               art(frames=["g" + "." * 48]), art(frames=[]), art(frames=["." * 49] * 9),
               art(palette=[]), art(palette=["#FFFFFF"] * 17), art(palette=["white"]),
               art(fps=0), art(fps=13), art(id="art-1"), art(name=" "), art(extra=True)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_art(value)

    def test_feed(self):
        self.assertEqual(validate_feed(feed(url=" https://example.com/x "))["url"], "https://example.com/x")
        minimal = validate_feed({"id": "feed-0123abcd", "name": "X", "url": "http://10.0.0.2/api"})
        self.assertEqual(minimal["interval_s"], 300)
        bad = [feed(url="file:///etc/passwd"), feed(url="https://"), feed(url="https://x/" + "a" * 520),
               feed(interval_s=59), feed(path="a..b"), feed(prefix="x" * 9), feed(id="feed-xyz"),
               feed(extra=1)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_feed(value)

    def test_lineup(self):
        known = set(catalog.BUILTINS) | {CUSTOM}
        moment = {"id": "m-0123abcd", "name": "Evening", "start": "22:00", "end": "06:30",
                  "days": [4, 0], "brightness": 20,
                  "screens": [{"screen_id": CUSTOM, "seconds": 30}]}
        lineup = {"always": [{"screen_id": "time-big", "seconds": 10}], "moments": [moment],
                  "transition": "wipe", "interrupts": {"rain_soon": {"enabled": True, "minutes": 30}}}
        clean = validate_lineup(lineup, known)
        self.assertEqual(clean["moments"][0]["days"], [0, 4])
        self.assertEqual(clean["interrupts"]["rain_soon"], {"enabled": True, "minutes": 30})
        self.assertEqual(clean["interrupts"]["plane_overhead"]["radius_nm"], 3)
        self.assertTrue(clean["interrupts"]["timer_done"]["enabled"])

        def with_moment(**changes):
            return {**lineup, "moments": [{**moment, **changes}]}

        bad = [
            {**lineup, "always": [{"screen_id": "nope", "seconds": 10}]},
            {**lineup, "always": [{"screen_id": "time-big", "seconds": 4}]},
            {**lineup, "always": [{"screen_id": "time-big", "seconds": 301}]},
            {**lineup, "always": [{"screen_id": "time-big", "seconds": 10}] * 21},
            {**lineup, "moments": [moment] * 13},
            {**lineup, "moments": [moment, moment]},
            {**lineup, "transition": "fade"},
            {**lineup, "interrupts": {"meteor": {"enabled": True}}},
            {**lineup, "interrupts": {"plane_overhead": {"enabled": True, "radius_nm": 0}}},
            {**lineup, "interrupts": {"plane_overhead": {"enabled": "yes"}}},
            {**lineup, "interrupts": {"timer_done": {"enabled": True, "minutes": 3}}},
            {**lineup, "extra": 1},
            with_moment(start="24:00"), with_moment(end="6:30"), with_moment(start="06:30"),
            with_moment(days=[1, 1]), with_moment(days=[7]), with_moment(days=[]),
            with_moment(brightness=0), with_moment(brightness=101), with_moment(id="m-1"),
            with_moment(name=""), with_moment(screens=[{"screen_id": "gone", "seconds": 10}]),
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_lineup(value, known)

    def test_library(self):
        lib = default_library()
        lib["screens"] = [screen()]
        lib["art"] = [art()]
        lib["feeds"] = [feed()]
        lib["habits"] = {"focus-streak": ["2027-01-02", "2027-01-01"]}
        lib["timers"] = {CUSTOM: {"state": "running", "phase": "work", "work_min": 25, "break_min": 5,
                                  "ends_at": NOW, "remaining_s": 100, "cycles": 1}}
        lib["pinned"] = {"screen_id": CUSTOM, "until": None}
        lib["lineup"]["always"] = [{"screen_id": CUSTOM, "seconds": 10},
                                   {"screen_id": "clock-weekday", "seconds": 10}]
        clean = validate_library(lib)
        self.assertEqual(clean["habits"]["focus-streak"], ["2027-01-01", "2027-01-02"])
        self.assertEqual(validate_library({"version": 1})["lineup"]["always"][0]["screen_id"], "time-classic")
        bad = [
            {**lib, "version": 2}, {**lib, "extra": {}}, {**lib, "screens": [screen(), screen()]},
            {**lib, "screens": [screen(id="custom-%032x" % i) for i in range(41)]},
            {**lib, "art": [art()] * 2}, {**lib, "feeds": [feed(id="feed-%08x" % i) for i in range(11)]},
            {**lib, "pinned": {"screen_id": "nope", "until": None}},
            {**lib, "pinned": {"screen_id": CUSTOM, "until": "soon"}},
            {**lib, "habits": {"x": ["yesterday"]}},
            {**lib, "timers": {CUSTOM: {**lib["timers"][CUSTOM], "state": "done"}}},
            {**lib, "timers": {CUSTOM: {**lib["timers"][CUSTOM], "ends_at": None}}},
            {**lib, "timers": {CUSTOM: {**lib["timers"][CUSTOM], "work_min": 121}}},
            {**lib, "timers": {"../x": lib["timers"][CUSTOM]}},
            {**lib, "screens": []},  # lineup and pin now point at a missing screen
            [], {"screens": []},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_library(value)

    def test_resolve_screen(self):
        lib = validate_library({"version": 1, "screens": [screen()]})
        self.assertEqual(resolve_screen(lib, CUSTOM)["name"], "Morning glance")
        self.assertEqual(resolve_screen(lib, "sky-radar")["id"], "sky-radar")
        self.assertEqual(resolve_screen(lib, "clock-classic")["id"], "time-classic")
        self.assertIsNone(resolve_screen(lib, "nope"))
        resolve_screen(lib, "sky-radar")["name"] = "changed"
        self.assertEqual(catalog.BUILTINS["sky-radar"]["name"], "Radar")
        ids = all_screen_ids(lib)
        self.assertEqual(ids[0], CUSTOM)
        self.assertIn("time-big", ids)


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.lib = default_library()

    def test_save_and_delete_screen(self):
        new = screen(id="")
        lib = act(self.lib, "save_screen", screen=new)
        saved = lib["screens"][0]
        self.assertRegex(saved["id"], r"^custom-[0-9a-f]{32}$")
        missing_id = dict(new)
        del missing_id["id"]
        lib = act(lib, "save_screen", screen={**new, "id": None})
        self.assertEqual(len(lib["screens"]), 2)
        lib = act(lib, "save_screen", screen={**saved, "name": "Renamed"})
        self.assertEqual([s["name"] for s in lib["screens"]], ["Renamed", "Morning glance"])
        with self.assertRaisesRegex(ValueError, "Built-in"):
            act(lib, "save_screen", screen=screen(id="time-big"))
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            act(lib, "save_screen", screen=screen(id="custom-" + "f" * 32))
        with self.assertRaises(ValueError):
            act(lib, "save_screen", screen={**new, "layout": "nope"})
        with self.assertRaises(ValueError):
            act(lib, "save_screen", screen=new, extra=1)
        # Deleting removes the screen everywhere it is referenced.
        sid = saved["id"]
        lineup = {"always": [{"screen_id": sid, "seconds": 10}, {"screen_id": "time-big", "seconds": 10}],
                  "moments": [{"id": "m-00000000", "name": "Day", "start": "08:00", "end": "17:00",
                               "days": [0], "brightness": None,
                               "screens": [{"screen_id": sid, "seconds": 20}]}]}
        lib = act(lib, "save_lineup", lineup=lineup)
        lib = act(lib, "show_now", screen_id=sid)
        lib = act(lib, "timer", timer_id=sid, op="start")
        lib = act(lib, "delete_screen", screen_id=sid)
        self.assertEqual([s["screen_id"] for s in lib["lineup"]["always"]], ["time-big"])
        self.assertEqual(lib["lineup"]["moments"][0]["screens"], [])
        self.assertIsNone(lib["pinned"])
        self.assertNotIn(sid, lib["timers"])
        with self.assertRaisesRegex(ValueError, "own screens"):
            act(lib, "delete_screen", screen_id="time-big")

    def test_screen_limit(self):
        lib = self.lib
        lib["screens"] = [screen(id="custom-%032x" % i) for i in range(40)]
        with self.assertRaisesRegex(ValueError, "at most 40"):
            act(lib, "save_screen", screen=screen(id=""))

    def test_art_and_feeds(self):
        lib = act(self.lib, "save_art", art=art(id=""))
        art_id = lib["art"][0]["id"]
        self.assertRegex(art_id, r"^art-[0-9a-f]{16}$")
        lib = act(lib, "save_art", art=art(id=art_id, name="Renamed"))
        self.assertEqual(lib["art"][0]["name"], "Renamed")
        with self.assertRaises(ValueError):
            act(lib, "save_art", art=art(id="", frames=["x" * 49]))
        with self.assertRaises(ValueError):
            act(lib, "save_art", art=art(id="art-" + "9" * 16))
        lib = act(lib, "delete_art", art_id=art_id)
        self.assertEqual(lib["art"], [])
        with self.assertRaises(ValueError):
            act(lib, "delete_art", art_id=art_id)

        lib = act(lib, "save_feed", feed=feed(id=""))
        feed_id = lib["feeds"][0]["id"]
        self.assertRegex(feed_id, r"^feed-[0-9a-f]{8}$")
        lib = act(lib, "save_feed", feed=feed(id=feed_id, interval_s=120))
        self.assertEqual(lib["feeds"][0]["interval_s"], 120)
        with self.assertRaises(ValueError):
            act(lib, "save_feed", feed=feed(id="", url="javascript:alert(1)"))
        for i in range(9):
            lib = act(lib, "save_feed", feed=feed(id=""))
        with self.assertRaisesRegex(ValueError, "at most 10"):
            act(lib, "save_feed", feed=feed(id=""))
        lib = act(lib, "delete_feed", feed_id=feed_id)
        self.assertEqual(len(lib["feeds"]), 9)

    def test_lineup_and_pin(self):
        lineup = {"always": [{"screen_id": "sky-radar", "seconds": 12}], "moments": [], "transition": "slide"}
        lib = act(self.lib, "save_lineup", lineup=lineup)
        self.assertEqual(lib["lineup"]["transition"], "slide")
        self.assertIn("iss_overhead", lib["lineup"]["interrupts"])
        with self.assertRaises(ValueError):
            act(lib, "save_lineup", lineup={**lineup, "always": [{"screen_id": "x", "seconds": 12}]})
        lib = act(lib, "show_now", screen_id="time-big")
        self.assertEqual(lib["pinned"], {"screen_id": "time-big", "until": None})
        lib = act(lib, "show_now", screen_id="clock-simple", seconds=60)
        self.assertEqual(lib["pinned"], {"screen_id": "clock-simple", "until": NOW + 60})
        for seconds in (4, 86401, "60", True):
            with self.assertRaises(ValueError):
                act(lib, "show_now", screen_id="time-big", seconds=seconds)
        with self.assertRaises(ValueError):
            act(lib, "show_now", screen_id="nope")
        lib = act(lib, "unpin")
        self.assertIsNone(lib["pinned"])
        with self.assertRaises(ValueError):
            act(lib, "unpin", screen_id="time-big")

    def test_unknown_and_malformed_actions(self):
        for value in ({"action": "explode"}, {}, [], {"action": 3}, {"action": "save_screen"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                apply_action(self.lib, value, now=lambda: NOW)

    def test_action_does_not_mutate_input(self):
        before = copy.deepcopy(self.lib)
        act(self.lib, "show_now", screen_id="time-big")
        self.assertEqual(self.lib, before)

    def test_timer_lifecycle(self):
        lib = act(self.lib, "timer", timer_id="focus-pomodoro", op="start", work_min=10, break_min=2)
        timer = lib["timers"]["focus-pomodoro"]
        self.assertEqual((timer["state"], timer["phase"], timer["ends_at"], timer["cycles"]),
                         ("running", "work", NOW + 600, 0))
        lib = act(lib, "timer", NOW + 100, timer_id="focus-pomodoro", op="pause")
        timer = lib["timers"]["focus-pomodoro"]
        self.assertEqual((timer["state"], timer["ends_at"], timer["remaining_s"]), ("paused", None, 500))
        with self.assertRaisesRegex(ValueError, "not running"):
            act(lib, "timer", timer_id="focus-pomodoro", op="pause")
        lib = act(lib, "timer", NOW + 1000, timer_id="focus-pomodoro", op="resume")
        self.assertEqual(lib["timers"]["focus-pomodoro"]["ends_at"], NOW + 1500)
        with self.assertRaisesRegex(ValueError, "not paused"):
            act(lib, "timer", timer_id="focus-pomodoro", op="resume")
        # Work ended at +1500 and the 2-minute break ended at +1620: back to work.
        lib = act(lib, "timer", NOW + 1630, timer_id="focus-pomodoro", op="skip")
        timer = lib["timers"]["focus-pomodoro"]
        self.assertEqual((timer["phase"], timer["cycles"], timer["ends_at"]), ("break", 2, NOW + 1630 + 120))
        lib = act(lib, "timer", NOW + 1640, timer_id="focus-pomodoro", op="skip")
        timer = lib["timers"]["focus-pomodoro"]
        self.assertEqual((timer["phase"], timer["cycles"], timer["remaining_s"]), ("work", 2, 600))
        lib = act(lib, "timer", NOW + 1700, timer_id="focus-pomodoro", op="reset")
        timer = lib["timers"]["focus-pomodoro"]
        self.assertEqual((timer["state"], timer["phase"], timer["ends_at"], timer["remaining_s"], timer["cycles"]),
                         ("idle", "work", None, 600, 0))
        with self.assertRaisesRegex(ValueError, "Start the timer"):
            act(lib, "timer", timer_id="focus-pomodoro", op="skip")
        for bad in ({"op": "explode"}, {"op": "start", "work_min": 0}, {"op": "start", "break_min": 61},
                    {"op": "start", "timer_id": "../x"}, {"op": "start", "extra": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                act(lib, "timer", **{"timer_id": "focus-pomodoro", **bad})

    def test_timer_defaults_come_from_the_screen(self):
        custom = screen(id=CUSTOM, layout="full", slots=[
            {"block": "timer", "color": None, "options": {"work_min": 50, "break_min": 10}}])
        lib = validate_library({"version": 1, "screens": [custom]})
        lib = act(lib, "timer", timer_id=CUSTOM, op="start")
        self.assertEqual(lib["timers"][CUSTOM]["ends_at"], NOW + 3000)
        lib = act(lib, "timer", timer_id="sky-radar", op="reset")
        self.assertEqual(lib["timers"]["sky-radar"]["work_min"], 25)

    def test_advance_timer_phase_math(self):
        timer = {"state": "running", "phase": "work", "work_min": 25, "break_min": 5,
                 "ends_at": 1500.0, "remaining_s": 1500, "cycles": 0}
        self.assertEqual(advance_timer(timer, 1000)["remaining_s"], 500)
        on_break = advance_timer(timer, 1500)
        self.assertEqual((on_break["phase"], on_break["cycles"], on_break["ends_at"]), ("break", 1, 1800))
        # 3 full cycles plus 10 s into the next work phase.
        later = advance_timer(timer, 1800 + 3 * 1800 + 10)
        self.assertEqual((later["phase"], later["cycles"], later["ends_at"]), ("work", 4, 1800 + 3 * 1800 + 1500))
        days = advance_timer(timer, 1500 + 86400 * 30)
        self.assertGreater(days["ends_at"], 1500 + 86400 * 30)
        paused = {**timer, "state": "paused", "ends_at": None}
        self.assertEqual(advance_timer(paused, 10**9), paused)

    def test_habits(self):
        lib = act(self.lib, "habit", habit_id="focus-streak", date="2027-01-15", done=True)
        lib = act(lib, "habit", habit_id="focus-streak", date="2027-01-14", done=True)
        lib = act(lib, "habit", habit_id="focus-streak", date="2027-01-14", done=True)
        self.assertEqual(lib["habits"]["focus-streak"], ["2027-01-14", "2027-01-15"])
        lib = act(lib, "habit", habit_id="focus-streak", date="2027-01-15", done=False)
        self.assertEqual(lib["habits"]["focus-streak"], ["2027-01-14"])
        # Sixty days later the old date is dropped when the habit next changes.
        later = NOW + 61 * 86400
        lib = act(lib, "habit", later, habit_id="focus-streak", date="2027-03-17", done=True)
        self.assertEqual(lib["habits"]["focus-streak"], ["2027-03-17"])
        lib = act(lib, "habit", later, habit_id="focus-streak", date="2027-03-17", done=False)
        self.assertNotIn("focus-streak", lib["habits"])
        for bad in ({"date": "2026-01-01"}, {"date": "2027-01-20"}, {"date": "15/01/2027"},
                    {"done": "yes"}, {"habit_id": ""}, {"habit_id": "a\nb"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                act(self.lib, "habit", **{"habit_id": "h", "date": "2027-01-15", "done": True, **bad})


class MigrationTests(unittest.TestCase):
    def test_nearby_mode(self):
        lib = migrate_from_settings(validate_settings({"mode": "nearby", "rotate": 12}))
        self.assertEqual(lib["lineup"]["always"], [{"screen_id": "sky-nearby", "seconds": 12}])
        self.assertEqual(lib["screens"], [])

    def test_flight_mode_copies_sky_follow(self):
        lib = migrate_from_settings(validate_settings({"mode": "flight", "flight": "aca150"}))
        (copy_,) = lib["screens"]
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], copy_["id"])
        self.assertEqual(copy_["based_on"], "sky-follow")
        self.assertEqual(copy_["name"], "Follow ACA150")
        self.assertEqual(copy_["slots"][0]["options"]["callsign"], "ACA150")
        self.assertEqual(copy_["slots"][0]["options"]["source"], "follow")
        again = migrate_from_settings(validate_settings({"mode": "flight", "flight": "ACA150"}))
        self.assertEqual(again["screens"][0]["id"], copy_["id"])  # deterministic across services

    def test_clock_mode_builtin_and_legacy_colors(self):
        lib = migrate_from_settings(validate_settings({"mode": "clock", "clock_screen_id": "clock-weekday"}))
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], "time-weekday")
        lib = migrate_from_settings(validate_settings({"mode": "clock"}))
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], "time-classic")
        lib = migrate_from_settings(validate_settings({"mode": "clock", "bottom_color": "#0056D6"}))
        (custom,) = lib["screens"]
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], custom["id"])
        self.assertEqual([slot["color"] for slot in custom["slots"]], ["#FFFFFF", "#0056D6"])

    def test_legacy_custom_screens(self):
        one = {"id": "custom-" + "1" * 32, "name": "Weekday", "rows": [{"content": "weekday", "color": "#33aaff"}]}
        two = {"id": "custom-" + "2" * 32, "name": "Clock", "rows": [
            {"content": "time", "color": "#FFFFFF"}, {"content": "date", "color": "#FFFF00"}]}
        settings = validate_settings({"mode": "clock", "custom_screens": [one, two],
                                      "clock_screen_id": one["id"]})
        lib = migrate_from_settings(settings)
        first, second = lib["screens"]
        self.assertEqual((first["id"], first["layout"], first["slots"]),
                         (one["id"], "full", [{"block": "weekday", "color": "#33AAFF", "options": {}}]))
        self.assertEqual(second["layout"], "two")
        self.assertEqual([slot["block"] for slot in second["slots"]], ["time", "date"])
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], one["id"])
        # Nearby mode keeps the migrated screens but plays the nearby screen.
        nearby = migrate_from_settings(validate_settings({"custom_screens": [one], "clock_screen_id": one["id"]}))
        self.assertEqual(len(nearby["screens"]), 1)
        self.assertEqual(nearby["lineup"]["always"][0]["screen_id"], "sky-nearby")


class PersistenceTests(unittest.TestCase):
    def test_load_creates_from_settings_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            settings = validate_settings({"mode": "flight", "flight": "WJA123"})
            lib = load_library(path, settings)
            self.assertTrue(path.exists())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(load_library(path), lib)
            # Once the file exists, the legacy settings are ignored.
            self.assertEqual(load_library(path, validate_settings({"mode": "nearby"})), lib)
            changed = act(lib, "show_now", screen_id="time-big")
            save_library(changed, path)
            self.assertEqual(json.loads(path.read_text())["pinned"]["screen_id"], "time-big")
            with self.assertRaises(ValueError):
                save_library({**changed, "version": 9}, path)
            self.assertEqual(load_library(path), changed)
            self.assertEqual([p.name for p in Path(directory).iterdir()], ["library.json"])

    def test_invalid_file_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            path.write_text("{not json")
            with self.assertRaisesRegex(ValueError, "library.json is not valid JSON"):
                load_library(path)
            path.write_text('{"version": 1, "screens": "lots"}')
            with self.assertRaisesRegex(ValueError, "library.json is invalid: Save at most"):
                load_library(path)


if __name__ == "__main__":
    unittest.main()
