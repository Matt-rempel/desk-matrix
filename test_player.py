import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import catalog
import player
from player import Player, apply_motion, blend, in_window, resolve_screen, timer_at
from render import BLACK, mix, parse_color
from settings import validate_settings

UTC = ZoneInfo("UTC")
# Friday 2026-10-09 12:00 UTC
FRIDAY_NOON = datetime(2026, 10, 9, 12, 0, tzinfo=UTC).timestamp()


def settings(**extra):
    return validate_settings({"timezone": "UTC", "night_start": "22:00", "night_end": "07:00",
                              **extra})


def text_screen(sid, text, color="#FFFFFF", motion="still"):
    return {"id": sid, "name": sid.upper(), "layout": "full",
            "slots": [{"block": "text", "color": color, "options": {"text": text}}],
            "style": {"palette": None, "motion": motion}, "based_on": None}


class Clock:
    def __init__(self, value=FRIDAY_NOON):
        self.value = value

    def __call__(self):
        return self.value


def library(always=(), moments=(), transition="cut", interrupts=None, pinned=None,
            screens=(), timers=None):
    return {"version": 1, "screens": list(screens), "art": [], "feeds": [], "habits": {},
            "timers": timers or {},
            "lineup": {"always": [{"screen_id": s, "seconds": n} for s, n in always],
                       "moments": list(moments), "transition": transition,
                       "interrupts": interrupts or {}},
            "pinned": pinned}


def lit(pixels):
    return [i for i, p in enumerate(pixels) if p != BLACK]


class HelperTests(unittest.TestCase):
    def test_resolve_screen_order(self):
        custom = text_screen("time-classic", "MINE")
        lib = library(screens=[custom])
        self.assertIs(resolve_screen(lib, "time-classic"), custom)
        self.assertIs(resolve_screen({}, "sky-radar"), catalog.BUILTINS["sky-radar"])
        self.assertIs(resolve_screen({}, "clock-weekday"), catalog.BUILTINS["time-weekday"])
        self.assertIsNone(resolve_screen({}, "nope"))
        self.assertIsNone(resolve_screen({}, None))

    def test_windows_cross_midnight_by_start_day(self):
        friday_late = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
        saturday_early = datetime(2026, 10, 10, 1, 0, tzinfo=UTC)
        saturday_late = datetime(2026, 10, 10, 23, 0, tzinfo=UTC)
        self.assertTrue(in_window("22:00", "06:00", friday_late, [4]))
        self.assertTrue(in_window("22:00", "06:00", saturday_early, [4]))
        self.assertFalse(in_window("22:00", "06:00", saturday_late, [4]))
        self.assertFalse(in_window("22:00", "06:00", datetime(2026, 10, 9, 12, 0, tzinfo=UTC)))
        self.assertTrue(in_window("09:00", "17:00", datetime(2026, 10, 9, 9, 0, tzinfo=UTC), None))
        self.assertFalse(in_window("09:00", "17:00", datetime(2026, 10, 9, 17, 0, tzinfo=UTC)))
        self.assertTrue(in_window("08:00", "08:00", friday_late, [4]))
        self.assertFalse(in_window("bad", "08:00", friday_late))

    def test_timer_phases_roll_from_ends_at(self):
        timer = {"state": "running", "phase": "work", "work_min": 25, "break_min": 5,
                 "ends_at": 1000.0, "remaining_s": None, "cycles": 2}
        self.assertEqual(timer_at(timer, 999)[1], None)
        current, ended = timer_at(timer, 1010)
        self.assertEqual((current["phase"], current["ends_at"], current["cycles"]), ("break", 1300.0, 3))
        self.assertEqual(ended, 1000.0)
        current, ended = timer_at(timer, 1400)
        self.assertEqual((current["state"], current["phase"], current["ends_at"]), ("running", "work", 2800.0))
        self.assertEqual(ended, 1300.0)
        paused = {**timer, "state": "paused", "remaining_s": 60}
        self.assertEqual(timer_at(paused, 5000), (paused, None))


