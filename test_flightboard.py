import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import flightboard as app
import render
from settings import CALGARY_TIME, Settings, effective_brightness, load_settings, save_settings, validate_settings


class FlightboardTests(unittest.TestCase):
    def test_font_is_shared_with_renderer(self):
        self.assertTrue(all(len(rows) == 7 and all(len(row) == 5 for row in rows)
                            for rows in app.FONT.values()))
        self.assertIs(app.FONT, render.FONT)

    def test_feed_keeps_airborne_recent_aircraft(self):
        data = {"ac": [
            {"flight": "WEN3373 ", "hex": "c07f39", "lat": app.DEFAULT_LAT,
             "lon": app.DEFAULT_LON, "seen_pos": 2, "alt_baro": 6500,
             "gs": 140, "t": "DH8D"},
            {"flight": "PARKED", "hex": "c00000", "lat": app.DEFAULT_LAT,
             "lon": app.DEFAULT_LON, "seen_pos": 1, "alt_baro": "ground", "gs": 0},
            {"flight": "STALE", "hex": "c00001", "lat": app.DEFAULT_LAT,
             "lon": app.DEFAULT_LON, "seen_pos": 45, "alt_baro": 9000, "gs": 100},
        ]}
        with patch("flightboard.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(data).encode())):
            result = app.fetch_aircraft(app.DEFAULT_LAT, app.DEFAULT_LON, 25)
        self.assertEqual([aircraft.callsign for aircraft in result], ["WEN3373"])
        self.assertEqual(result[0].aircraft_type, "DH8D")

    def test_malformed_provider_rows_are_ignored(self):
        self.assertEqual(app.parse_aircraft([], 0, 0, 20), [])
        self.assertEqual(app.parse_aircraft({"ac": [None, [], "bad", {}]}, 0, 0, 20), [])
        self.assertEqual(app.parse_aircraft({"ac": [{"flight": "BAD", "lat": float("nan"),
                                                     "lon": 0, "seen_pos": 1,
                                                     "alt_baro": 5000}]}, 0, 0, 20), [])
        self.assertEqual(app.parse_metadata([]), app.Metadata())
        self.assertEqual(app.parse_metadata({"response": []}), app.Metadata())
        malformed = io.BytesIO(b'[]')
        with patch("flightboard.urllib.request.urlopen", return_value=malformed):
            self.assertEqual(app.fetch_tracked_aircraft("ACA150", 0, 0), (None, "ACA150"))

    def test_adsb_calls_are_serialized(self):
        active = 0
        peak = 0
        lock = threading.Lock()
        starts = []
        def fake_open(_request, timeout):
            nonlocal active, peak
            import time
            with lock:
                active += 1
                peak = max(peak, active)
                starts.append(time.monotonic())
            time.sleep(.04)
            with lock:
                active -= 1
            return io.BytesIO(b'{"ac": []}')
        with patch("flightboard.urllib.request.urlopen", side_effect=fake_open):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(app.fetch_aircraft, 0, 0, 20)
                second = pool.submit(app._fetch_callsign, "ACA150", 0, 0)
                first.result()
                second.result()
        self.assertEqual(peak, 1)
        self.assertGreaterEqual(starts[1] - starts[0], 1.0)

    def test_combined_metadata_and_two_pages(self):
        payload = {"response": {
            "aircraft": {"icao_type": "DH8D"},
            "flightroute": {
                "callsign_iata": "WS3373",
                "airline": {"name": "WestJet Encore"},
                "origin": {"iata_code": "YMM"},
                "destination": {"iata_code": "YYC"},
            },
        }}
        info = app.parse_metadata(payload)
        aircraft = app.Aircraft("WEN3373", "c07f39", 7.2, 6500, 140)
        self.assertEqual(info.route, "YMM-YYC")
        self.assertEqual(app.detail(aircraft, info, 0), ("WS3373", "YMM-YYC"))
        self.assertEqual(app.detail(aircraft, info, 1),
                         ("WestJet Encore DH8D", "07NM 6KFT 140KT"))

    def test_selection_includes_nearest_and_airline_flights(self):
        flights = [
            app.Aircraft("CGPXG", "c00001", 4, 7000, 120),
            app.Aircraft("CFIAH", "c00002", 6, 7000, 120),
            app.Aircraft("SDE150", "c00003", 11, 7000, 120),
            app.Aircraft("WJA615", "c00004", 12, 7000, 120),
        ]
        self.assertEqual([a.callsign for a in app.select_flights(flights)],
                         ["CGPXG", "SDE150", "WJA615"])

    def test_route_lookup_falls_back_when_hex_unknown(self):
        aircraft = app.Aircraft("WEN3373", "c07f39", 7.2, 6500, 140)
        missing = HTTPError("https://api.adsbdb.com", 404, "unknown", {}, None)
        route = {"response": {"flightroute": {
            "origin": {"iata_code": "YMM"},
            "destination": {"iata_code": "YYC"},
        }}}
        with patch("flightboard.urllib.request.urlopen",
                   side_effect=[missing, io.BytesIO(json.dumps(route).encode())]) as get:
            result = app.lookup_metadata(aircraft)
        self.assertEqual(result.route, "YMM-YYC")
        self.assertEqual(get.call_count, 2)

    def test_settings_round_trip_and_night_schedule(self):
        value = validate_settings({"mode": "flight", "flight": "aca150",
                                   "brightness": 85, "night_enabled": True})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_settings(value, path)
            self.assertEqual(load_settings(path).flight, "ACA150")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            save_settings(validate_settings({"display_enabled": False}), path)
            self.assertFalse(load_settings(path).display_enabled)
            path.write_text('{"brightness": 55}')  # Settings saved before the power button existed.
            self.assertTrue(load_settings(path).display_enabled)
        self.assertEqual(effective_brightness(value, datetime(2026, 10, 8, 23, 0,
                                                              tzinfo=CALGARY_TIME)), 30)
        self.assertEqual(effective_brightness(value, datetime(2026, 10, 8, 12, 0,
                                                              tzinfo=CALGARY_TIME)), 85)
        london = validate_settings({"night_enabled": True, "timezone": "Europe/London"})
        self.assertEqual(effective_brightness(london, datetime(2026, 10, 8, 22, 0,
                                                               tzinfo=CALGARY_TIME)), 30)
        with self.assertRaisesRegex(ValueError, "Time zone"):
            validate_settings({"timezone": "../bad"})
        self.assertFalse(validate_settings({"display_enabled": False}).display_enabled)
        with self.assertRaisesRegex(ValueError, "display_enabled"):
            validate_settings({"display_enabled": "off"})
        with self.assertRaisesRegex(ValueError, "Flight must"):
            validate_settings({"mode": "flight", "flight": "../etc"})

    def test_progress_and_icon(self):
        plane = app.Aircraft("ACA150", "c00001", 10, 25000, 400,
                             lat=0, lon=5)
        info = app.Metadata(route="AAA-BBB", origin_position=(0, 0),
                            destination_position=(0, 10))
        self.assertAlmostEqual(app.route_progress(plane, info), .5, places=2)
        self.assertEqual(app.icon_for(plane, info), "maple")

    def test_tracked_flight_query_uses_global_callsign(self):
        data = {"ac": [{"flight": "ACA150", "hex": "c00001", "lat": 50.0,
                        "lon": -80.0, "seen_pos": 2, "alt_baro": 25000,
                        "gs": 420}]}
        with patch("flightboard.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps(data).encode())) as get:
            found, alias = app.fetch_tracked_aircraft("ACA150", app.DEFAULT_LAT,
                                                      app.DEFAULT_LON)
        self.assertEqual(found.callsign, "ACA150")
        self.assertEqual(alias, "ACA150")
        self.assertIn("/v2/callsign/ACA150", get.call_args.args[0].full_url)



class InlineExecutor:
    """Runs submitted work immediately so tests need no threads or network."""

    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append(fn)
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future

    def shutdown(self, **_kwargs):
        pass


class Ticker:
    def __init__(self, step=0.0, start=1000.0):
        self.value, self.step = start, step

    def __call__(self):
        self.value += self.step
        return self.value


class AircraftProviderTests(unittest.TestCase):
    HOME = (51.0, -114.0)

    def provider(self, clock=None, **settings):
        base = {"lat": self.HOME[0], "lon": self.HOME[1], "radius": 25, "max_planes": 2}
        base.update(settings)
        self.successes = 0

        def ok():
            self.successes += 1

        self.executor = InlineExecutor()
        return app.AircraftProvider(validate_settings(base), 20, executor=self.executor,
                                    monotonic_fn=clock or Ticker(), now_fn=lambda: 1_760_000_000.0,
                                    on_success=ok)

    def test_bearing_math(self):
        lat, lon = self.HOME
        self.assertAlmostEqual(app.bearing_deg(lat, lon, lat + 0.1, lon), 0, places=3)
        self.assertAlmostEqual(app.bearing_deg(lat, lon, lat, lon + 0.1), 90, delta=0.1)
        self.assertAlmostEqual(app.bearing_deg(lat, lon, lat - 0.1, lon), 180, places=3)
        self.assertAlmostEqual(app.bearing_deg(lat, lon, lat, lon - 0.1), 270, delta=0.1)
        self.assertAlmostEqual(app.bearing_deg(0, 0, 1, 1), 45, delta=0.1)

    def test_nearby_snapshot_shape_and_cadence(self):
        lat, lon = self.HOME
        planes = [app.Aircraft("CGABC", "c00001", 2.0, 4000, 110, None, lat, lon + 0.05),
                  app.Aircraft("WJA123", "c00002", 5.04, 12000, 250, "B738", lat + 0.08, lon)]
        meta = app.Metadata(route="YYC-YVR", iata_callsign="WS123")
        clock = Ticker()
        provider = self.provider(clock)
        self.assertIsNone(provider.snapshot())
        with patch("flightboard.fetch_aircraft", return_value=planes) as fetch, \
                patch("flightboard.lookup_metadata", return_value=meta) as lookup:
            provider.update({"aircraft:nearby", "weather"})
            provider.update({"aircraft:nearby"})
            self.assertEqual(fetch.call_count, 1)
            fetch.assert_called_with(lat, lon, 25)
            self.assertEqual(lookup.call_count, 1)
            clock.value += 21
            provider.update({"aircraft:nearby"})
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(lookup.call_count, 2)
        snap = provider.snapshot()
        self.assertEqual(set(snap), {"nearby", "tracked", "follow", "updated_at", "error"})
        self.assertIsNone(snap["tracked"])
        self.assertIsNone(snap["error"])
        first, second = snap["nearby"]
        self.assertEqual(first["callsign"], "CGABC")
        self.assertEqual(round(first["bearing_deg"]), 90)
        self.assertEqual(first["route"], "YYC>YVR")
        self.assertEqual(second, {"callsign": "WJA123", "route": "YYC>YVR", "distance_nm": 5.0,
                                  "altitude_ft": 12000, "speed_kt": 250, "icon": "westjet",
                                  "bearing_deg": 0.0})
        self.assertEqual(self.successes, 2)
        json.dumps(snap)

    def test_follow_snapshot_and_errors(self):
        plane = app.Aircraft("ACA150", "c00003", 300, 34000, 450, "A320", 0.0, 5.0)
        meta = app.Metadata(route="AAA-BBB", iata_callsign="AC150",
                            origin_position=(0.0, 0.0), destination_position=(0.0, 10.0))
        provider = self.provider()
        with patch("flightboard.fetch_tracked_aircraft", return_value=(plane, "ACA150")) as track, \
                patch("flightboard.lookup_metadata", return_value=meta):
            provider.update({"aircraft:follow:AC150"})
        track.assert_called_once_with("AC150", *self.HOME)
        snap = provider.snapshot()
        tracked = snap["tracked"]
        self.assertEqual(snap["follow"], {"AC150": tracked})
        self.assertEqual((tracked["callsign"], tracked["icao"], tracked["origin"],
                          tracked["destination"], tracked["icon"]),
                         ("AC150", "ACA150", "AAA", "BBB", "maple"))
        self.assertAlmostEqual(tracked["progress"], 0.5, places=2)
        self.assertAlmostEqual(tracked["remaining_min"], 300 / 450 * 60, delta=2)
        self.assertIsNone(snap["nearby"])
        failing = self.provider()
        with patch("flightboard.fetch_aircraft", side_effect=OSError("down")):
            failing.update({"aircraft:nearby"})
        snap = failing.snapshot()
        self.assertEqual((snap["nearby"], snap["error"]), (None, "down"))
        self.assertEqual(self.successes, 0)

    def test_location_change_discards_nearby(self):
        provider = self.provider()
        with patch("flightboard.fetch_aircraft", return_value=[]), \
                patch("flightboard.lookup_metadata", return_value=None):
            provider.update({"aircraft:nearby"})
        self.assertEqual(provider.snapshot()["nearby"], [])
        provider.set_settings(validate_settings({"lat": 10, "lon": 10}))
        self.assertIsNone(provider.snapshot())


class FakeCanvas:
    def __init__(self):
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)


class FakeMatrix:
    def __init__(self):
        self.brightness = 100
        self.swaps = 0
        self.clears = 0
        self.canvas = FakeCanvas()

    def CreateFrameCanvas(self):
        return self.canvas

    def SwapOnVSync(self, canvas):
        self.swaps += 1
        return canvas

    def Clear(self):
        self.clears += 1


class FakeProviders:
    def __init__(self):
        self.updates = []

    def update(self, needs, feeds):
        self.updates.append((set(needs), list(feeds)))

    def snapshot(self):
        return {"health": {"cpu_temp_c": 40.0, "net_ok": True, "feed_age_s": 7},
                "weather": {"temp_c": 3.0, "age_s": 120}}

    def set_settings(self, settings):
        self.settings = settings

    def mark_network_ok(self):
        pass

    def close(self):
        pass


class RunLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.settings_path = self.dir / "settings.json"
        self.library_path = self.dir / "library.json"
        self.libraries = []

    def tearDown(self):
        self.tmp.cleanup()

    def args(self):
        return app.parse_args(["--settings", str(self.settings_path),
                               "--library", str(self.library_path)])

    def fake_load(self, path, settings):
        return self.libraries.pop(0) if len(self.libraries) > 1 else self.libraries[0]

    def run_loop(self, frames, sleep=lambda _s: None, step=0.05):
        matrix = FakeMatrix()
        aircraft = app.AircraftProvider(Settings(), executor=InlineExecutor())
        with patch("flightboard.load_library", side_effect=self.fake_load):
            app.run(matrix, self.args(), stop_after=frames, state_dir=self.dir,
                    providers=FakeProviders(), aircraft=aircraft,
                    monotonic=Ticker(step), sleep=sleep)
        return matrix

    @staticmethod
    def lineup(screen_id, **extra):
        return {"lineup": {"always": [{"screen_id": screen_id, "seconds": 10}], "moments": [],
                           "transition": "cut", "interrupts": {}}, "pinned": None, **extra}

    def test_loop_pushes_changed_frames_and_writes_status_and_data(self):
        save_settings(validate_settings({"brightness": 40}), self.settings_path)
        self.libraries = [self.lineup("time-classic")]
        matrix = self.run_loop(700, step=0.05)  # ~35 s of frames
        self.assertGreaterEqual(matrix.swaps, 1)
        self.assertLess(matrix.swaps, 10)  # a still clock is only redrawn when it changes
        self.assertEqual(matrix.brightness, 40)
        self.assertTrue(any(value != (0, 0, 0) for value in matrix.canvas.pixels.values()))
        status = json.loads((self.dir / "status.json").read_text())
        self.assertEqual(status["mode"], "lineup")
        self.assertEqual(status["state"], "live")
        self.assertEqual((status["screen_id"], status["title"]), ("time-classic", "Classic"))
        self.assertEqual(status["detail"], "Always on")
        self.assertIsNone(status["pinned"])
        self.assertIsNone(status["moment"])
        self.assertEqual(len(status["frame"]), 3072)
        self.assertEqual(status["frame"], status["frame"].lower())
        self.assertEqual(status["data_age"]["weather"], 120)
        self.assertEqual(status["nearby"], [])
        data = json.loads((self.dir / "data.json").read_text())
        self.assertEqual(data["health"]["feed_age_s"], 7)
        self.assertEqual(stat.S_IMODE((self.dir / "data.json").stat().st_mode), 0o640)

    def test_display_off_blanks_and_reports_off(self):
        save_settings(validate_settings({"display_enabled": False}), self.settings_path)
        self.libraries = [self.lineup("time-classic")]
        matrix = self.run_loop(5)
        self.assertEqual(matrix.swaps, 0)
        self.assertGreaterEqual(matrix.clears, 1)
        status = json.loads((self.dir / "status.json").read_text())
        self.assertEqual((status["state"], status["title"]), ("off", "DISPLAY OFF"))
        self.assertEqual(status["frame"], "0" * 3072)

    def test_library_reload_on_change(self):
        save_settings(Settings(), self.settings_path)
        self.library_path.write_text("{}")
        pinned = self.lineup("time-classic", pinned={"screen_id": "sky-sun", "until": None})
        self.libraries = [self.lineup("time-classic"), pinned]
        calls = []

        def sleep(_seconds):
            calls.append(1)
            if len(calls) == 3:
                stamp = self.library_path.stat().st_mtime_ns + 5_000_000_000
                os.utime(self.library_path, ns=(stamp, stamp))

        self.run_loop(80, sleep=sleep, step=0.1)
        status = json.loads((self.dir / "status.json").read_text())
        self.assertEqual(status["screen_id"], "sky-sun")
        self.assertEqual(status["pinned"], {"screen_id": "sky-sun", "until": None})
        self.assertEqual(status["detail"], "Pinned")

    def test_build_status_shapes(self):
        info = {"screen_id": "sky-follow", "screen_name": "Follow a flight", "moment": "Morning",
                "pinned": False, "pin": None, "interrupt": None, "moment_brightness": 50}
        data = {"aircraft": {"nearby": [{"callsign": "WJA1", "distance_nm": 3.0, "altitude_ft": 9000,
                                         "route": "YYC>YVR", "icon": "plane"}],
                             "tracked": {"progress": 0.42}, "updated_at": "2026-10-09T16:00:00+00:00",
                             "error": None},
                "health": {"net_ok": True, "feed_age_s": 3}}
        now = datetime(2026, 10, 9, 16, 0, 30, tzinfo=timezone.utc).timestamp()
        status = app.build_status(Settings(), info, [(255, 0, 0)] * 512, data, now)
        self.assertEqual(status["progress_percent"], 42)
        self.assertEqual(status["detail"], "Morning")
        self.assertEqual(status["moment"], "Morning")
        self.assertEqual(status["nearby"], [{"callsign": "WJA1", "distance_nm": 3.0,
                                             "altitude_ft": 9000, "route": "YYC>YVR"}])
        self.assertEqual(status["data_age"], {"aircraft": 30, "weather": None, "metar": None,
                                              "iss": None, "calendar": None})
        self.assertEqual(status["frame"][:6], "ff0000")
        pinned = app.build_status(Settings(), {**info, "pinned": True,
                                               "pin": {"screen_id": "x", "until": None}}, [], {}, now)
        self.assertIsNone(pinned["moment"])
        self.assertEqual(pinned["pinned"], {"screen_id": "x", "until": None})


if __name__ == "__main__":
    unittest.main()
