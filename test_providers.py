from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
from zoneinfo import ZoneInfo

import providers
from providers import Providers

UTC = timezone.utc
EDMONTON = ZoneInfo("America/Edmonton")
NOW = datetime(2026, 10, 9, 16, 24, tzinfo=UTC).timestamp()  # 10:24 local


@dataclass(frozen=True)
class FakeSettings:
    lat: float = 51.08
    lon: float = -114.22
    timezone: str = "America/Edmonton"
    calendar_ics_url: str = "https://example.com/cal.ics"
    temp_unit: str = "C"


class InlineExecutor:
    """Runs submitted work immediately so tests are deterministic."""

    def __init__(self):
        self.calls = 0

    def submit(self, fn, *args):
        self.calls += 1
        future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:  # pragma: no cover - _run never raises
            future.set_exception(exc)
        return future

    def shutdown(self, *args, **kwargs):
        pass


class Clock:
    def __init__(self, wall: float = NOW):
        self.wall = wall
        self.mono = 1000.0

    def advance(self, seconds: float) -> None:
        self.wall += seconds
        self.mono += seconds


def weather_payload(now: float = NOW) -> dict:
    hour = now - now % 3600
    day = datetime(2026, 10, 9, tzinfo=EDMONTON).timestamp()
    quarter = now - now % 900
    return {
        "utc_offset_seconds": -21600,
        "current": {"time": now - 300, "temperature_2m": 14.2, "weather_code": 2, "is_day": 1},
        "daily": {"time": [day, day + 86400], "temperature_2m_max": [18.0, 12.0],
                  "temperature_2m_min": [4.0, 1.0]},
        "hourly": {"time": [hour + 3600 * i for i in range(-3, 30)],
                   "temperature_2m": [float(i) for i in range(-3, 30)],
                   "precipitation": [0.0] * 33},
        "minutely_15": {"time": [quarter + 900 * i for i in range(0, 16)],
                        "precipitation": [0, 0, 0.05, 0, 0.4] + [0] * 11},
    }


METAR_PAYLOAD = [{
    "icaoId": "CYYC", "obsTime": NOW - 600, "reportTime": "2026-10-09T16:00:00.000Z",
    "wdir": 320, "wspd": 12, "wgst": 22, "visib": "6+",
    "clouds": [{"cover": "FEW", "base": 4000}, {"cover": "BKN", "base": 2500}],
}]

ISS_PAYLOAD = {"latitude": 55.0, "longitude": -100.0, "altitude": 420, "timestamp": NOW - 2}

ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nDTSTART:20261009T140000Z\r\nSUMMARY:Past\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTSTART;TZID=America/Edmonton:20261009T150000\r\n"
    "SUMMARY:Design review with a very long title that is\r\n  folded\\, twice\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def patch_fetch(json_map: dict | None = None, text: str | None = None, error: Exception | None = None):
    def fake_json(url, timeout=providers.FETCH_TIMEOUT):
        if error:
            raise error
        for needle, payload in (json_map or {}).items():
            if needle in url:
                return json.loads(json.dumps(payload))
        raise urllib.error.URLError("no fixture")

    def fake_text(url, timeout=providers.FETCH_TIMEOUT):
        if error:
            raise error
        return text

    return mock.patch.multiple(providers, _get_json=fake_json, _get_text=fake_text)


class ProviderTestCase(unittest.TestCase):
    def make(self, settings=None, state_dir=None):
        self.clock = Clock()
        self.executor = InlineExecutor()
        self.cpu = Path(self.enterContext(tempfile.TemporaryDirectory())) / "temp"
        self.cpu.write_text("48312\n")
        return Providers(settings or FakeSettings(), state_dir, executor=self.executor,
                         now_fn=lambda: self.clock.wall, monotonic_fn=lambda: self.clock.mono,
                         cpu_path=self.cpu)