class PlaylistTests(unittest.TestCase):
    def make(self, lib, clock=None, **kw):
        return Player(lib, settings(**kw), now_fn=clock or Clock())

    def test_empty_lineup_shows_time_classic(self):
        for lib in ({}, library(), library(always=[("missing", 10)])):
            _, info = self.make(lib).tick(0, {})
            self.assertEqual(info["screen_id"], "time-classic")
            self.assertIsNone(info["moment"])
            self.assertFalse(info["pinned"])

    def test_always_and_moments(self):
        moments = [
            {"id": "m-1", "name": "Late", "start": "22:00", "end": "06:00", "days": [4],
             "brightness": 20, "screens": [{"screen_id": "night-clock", "seconds": 30}]},
            {"id": "m-2", "name": "Midday", "start": "11:00", "end": "13:00", "days": [4],
             "brightness": None, "screens": [{"screen_id": "weather-now", "seconds": 30}]},
            {"id": "m-3", "name": "Also midday", "start": "11:30", "end": "12:30", "days": [4],
             "brightness": 90, "screens": [{"screen_id": "sky-sun", "seconds": 30}]},
        ]
        clock = Clock()
        p = self.make(library(always=[("time-big", 10)], moments=moments), clock)
        _, info = p.tick(0, {})
        self.assertEqual((info["screen_id"], info["moment"], info["moment_brightness"]),
                         ("weather-now", "Midday", None))
        clock.value = datetime(2026, 10, 10, 1, 0, tzinfo=UTC).timestamp()  # Saturday 01:00
        _, info = p.tick(1, {})
        self.assertEqual((info["screen_id"], info["moment"], info["moment_brightness"]),
                         ("night-clock", "Late", 20))
        clock.value = datetime(2026, 10, 10, 12, 0, tzinfo=UTC).timestamp()  # Saturday noon
        _, info = p.tick(2, {})
        self.assertEqual((info["screen_id"], info["moment"]), ("time-big", None))

    def test_pin_until_and_expiry(self):
        clock = Clock()
        lib = library(always=[("time-big", 10)],
                      pinned={"screen_id": "sky-radar", "until": FRIDAY_NOON + 60})
        p = self.make(lib, clock)
        _, info = p.tick(0, {})
        self.assertEqual(info["screen_id"], "sky-radar")
        self.assertTrue(info["pinned"])
        self.assertEqual(info["pin"], {"screen_id": "sky-radar", "until": FRIDAY_NOON + 60})
        clock.value += 61
        _, info = p.tick(1, {})
        self.assertEqual(info["screen_id"], "time-big")
        self.assertFalse(info["pinned"])
        self.assertIsNone(info["pin"])
        lib["pinned"] = {"screen_id": "sky-sun", "until": None}
        p.set_library(lib)
        self.assertEqual(p.tick(2, {})[1]["screen_id"], "sky-sun")
        lib["pinned"] = {"screen_id": "unknown-screen", "until": None}
        self.assertEqual(p.tick(3, {})[1]["screen_id"], "time-big")

    def test_rotation_timing_and_elapsed_reset(self):
        p = self.make(library(always=[("time-big", 5), ("sky-sun", 7)]))
        expected = [(0, "time-big"), (4.9, "time-big"), (5.0, "sky-sun"), (11.9, "sky-sun"),
                    (12.0, "time-big"), (17.0, "sky-sun")]
        for when, screen_id in expected:
            self.assertEqual(p.tick(when, {})[1]["screen_id"], screen_id, when)
        self.assertEqual(p._screen_started, 17.0)
        # A single-item lineup never restarts its screen.
        single = self.make(library(always=[("time-big", 5)]))
        single.tick(0, {})
        single.tick(30, {})
        self.assertEqual(single._screen_started, 0)

    def test_lineup_resumes_after_pin(self):
        clock = Clock()
        lib = library(always=[("time-big", 5), ("sky-sun", 5)])
        p = self.make(lib, clock)
        p.tick(0, {})
        p.tick(6, {})  # sky-sun
        lib["pinned"] = {"screen_id": "sky-radar", "until": None}
        self.assertEqual(p.tick(7, {})[1]["screen_id"], "sky-radar")
        lib["pinned"] = None
        _, info = p.tick(100, {})
        self.assertEqual(info["screen_id"], "sky-sun")
        self.assertEqual(p.tick(104.9, {})[1]["screen_id"], "sky-sun")


