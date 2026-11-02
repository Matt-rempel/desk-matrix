import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import Future

import flightboard as app
from flight_lookup import normalize_flight, request_flight, requested_flight, REQUEST_NAME
from settings import Settings
from test_flightboard import InlineExecutor, Ticker


class FlightLookupTests(unittest.TestCase):
    def test_formats_and_expiry(self):
        for value in ("ws2231", "WS 2231", "WS-2231", " WS2231 "):
            self.assertEqual(normalize_flight(value), "WS2231")
        for value in (None, "1234", "https://example.com", "WS/2231", "A", "A" * 11):
            with self.assertRaises(ValueError):
                normalize_flight(value)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with patch("flight_lookup.time.time", return_value=1000):
                request_flight(directory, "ws 2231")
            self.assertEqual(requested_flight(directory, 1001), "WS2231")
            self.assertIsNone(requested_flight(directory, 1120))
            for bad in ([], {}, {"callsign": "WS1", "expires_at": float("inf")},
                        {"callsign": "WS1", "expires_at": 99999}):
                (directory / REQUEST_NAME).write_text(json.dumps(bad))
                self.assertIsNone(requested_flight(directory, 1000))

    def test_not_seen_and_feed_error_are_separate_and_original_query_is_retried(self):
        clock = Ticker()
        provider = app.AircraftProvider(Settings(), executor=InlineExecutor(), monotonic_fn=clock)
        with patch("flightboard.fetch_tracked_aircraft", return_value=(None, "DAL4113")) as fetch:
            provider.update({"aircraft:follow:DL4113"})
            status = provider.snapshot()["follow_status"]["DL4113"]
            self.assertEqual(status["state"], "not_seen")
            self.assertEqual(status["resolved"], "DAL4113")
            clock.value += 21
            provider.update({"aircraft:follow:DL4113"})
            self.assertEqual(fetch.call_args.args[0], "DL4113")
        clock.value += 21
        with patch("flightboard.fetch_tracked_aircraft", side_effect=OSError("offline")):
            provider.update({"aircraft:follow:DL4113"})
        self.assertEqual(provider.snapshot()["follow_status"]["DL4113"]["state"], "error")

    def test_pending_lookup_is_not_a_missing_flight(self):
        class PendingExecutor:
            def submit(self, *args):
                return Future()
        provider = app.AircraftProvider(Settings(), executor=PendingExecutor())
        provider.update({"aircraft:follow:WS2231"})
        self.assertEqual(provider.snapshot()["follow_status"]["WS2231"]["state"], "checking")