class WeatherTests(ProviderTestCase):
    def test_wmo_mapping(self):
        cases = {0: "sun", 1: "sun", 2: "cloud", 3: "cloud", 45: "fog", 48: "fog", 51: "rain",
                 61: "rain", 66: "rain", 80: "rain", 71: "snow", 77: "snow", 85: "snow",
                 95: "storm", 99: "storm"}
        for code, icon in cases.items():
            self.assertEqual(providers.wmo_icon(code), icon, code)
        self.assertEqual(providers.wmo_icon(0, is_day=False), "moon")
        self.assertEqual(providers.wmo_icon(3, is_day=False), "cloud")
        self.assertIsNone(providers.wmo_icon(None))

    def test_weather_snapshot(self):
        p = self.make()
        with patch_fetch({"open-meteo": weather_payload()}):
            p.update({"weather"}, [])
        weather = p.snapshot()["weather"]
        self.assertEqual(weather["temp_c"], 14.2)
        self.assertEqual((weather["high_c"], weather["low_c"]), (18.0, 4.0))
        self.assertEqual(weather["code"], "cloud")
        self.assertEqual(weather["hourly_c"], [float(i) for i in range(12)])
        # 0.4 mm in the slot ending quarter+3600 starts at quarter+2700 → 36 min from 16:24
        self.assertEqual(weather["rain_in_min"], 36)
        self.assertEqual(weather["age_s"], 300)
        self.clock.advance(60)
        self.assertEqual(p.snapshot()["weather"]["age_s"], 360)

    def test_no_rain_and_hourly_fallback(self):
        payload = weather_payload()
        payload["minutely_15"]["precipitation"] = [0] * 16
        self.assertIsNone(providers.parse_weather(payload, NOW)["rain_in_min"])
        del payload["minutely_15"]
        hour = NOW - NOW % 3600
        payload["hourly"]["precipitation"][5] = 1.2  # slot ending hour+2h covers hour+1h..+2h
        self.assertEqual(providers.parse_weather(payload, NOW)["rain_in_min"], 36)
        self.assertEqual(payload["hourly"]["time"][5], hour + 7200)

    def test_url_has_location(self):
        url = providers.weather_url(51.08, -114.22, "America/Edmonton")
        self.assertIn("latitude=51.0800", url)
        self.assertIn("timezone=America%2FEdmonton", url)
        self.assertIn("minutely_15=precipitation", url)


class MetarTests(ProviderTestCase):
    def test_category_derivation(self):
        fc = providers.flight_category
        self.assertEqual(fc(10, None), "VFR")
        self.assertEqual(fc(5, None), "MVFR")
        self.assertEqual(fc(10, 3000), "MVFR")
        self.assertEqual(fc(2.5, 5000), "IFR")
        self.assertEqual(fc(10, 800), "IFR")
        self.assertEqual(fc(0.5, None), "LIFR")
        self.assertEqual(fc(10, 400), "LIFR")
        self.assertIsNone(fc(None, None))
        self.assertEqual(providers._visibility_sm("1 1/2"), 1.5)
        self.assertEqual(providers._visibility_sm("10+"), 10)

    def test_parse_and_snapshot(self):
        p = self.make()
        with patch_fetch({"aviationweather.gov": METAR_PAYLOAD}):
            p.update({"metar:cyyc", "metar:bad!", "metar:TOOLONG"}, [])
        self.assertEqual(self.executor.calls, 1)
        entry = p.snapshot()["metar"]["CYYC"]
        self.assertEqual(entry, {"station": "CYYC", "category": "MVFR", "wind_dir": 320,
                                 "wind_kt": 12, "gust_kt": 22,
                                 "observed_at": "2026-10-09T16:14:00Z", "age_s": 600})

    def test_reported_category_and_variable_wind(self):
        report = dict(METAR_PAYLOAD[0], fltCat="IFR", wdir="VRB", wgst=None)
        entry = providers.parse_metar([report], "CYYC")
        self.assertEqual((entry["category"], entry["wind_dir"], entry["gust_kt"]), ("IFR", "VRB", None))
        with self.assertRaises(ValueError):
            providers.parse_metar([], "CYYC")