class EffectTests(unittest.TestCase):
    A = text_screen("custom-a", "AAA", "#FF0000")
    B = text_screen("custom-b", "BB", "#00FF00")

    def frames(self, transition):
        lib = library(always=[("custom-a", 5), ("custom-b", 5)], transition=transition,
                      screens=[self.A, self.B])
        p = Player(lib, settings(), now_fn=Clock())
        p.tick(0, {})
        old = p.tick(4.99, {})[0]
        return p, old

    def pure(self, screen):
        p = Player(library(always=[(screen["id"], 10)], screens=[screen]), settings(), now_fn=Clock())
        return p.tick(0, {})[0]

    def test_each_transition_blends_then_lands_on_new_frame(self):
        new = self.pure(self.B)
        for kind, duration in (("slide", 0.4), ("dissolve", 0.5), ("wipe", 0.6)):
            p, old = self.frames(kind)
            self.assertTrue(old == self.pure(self.A))
            self.assertTrue(p.tick(5.0, {})[0] == old, kind)  # the transition starts here
            self.assertEqual(p.tick(5.0, {})[1]["screen_id"], "custom-b")
            middle = p.tick(5.0 + duration / 2, {})[0]
            self.assertTrue(middle != old and middle != new, kind)
            self.assertTrue(p.tick(5.0 + duration, {})[0] == new, kind)
        p, _ = self.frames("cut")
        self.assertTrue(p.tick(5.0, {})[0] == new)

    def test_blend_math(self):
        old = [(200, 0, 0)] * 512
        new = [(0, 0, 200)] * 512
        self.assertEqual(blend(old, new, "dissolve", 0.5), [mix(old[0], new[0], 0.5)] * 512)
        wiped = blend(old, new, "wipe", 0.5)
        self.assertEqual(sum(p == new[0] for p in wiped), 256)
        self.assertEqual(blend(old, new, "wipe", 0.5), wiped)  # fixed order
        old_cols = [(x, 0, 0) for _ in range(16) for x in range(32)]
        slid = blend(old_cols, new, "slide", 0.5)
        self.assertEqual(slid[:16], old_cols[16:32])
        self.assertEqual(slid[16:32], new[:16])
        self.assertEqual(blend(old, new, "cut", 0.1), new)
        self.assertEqual(blend(old, new, "dissolve", 1.0), new)

    def test_motions(self):
        base = [BLACK] * 512
        base[5 * 32 + 3] = (200, 100, 0)
        base[6 * 32 + 10] = (0, 200, 0)
        self.assertIs(apply_motion(base, "still", 1), base)
        dim = apply_motion(base, "breathe", 3.0)  # sin = -1 -> 70 %
        self.assertEqual(dim[5 * 32 + 3], (140, 70, 0))
        self.assertEqual(apply_motion(base, "breathe", 1.0)[5 * 32 + 3], (200, 100, 0))
        self.assertEqual(lit(apply_motion(base, "slide", 0.0)), [])
        partial = apply_motion(base, "slide", 0.1)
        self.assertTrue(lit(partial))
        self.assertGreater(lit(partial)[0] % 32, 3)
        self.assertEqual(apply_motion(base, "slide", 0.4), base)
        changed = set()
        for step in range(20):
            frame = apply_motion(base, "sparkle", step * player.SPARKLE_STEP_S + player.SPARKLE_STEP_S / 2)
            diff = [i for i in range(512) if frame[i] != base[i]]
            self.assertLessEqual(len(diff), player.SPARKLE_COUNT)
            for i in diff:
                self.assertNotEqual(base[i], BLACK)
                self.assertGreaterEqual(sum(frame[i]), sum(base[i]))
            changed.update(diff)
        self.assertTrue(changed)

    def test_screen_motion_and_new_screen_elapsed(self):
        screen = text_screen("custom-s", "HI", motion="slide")
        p = Player(library(always=[("custom-s", 10)], screens=[screen]), settings(), now_fn=Clock())
        first = p.tick(0, {})[0]
        settled = p.tick(1, {})[0]
        self.assertEqual(lit(first), [])
        self.assertTrue(lit(settled))

    def test_night_palette(self):
        clock = Clock(datetime(2026, 10, 9, 23, 0, tzinfo=UTC).timestamp())
        lib = library(always=[("time-classic", 10)])
        day = Player(lib, settings(), now_fn=clock).tick(0, {})[0]
        self.assertIn(parse_color(catalog.INK), day)
        self.assertEqual(Player(lib, settings(night_enabled=True), now_fn=clock).tick(0, {})[0], day)
        night = Player(lib, settings(night_palette=True, night_enabled=True), now_fn=clock).tick(0, {})[0]
        red = parse_color(catalog.PALETTES["night"]["primary"])
        self.assertIn(red, night)
        for pixel in night:
            self.assertTrue(pixel == BLACK or (pixel[0] >= pixel[1] and pixel[0] >= pixel[2]), pixel)
        clock.value = FRIDAY_NOON
        noon = Player(lib, settings(night_palette=True, night_enabled=True), now_fn=clock).tick(0, {})[0]
        self.assertIn(parse_color(catalog.INK), noon)


