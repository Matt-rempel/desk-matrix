import io
import json
import stat
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import flightboard as app
from settings import CALGARY_TIME, Settings, effective_brightness, load_settings, save_settings, validate_settings


class FlightboardTests(unittest.TestCase):
    def test_font_and_scrolling_fit_panel(self):
        self.assertTrue(all(len(rows) == 7 and all(len(row) == 5 for row in rows)
                            for rows in app.FONT.values()))
        self.assertEqual(app.scroll_offset("WJA1162", 0), 0)
        self.assertEqual(app.scroll_offset("WJA1162", 10),
                         32 - app.text_width("WJA1162"))
        self.assertEqual(len(app.frame("WJA1162", "04NM 6KFT", 5)), 512)

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

    def test_clock_uses_selected_timezone_and_fits_two_rows(self):
        settings = validate_settings({"mode": "clock", "timezone": "America/Edmonton"})
        instant = datetime(2026, 10, 9, 5, 7, tzinfo=timezone.utc)
        top, bottom = app.clock_lines(settings, instant)
        self.assertEqual((top, bottom), ("23:07", "THU OCT 8"))
        self.assertLessEqual(app.text_width(top), 32)
        self.assertGreater(app.text_width(bottom), 32)
        self.assertEqual(len(app.frame(top, bottom)), 512)
        self.assertNotEqual(tuple(app.FONT[":"]), tuple(app.FONT[" "]))
        self.assertLess(app.scroll_offset(bottom, app.clock_scroll_period(bottom) - 2), 0)
        self.assertEqual(app.scroll_offset(bottom, 0), 0)

    def test_progress_icon_and_dots(self):
        plane = app.Aircraft("ACA150", "c00001", 10, 25000, 400,
                             lat=0, lon=5)
        info = app.Metadata(route="AAA-BBB", origin_position=(0, 0),
                            destination_position=(0, 10))
        self.assertAlmostEqual(app.route_progress(plane, info), .5, places=2)
        self.assertEqual(app.icon_for(plane, info), "maple")
        pixels = app.frame("ACA150", "AAA-BBB", 0, settings=Settings(),
                           progress=.5, icon="maple")
        self.assertEqual(pixels[15 * 32], app.rgb(Settings().accent_color))
        self.assertNotEqual(pixels[15 * 32 + 20], app.rgb(Settings().accent_color))
        dots = app.frame("ACA150", "AAA-BBB", 0, dots=3, active_dot=1)
        self.assertEqual(sum(pixel != (0, 0, 0) for pixel in dots[15 * 32:]), 6)

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


if __name__ == "__main__":
    unittest.main()