class IssTests(ProviderTestCase):
    def test_distance_and_direction(self):
        p = self.make()
        with patch_fetch({"wheretheiss": ISS_PAYLOAD}):
            p.update({"iss"}, [])
        iss = p.snapshot()["iss"]
        self.assertAlmostEqual(iss["distance_km"], 1045, delta=15)
        self.assertEqual(iss["direction"], "NE")
        self.assertTrue(iss["overhead"])
        self.assertEqual(iss["updated_at"], "2026-10-09T16:23:58Z")
        far = providers.parse_iss({"latitude": -30, "longitude": 150}, 51.08, -114.22, NOW)
        self.assertFalse(far["overhead"])

    def test_compass(self):
        self.assertEqual([providers.compass8(b) for b in (0, 44, 90, 135, 180, 225, 270, 315, 350)],
                         ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"])
        distance, bearing = providers.great_circle(0, 0, 0, 1)
        self.assertAlmostEqual(distance, 111.19, places=1)
        self.assertAlmostEqual(bearing, 90)


class SunTests(unittest.TestCase):
    def assertNear(self, actual: datetime, expected: datetime, minutes: float = 3):
        self.assertLess(abs((actual - expected).total_seconds()), minutes * 60, (actual, expected))

    def test_calgary_published_times(self):
        # NOAA solar calculator values for 51.08 N, 114.22 W (UTC).
        rise, sset, polar = providers.sun_times(51.08, -114.22, date(2026, 12, 21), EDMONTON)
        self.assertIsNone(polar)
        self.assertNear(rise, datetime(2026, 12, 21, 15, 38, tzinfo=UTC))
        self.assertNear(sset, datetime(2026, 12, 21, 23, 32, tzinfo=UTC))
        rise, sset, _ = providers.sun_times(51.08, -114.22, date(2026, 6, 21), EDMONTON)
        self.assertNear(rise, datetime(2026, 6, 21, 11, 22, tzinfo=UTC))
        self.assertNear(sset, datetime(2026, 6, 22, 3, 55, tzinfo=UTC))

    def test_sun_info_daytime(self):
        info = providers.sun_info(51.08, -114.22, "America/Edmonton",
                                  datetime.fromtimestamp(NOW, UTC))
        self.assertEqual(info["next_event"], "sunset")
        self.assertEqual(info["next_at"], info["sunset"])
        self.assertGreater(info["daylight_progress"], 0.15)
        self.assertLess(info["daylight_progress"], 0.3)
        night = providers.sun_info(51.08, -114.22, "America/Edmonton",
                                   datetime(2026, 10, 10, 5, 0, tzinfo=UTC))
        self.assertIsNone(night["daylight_progress"])
        self.assertEqual(night["next_event"], "sunrise")

    def test_polar_day_and_night(self):
        summer = providers.sun_info(78.2, 15.6, "Arctic/Longyearbyen", datetime(2026, 6, 21, 12, tzinfo=UTC))
        self.assertEqual(summer["polar"], "day")
        self.assertIsNone(summer["sunrise"])
        self.assertIsNotNone(summer["daylight_progress"])
        self.assertEqual(summer["next_event"], "sunset")
        winter = providers.sun_info(78.2, 15.6, "Arctic/Longyearbyen", datetime(2026, 12, 21, 12, tzinfo=UTC))
        self.assertEqual(winter["polar"], "night")
        self.assertIsNone(winter["daylight_progress"])
        self.assertEqual(winter["next_event"], "sunrise")


class CalendarTests(ProviderTestCase):
    def test_folding_tzid_and_escapes(self):
        events = providers.parse_ics(ICS, EDMONTON)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["title"], "Design review with a very long title that is folded, twice")
        self.assertEqual(events[1]["start"], datetime(2026, 10, 9, 15, tzinfo=EDMONTON))
        nxt = providers.next_event(events, datetime.fromtimestamp(NOW, UTC))
        self.assertEqual(nxt["start"], providers.iso_utc(datetime(2026, 10, 9, 15, tzinfo=EDMONTON)))

    def test_all_day_and_floating(self):
        text = ("BEGIN:VEVENT\nDTSTART;VALUE=DATE:20261011\nSUMMARY:Holiday\nEND:VEVENT\n"
                "BEGIN:VEVENT\nDTSTART:20261012T090000\nSUMMARY:Floating\nEND:VEVENT\n"
                "BEGIN:VEVENT\nDTSTART:20261010T090000Z\nSUMMARY:Cancelled\nSTATUS:CANCELLED\nEND:VEVENT\n"
                "BEGIN:VEVENT\nDTSTART:20261030T090000Z\nSUMMARY:Too far\nEND:VEVENT\n")
        events = providers.parse_ics(text, EDMONTON)
        self.assertEqual(len(events), 3)
        self.assertTrue(events[0]["all_day"])
        self.assertEqual(events[0]["start"], datetime(2026, 10, 11, tzinfo=EDMONTON))
        self.assertEqual(events[1]["start"], datetime(2026, 10, 12, 9, tzinfo=EDMONTON))
        nxt = providers.next_event(events, datetime.fromtimestamp(NOW, UTC))
        self.assertEqual((nxt["title"], nxt["all_day"]), ("Holiday", True))
        self.assertIsNone(providers.next_event(events[2:], datetime.fromtimestamp(NOW, UTC)))

    def test_weekly_rrule_with_byday(self):
        text = ("BEGIN:VEVENT\nDTSTART;TZID=America/Edmonton:20260105T093000\n"
                "RRULE:FREQ=WEEKLY;BYDAY=MO,TH\nEXDATE;TZID=America/Edmonton:20261012T093000\n"
                "SUMMARY:Standup\nEND:VEVENT\n")
        events = providers.parse_ics(text, EDMONTON)
        now = datetime.fromtimestamp(NOW, UTC)  # Friday Oct 9
        nxt = providers.next_event(events, now)
        # Monday Oct 12 is excluded, so Thursday Oct 15 is next.
        self.assertEqual(nxt["start"], providers.iso_utc(datetime(2026, 10, 15, 9, 30, tzinfo=EDMONTON)))

    def test_rrule_interval_count_until(self):
        now = datetime.fromtimestamp(NOW, UTC)
        def nxt(rule, start="20260928T120000Z"):
            text = f"BEGIN:VEVENT\nDTSTART:{start}\nRRULE:{rule}\nSUMMARY:R\nEND:VEVENT\n"
            return providers.next_event(providers.parse_ics(text, EDMONTON), now)
        self.assertEqual(nxt("FREQ=DAILY")["start"], "2026-10-10T12:00:00Z")
        self.assertEqual(nxt("FREQ=DAILY;INTERVAL=3")["start"], "2026-10-10T12:00:00Z")
        self.assertEqual(nxt("FREQ=WEEKLY;INTERVAL=2")["start"], "2026-10-12T12:00:00Z")
        self.assertIsNone(nxt("FREQ=DAILY;COUNT=5"))
        self.assertEqual(nxt("FREQ=DAILY;COUNT=13")["start"], "2026-10-10T12:00:00Z")
        self.assertIsNone(nxt("FREQ=DAILY;UNTIL=20261009T000000Z"))
        self.assertEqual(nxt("FREQ=DAILY;UNTIL=20261010")["start"], "2026-10-10T12:00:00Z")
        self.assertIsNone(nxt("FREQ=MONTHLY"))  # unsupported rules are not expanded
        self.assertEqual(nxt("FREQ=DAILY", start="20200101T120000Z")["start"], "2026-10-10T12:00:00Z")

    def test_provider_calendar(self):
        p = self.make()
        with patch_fetch(text=ICS):
            p.update({"calendar"}, [])
        cal = p.snapshot()["calendar"]
        self.assertEqual(cal["next"]["title"][:6], "Design")
        self.assertEqual(cal["updated_at"], "2026-10-09T16:24:00Z")
        self.clock.advance(6 * 3600)  # event started; nothing else this week
        self.assertIsNone(p.snapshot()["calendar"]["next"])

    def test_calendar_needs_url(self):
        p = self.make(FakeSettings(calendar_ics_url=""))
        p.update({"calendar"}, [])
        self.assertEqual(self.executor.calls, 0)
        with self.assertRaises(ValueError):
            providers._get_text("file:///etc/passwd")