class InterruptTests(unittest.TestCase):
    PLANE = {"callsign": "WJA123", "route": "YYC>YVR", "distance_nm": 2.0, "altitude_ft": 5000,
             "speed_kt": 200, "icon": "plane", "bearing_deg": 90.0}
    FAR = {"callsign": "ACA150", "route": None, "distance_nm": 9.0, "altitude_ft": 5000}

    def make(self, interrupts, clock=None, **kw):
        lib = library(always=[("time-big", 10)], interrupts=interrupts, **kw)
        return Player(lib, settings(), now_fn=clock or Clock()), lib

    def test_plane_overhead_once_per_callsign_per_hour(self):
        p, _ = self.make({"plane_overhead": {"enabled": True, "radius_nm": 3,
                                             "max_alt_ft": 10000, "seconds": 15}})
        data = {"aircraft": {"nearby": [self.FAR, self.PLANE], "tracked": None}}
        _, info = p.tick(0, data)
        self.assertEqual((info["screen_id"], info["interrupt"]), ("sky-nearby", "plane_overhead"))
        focused = p._screen_data(p._interrupt["screen"], data)
        self.assertEqual([x["callsign"] for x in focused["aircraft"]["nearby"]], ["WJA123"])
        self.assertEqual(p.tick(14.9, data)[1]["interrupt"], "plane_overhead")
        self.assertEqual(p.tick(15.0, data)[1]["screen_id"], "time-big")
        self.assertIsNone(p.tick(1000, data)[1]["interrupt"])
        self.assertEqual(p.tick(3601, data)[1]["interrupt"], "plane_overhead")
        high = {"aircraft": {"nearby": [{**self.PLANE, "callsign": "HIGH1", "altitude_ft": 30000}]}}
        self.assertIsNone(p.tick(4000, high)[1]["interrupt"])
        off, _ = self.make({"plane_overhead": {"enabled": False, "radius_nm": 3,
                                               "max_alt_ft": 10000, "seconds": 15}})
        self.assertIsNone(off.tick(0, data)[1]["interrupt"])

    def test_pi_hot_repeats_while_hot_and_rearms_when_cool(self):
        p, _ = self.make({"pi_hot": {"enabled": True, "threshold_c": 75}})
        hot = {"health": {"cpu_temp_c": 77.0}}
        _, info = p.tick(0, hot)
        self.assertEqual((info["screen_id"], info["interrupt"]), ("sys-hot", "pi_hot"))
        self.assertEqual(p.tick(player.ALERT_SHOW_S, hot)[1]["screen_id"], "time-big")
        self.assertIsNone(p.tick(300, hot)[1]["interrupt"])  # repeats every 10 minutes
        self.assertEqual(p.tick(600, hot)[1]["interrupt"], "pi_hot")
        warm = {"health": {"cpu_temp_c": 72.0}}  # below the threshold but not 5° below
        self.assertIsNone(p.tick(700, warm)[1]["interrupt"])
        self.assertIsNone(p.tick(710, hot)[1]["interrupt"])  # still waiting out the repeat
        cool = {"health": {"cpu_temp_c": 65.0}}
        self.assertIsNone(p.tick(720, cool)[1]["interrupt"])
        self.assertEqual(p.tick(730, hot)[1]["interrupt"], "pi_hot")  # re-armed
        off, _ = self.make({"pi_hot": {"enabled": False, "threshold_c": 75}})
        self.assertIsNone(off.tick(0, hot)[1]["interrupt"])

    def test_power_offline_and_disk_alerts(self):
        p, _ = self.make({"pi_power": {"enabled": True}, "offline": {"enabled": True, "minutes": 5},
                          "disk_low": {"enabled": True, "percent": 10}})
        self.assertEqual(p.tick(0, {"health": {"under_voltage": True, "throttled": False}})[1]["screen_id"],
                         "sys-power")
        self.assertIsNone(p.tick(20, {"health": {"offline_s": 120}})[1]["interrupt"])
        self.assertEqual(p.tick(40, {"health": {"offline_s": 300}})[1]["screen_id"], "sys-offline")
        self.assertEqual(p.tick(60, {"health": {"disk_free_pct": 4.0}})[1]["screen_id"], "sys-disk")
        self.assertIsNone(p.tick(80, {"health": {"disk_free_pct": 4.0, "offline_s": 400,
                                                  "under_voltage": True}})[1]["interrupt"])
        self.assertTrue({"health", "net"} <= p.needs())

    def test_rain_soon_once_per_hour(self):
        p, _ = self.make({"rain_soon": {"enabled": True, "minutes": 30}})
        dry = {"weather": {"rain_in_min": None}}
        self.assertIsNone(p.tick(0, dry)[1]["interrupt"])
        wet = {"weather": {"rain_in_min": 12}}
        _, info = p.tick(1, wet)
        self.assertEqual((info["screen_id"], info["interrupt"]), ("weather-rain", "rain_soon"))
        self.assertEqual(p.tick(1 + player.RAIN_SHOW_S, wet)[1]["screen_id"], "time-big")
        self.assertIsNone(p.tick(1800, wet)[1]["interrupt"])
        self.assertEqual(p.tick(3602, wet)[1]["interrupt"], "rain_soon")
        later = {"weather": {"rain_in_min": 45}}
        q, _ = self.make({"rain_soon": {"enabled": True, "minutes": 30}})
        self.assertIsNone(q.tick(0, later)[1]["interrupt"])

    def test_iss_once_per_pass(self):
        p, _ = self.make({"iss_overhead": {"enabled": True}})
        over = {"iss": {"overhead": True}}
        away = {"iss": {"overhead": False}}
        _, info = p.tick(0, over)
        self.assertEqual((info["screen_id"], info["interrupt"]), ("sky-iss", "iss_overhead"))
        self.assertIsNone(p.tick(20, over)[1]["interrupt"])
        self.assertIsNone(p.tick(21, {})[1]["interrupt"])  # no data keeps the pass state
        self.assertIsNone(p.tick(22, over)[1]["interrupt"])
        p.tick(30, away)
        self.assertEqual(p.tick(40, over)[1]["interrupt"], "iss_overhead")

    def test_timer_done_flashes_then_shows_timer(self):
        clock = Clock()
        timers = {"focus-pomodoro": {"state": "running", "phase": "work", "work_min": 25,
                                     "break_min": 5, "ends_at": FRIDAY_NOON + 1,
                                     "remaining_s": None, "cycles": 0}}
        p, _ = self.make({"timer_done": {"enabled": True}}, clock, timers=timers)
        self.assertIsNone(p.tick(0, {})[1]["interrupt"])
        clock.value += 2
        pixels, info = p.tick(10, {})
        self.assertEqual((info["screen_id"], info["interrupt"]), ("focus-pomodoro", "timer_done"))
        self.assertEqual(len(lit(pixels)), 512)
        self.assertEqual(lit(p.tick(10.3, {})[0]), [])
        self.assertEqual(len(lit(p.tick(10.5, {})[0])), 512)
        pixels, info = p.tick(11.6, {})
        self.assertEqual(info["interrupt"], "timer_done")
        self.assertLess(len(lit(pixels)), 512)
        # The timer screen now shows the break phase computed from ends_at.
        ctx = p._context(p._local(clock.value), clock.value, 0, {})
        self.assertEqual(ctx.timers["focus-pomodoro"]["phase"], "break")
        self.assertEqual(ctx.timers["focus-pomodoro"]["cycles"], 1)
        self.assertEqual(p.tick(10 + 1.5 + player.TIMER_SHOW_S, {})[1]["screen_id"], "time-big")
        self.assertIsNone(p.tick(20, {})[1]["interrupt"])  # once per phase end
        clock.value = FRIDAY_NOON + 1 + 300 + 1  # break ends
        self.assertEqual(p.tick(30, {})[1]["interrupt"], "timer_done")

    def test_timer_that_ended_long_ago_does_not_flash(self):
        timers = {"focus-pomodoro": {"state": "running", "phase": "work", "work_min": 25,
                                     "break_min": 5, "ends_at": FRIDAY_NOON - 3500,  # last phase ended 1400 s ago
                                     "remaining_s": None, "cycles": 0}}
        p, _ = self.make({"timer_done": {"enabled": True}}, timers=timers)
        self.assertIsNone(p.tick(0, {})[1]["interrupt"])

    def test_pin_wins_over_interrupts(self):
        p, lib = self.make({"rain_soon": {"enabled": True, "minutes": 30}},
                           pinned={"screen_id": "sky-sun", "until": None})
        wet = {"weather": {"rain_in_min": 5}}
        _, info = p.tick(0, wet)
        self.assertEqual((info["screen_id"], info["interrupt"]), ("sky-sun", None))
        lib["pinned"] = None
        self.assertEqual(p.tick(1, wet)[1]["interrupt"], "rain_soon")