class FeedTests(ProviderTestCase):
    FEED = {"id": "feed-1a2b3c4d", "url": "https://example.com/btc.json", "path": "data.0.price",
            "series_path": "data.0.history", "prefix": "$", "suffix": "", "interval_s": 120}

    def test_extract_path(self):
        data = {"data": [{"price": 1.5, "nested": {"x": "y"}}]}
        self.assertEqual(providers.extract_path(data, "data.0.price"), 1.5)
        self.assertEqual(providers.extract_path(data, "data.0.nested.x"), "y")
        self.assertIs(providers.extract_path(data, ""), data)
        for bad in ("data.1.price", "data.x", "missing", "data.0.price.deeper"):
            with self.assertRaises(KeyError):
                providers.extract_path(data, bad)

    def test_format_value(self):
        fv = providers.format_value
        self.assertEqual(fv(67123.45), "67123")
        self.assertEqual(fv(1.50), "1.5")
        self.assertEqual(fv(100.0), "100")
        self.assertEqual(fv(1234567), "1.23M")
        self.assertEqual(fv("42.50", "$", "/h"), "$42.5/h")
        self.assertEqual(fv("Delayed"), "Delayed")
        self.assertEqual(fv("007"), "007")
        self.assertEqual(fv(True), "ON")
        self.assertEqual(fv(None), "--")

    def test_feed_value_series_and_error(self):
        p = self.make()
        payload = {"data": [{"price": "67123.40", "history": list(range(40)) + ["x"]}]}
        with patch_fetch({"btc.json": payload}):
            p.update({"feed:feed-1a2b3c4d", "feed:unknown"}, [self.FEED])
        feed = p.snapshot()["feeds"]["feed-1a2b3c4d"]
        self.assertEqual(feed["value"], "$67123")
        self.assertEqual(feed["series"], [float(i) for i in range(8, 40)])
        self.assertIsNone(feed["error"])
        self.assertEqual(self.executor.calls, 1)
        self.clock.advance(120)
        with patch_fetch({"btc.json": {"data": []}}):
            p.update({"feed:feed-1a2b3c4d"}, [self.FEED])
        feed = p.snapshot()["feeds"]["feed-1a2b3c4d"]
        self.assertEqual(feed["value"], "$67123")  # last good value kept
        self.assertEqual(feed["error"], "path not found")
        self.assertEqual(feed["updated_at"], "2026-10-09T16:24:00Z")

    def test_interval_floor_and_config_change(self):
        p = self.make()
        feed = dict(self.FEED, interval_s=5)
        with patch_fetch({"btc.json": {"data": [{"price": 1}]}}):
            p.update({"feed:feed-1a2b3c4d"}, [feed])
            self.clock.advance(30)
            p.update({"feed:feed-1a2b3c4d"}, [feed])
            self.assertEqual(self.executor.calls, 1)
            self.clock.advance(31)
            p.update({"feed:feed-1a2b3c4d"}, [feed])
            self.assertEqual(self.executor.calls, 2)
            p.update({"feed:feed-1a2b3c4d"}, [dict(feed, suffix="%")])
            self.assertEqual(self.executor.calls, 3)
        self.assertEqual(p.snapshot()["feeds"]["feed-1a2b3c4d"]["value"], "$1%")