class NeedsTests(unittest.TestCase):
    def test_needs_cover_playlist_pin_soon_and_interrupts(self):
        clock = Clock()
        moments = [{"id": "m-1", "name": "Soon", "start": "12:01", "end": "13:00", "days": None,
                    "brightness": None, "screens": [{"screen_id": "weather-metar", "seconds": 10}]}]
        lib = library(always=[("sky-radar", 10), ("weather-now", 10)], moments=moments)
        p = Player(lib, settings(), now_fn=clock)
        self.assertEqual(p.needs(), {"aircraft:nearby", "weather", "metar:CYYC"})
        clock.value += 3600 * 3
        self.assertEqual(p.needs(), {"aircraft:nearby", "weather"})
        lib["pinned"] = {"screen_id": "sky-iss", "until": None}
        self.assertIn("iss", p.needs())
        lib["pinned"] = None
        lib["lineup"]["always"] = [{"screen_id": "time-classic", "seconds": 10}]
        self.assertEqual(p.needs(), set())
        lib["lineup"]["interrupts"] = {"plane_overhead": {"enabled": True}, "timer_done": {"enabled": True},
                                       "rain_soon": {"enabled": True}, "iss_overhead": {"enabled": False}}
        self.assertEqual(p.needs(), {"aircraft:nearby", "weather"})
        follow = {**catalog.BUILTINS["sky-follow"], "id": "custom-" + "f" * 32}
        follow["slots"] = [{**follow["slots"][0], "options": {"source": "follow", "callsign": "ac150"}}]
        lib["screens"] = [follow]
        lib["lineup"]["always"] = [{"screen_id": follow["id"], "seconds": 10}]
        self.assertIn("aircraft:follow:AC150", p.needs())

    def test_follow_screen_sees_its_own_tracked_flight(self):
        follow = {**catalog.BUILTINS["sky-follow"], "id": "custom-" + "f" * 32}
        follow["slots"] = [{**follow["slots"][0], "options": {"source": "follow", "callsign": "WJA9"}}]
        p = Player(library(screens=[follow]), settings(), now_fn=Clock())
        data = {"aircraft": {"nearby": [], "tracked": {"callsign": "AC150"},
                             "follow": {"AC150": {"callsign": "AC150"}, "WJA9": {"callsign": "WJA9"}}}}
        self.assertEqual(p._screen_data(follow, data)["aircraft"]["tracked"], {"callsign": "WJA9"})
        self.assertIs(p._screen_data(catalog.BUILTINS["time-big"], data), data)


if __name__ == "__main__":
    unittest.main()