class SchedulingTests(ProviderTestCase):
    def test_only_needed_and_interval(self):
        p = self.make()
        with patch_fetch({"open-meteo": weather_payload()}):
            p.update({"weather", "sun", "health", "timers", "aircraft:nearby"}, [])
            self.assertEqual(self.executor.calls, 1)
            self.clock.advance(899)
            p.update({"weather"}, [])
            self.assertEqual(self.executor.calls, 1)
            self.clock.advance(1)
            p.update({"weather"}, [])
            self.assertEqual(self.executor.calls, 2)
        snap = p.snapshot()
        self.assertNotIn("iss", snap)
        self.assertIn("sun", snap)

    def test_backoff_keeps_last_value(self):
        p = self.make()
        with patch_fetch({"wheretheiss": ISS_PAYLOAD}):
            p.update({"iss"}, [])
        good = p.snapshot()["iss"]
        delays = []
        with patch_fetch(error=urllib.error.URLError(TimeoutError())):
            for _ in range(8):
                self.clock.advance(10_000)  # always due
                p.update({"iss"}, [])
                source = p._sources["iss"]
                delays.append(source.next_due - self.clock.mono)
        self.assertEqual(delays, [60, 120, 240, 480, 960, 1800, 1800, 1800])
        self.assertEqual(p._sources["iss"].error, "timeout")
        self.assertEqual(p.snapshot()["iss"], good)
        calls = self.executor.calls
        self.clock.advance(1799)
        p.update({"iss"}, [])
        self.assertEqual(self.executor.calls, calls)
        with patch_fetch({"wheretheiss": ISS_PAYLOAD}):
            self.clock.advance(1)
            p.update({"iss"}, [])
        self.assertEqual(p._sources["iss"].failures, 0)

    def test_error_text(self):
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        self.assertEqual(providers._error_text(err), "HTTP 429")

    def test_update_does_not_block(self):
        release = threading.Event()
        started = threading.Event()

        def slow(url, timeout=providers.FETCH_TIMEOUT):
            started.set()
            release.wait(5)
            return ISS_PAYLOAD

        executor = ThreadPoolExecutor(max_workers=3)
        p = Providers(FakeSettings(calendar_ics_url=""), None, executor=executor)
        try:
            with mock.patch.object(providers, "_get_json", slow):
                begin = time.monotonic()
                p.update({"iss", "weather"}, [])
                p.update({"iss", "weather"}, [])  # in flight: not scheduled twice
                self.assertLess(time.monotonic() - begin, 0.5)
                self.assertTrue(started.wait(2))
                self.assertNotIn("iss", p.snapshot())
                release.set()
                executor.shutdown(wait=True)
            self.assertIn("iss", p.snapshot())
        finally:
            release.set()
            p.close()

    def test_location_change_invalidates(self):
        p = self.make()
        with patch_fetch({"open-meteo": weather_payload(), "wheretheiss": ISS_PAYLOAD,
                          "aviationweather": METAR_PAYLOAD}):
            p.update({"weather", "iss", "metar:CYYC"}, [])
        p.set_settings(FakeSettings(lat=49.28, lon=-123.12, timezone="America/Vancouver"))
        snap = p.snapshot()
        self.assertNotIn("weather", snap)
        self.assertNotIn("iss", snap)
        self.assertIn("CYYC", snap["metar"])
        with patch_fetch({"open-meteo": weather_payload()}) as _:
            p.update({"weather"}, [])
        self.assertIn("weather", p.snapshot())
        p.set_settings(FakeSettings(lat=49.28, lon=-123.12, timezone="America/Vancouver"))
        self.assertIn("weather", p.snapshot())  # unchanged settings keep caches


class HealthTests(ProviderTestCase):
    def test_health_values(self):
        p = self.make()
        pick = lambda h: {k: h[k] for k in ("cpu_temp_c", "net_ok", "feed_age_s")}
        self.assertEqual(pick(p.snapshot()["health"]), {"cpu_temp_c": 48.3, "net_ok": None, "feed_age_s": None})
        with patch_fetch({"open-meteo": weather_payload()}):
            p.update({"weather", "health"}, [])
        self.clock.advance(120)
        self.assertEqual(pick(p.snapshot()["health"]), {"cpu_temp_c": 48.3, "net_ok": True, "feed_age_s": 120})
        self.clock.advance(600)
        self.assertFalse(p.snapshot()["health"]["net_ok"])
        p.mark_network_ok()
        self.assertTrue(p.snapshot()["health"]["net_ok"])
        self.assertIsNone(providers.cpu_temp_c(Path("/nonexistent/thermal")))

    def test_throttling_and_disk(self):
        flags = Path(self.enterContext(tempfile.TemporaryDirectory())) / "get_throttled"
        flags.write_text("0x50005\n")  # under-voltage and throttled now, plus history bits
        self.assertEqual(providers.throttle_flags(flags), {"under_voltage": True, "throttled": True})
        flags.write_text("50000")  # only "has happened since boot" bits
        self.assertEqual(providers.throttle_flags(flags), {"under_voltage": False, "throttled": False})
        self.assertIsNone(providers.throttle_flags(Path("/nonexistent/get_throttled")))
        self.assertIsNone(providers.disk_free_pct("/nonexistent/path"))
        free = providers.disk_free_pct("/")
        self.assertTrue(0 <= free <= 100)

    def test_offline_probe(self):
        p = self.make()
        self.assertEqual(p.snapshot()["health"]["offline_s"], 0)
        with mock.patch.object(providers, "probe_network", side_effect=OSError("unreachable")):
            p.update({"net"}, [])
            self.clock.advance(300)
            self.assertEqual(p.snapshot()["health"]["offline_s"], 300)
            p.update({"net"}, [])  # retried every minute, not backed off
            self.clock.advance(60)
            p.update({"net"}, [])
        self.assertEqual(p.snapshot()["health"]["offline_s"], 360)
        with mock.patch.object(providers, "probe_network", return_value={}):
            self.clock.advance(60)
            p.update({"net"}, [])
        self.assertEqual(p.snapshot()["health"]["offline_s"], 0)

    def test_seed_from_state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "data.json").write_text(json.dumps({
                "weather": {"temp_c": 3.0, "observed_at": "2026-10-09T16:00:00Z"},
                "metar": {"CYYC": {"station": "CYYC", "category": "VFR"}},
                "feeds": {"feed-1": {"value": "$1", "series": [1.0]}}}))
            os.utime(Path(tmp, "data.json"), (NOW, NOW))
            p = self.make(state_dir=tmp)
            snap = p.snapshot()
        self.assertEqual(snap["weather"]["temp_c"], 3.0)
        self.assertEqual(snap["weather"]["age_s"], 1440)
        self.assertEqual(snap["metar"]["CYYC"]["category"], "VFR")
        self.assertEqual(snap["feeds"]["feed-1"]["value"], "$1")

    def test_close(self):
        p = Providers(FakeSettings(), None)
        p.close()
        p.update({"weather"}, [])  # ignored after close


if __name__ == "__main__":
    unittest.main()
