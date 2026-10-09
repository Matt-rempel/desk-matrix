import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import web_server


class WebServerTests(unittest.TestCase):
    def test_clock_screen_library_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            token_path = Path(directory) / "web-token"
            token_path.write_text("a" * 64)
            with (patch.object(web_server, "DEFAULT_PATH", path),
                  patch.object(web_server, "TOKEN_PATH", token_path)):
                server = web_server.BoundedHTTPServer(("127.0.0.1", 0), web_server.Handler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"

                def post(endpoint, value):
                    request = Request(base + endpoint, json.dumps(value).encode(),
                                      {"Content-Type": "application/json", "Origin": base,
                                       "X-Flightboard-Key": "a" * 64})
                    with urlopen(request) as response:
                        return json.load(response)

                try:
                    request = Request(base + "/api/screens",
                                      headers={"X-Flightboard-Key": "a" * 64})
                    with urlopen(request) as response:
                        self.assertEqual(len(json.load(response)["builtins"]), 3)
                    cloned = post("/api/screens", {"action": "clone", "source_id": "clock-classic"})
                    custom_id = cloned["clock_screen_id"]
                    self.assertEqual(cloned["mode"], "clock")
                    self.assertEqual(len(cloned["custom_screens"]), 1)
                    screen = {"id": custom_id, "name": "Weekday", "rows": [
                        {"content": "weekday", "color": "#33aaff"}]}
                    saved = post("/api/screens", {"action": "save", "screen": screen})
                    self.assertEqual(saved["custom_screens"][0]["rows"][0]["color"], "#33AAFF")
                    post("/api/settings", {"brightness": 70})
                    with urlopen(request) as response:
                        self.assertEqual(json.load(response)["custom"][0]["name"], "Weekday")
                    with self.assertRaises(HTTPError) as rejected:
                        post("/api/screens", {"action": "save", "screen": {
                            "id": custom_id, "name": "Bad", "rows": [
                                {"content": "weather", "color": "#FFFFFF"}]}})
                    self.assertEqual(rejected.exception.code, 400)
                    with self.assertRaises(HTTPError) as rejected:
                        post("/api/screens", {"action": "delete", "screen_id": "clock-classic"})
                    self.assertEqual(rejected.exception.code, 400)
                    deleted = post("/api/screens", {"action": "delete", "screen_id": custom_id})
                    self.assertEqual(deleted["clock_screen_id"], "clock-classic")
                    self.assertEqual(deleted["custom_screens"], [])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_settings_api_validates_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            token_path = Path(directory) / "web-token"
            token_path.write_text("a" * 64)
            public_host_path = Path(directory) / "public-host"
            public_host_path.write_text("flightboard.example.ts.net\n")
            with (patch.object(web_server, "DEFAULT_PATH", path),
                  patch.object(web_server, "TOKEN_PATH", token_path),
                  patch.object(web_server, "PUBLIC_HOST_PATH", public_host_path)):
                server = web_server.BoundedHTTPServer(("127.0.0.1", 0), web_server.Handler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(base + "/api/settings")
                    self.assertEqual(rejected.exception.code, 401)
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(base + "/api/status")
                    self.assertEqual(rejected.exception.code, 401)
                    authorized = Request(base + "/api/settings", headers={"X-Flightboard-Key": "a" * 64})
                    with urlopen(authorized) as response:
                        self.assertEqual(json.load(response)["mode"], "nearby")
                    payload = json.dumps({"mode": "flight", "flight": "aca150"}).encode()
                    bad_origin = Request(base + "/api/settings", payload,
                                         {"Content-Type": "application/json",
                                          "Origin": "http://evil.example",
                                          "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(bad_origin)
                    self.assertEqual(rejected.exception.code, 403)
                    no_origin = Request(base + "/api/settings", payload,
                                        {"Content-Type": "application/json",
                                         "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(no_origin)
                    self.assertEqual(rejected.exception.code, 403)
                    invalid = Request(base + "/api/settings", b'{"mode":"flight"}',
                                      {"Content-Type": "application/json",
                                       "Origin": base, "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(invalid)
                    self.assertEqual(rejected.exception.code, 400)
                    valid = Request(base + "/api/settings", payload,
                                    {"Content-Type": "application/json",
                                     "Origin": base, "X-Flightboard-Key": "a" * 64})
                    with urlopen(valid) as response:
                        self.assertEqual(json.load(response)["flight"], "ACA150")
                    self.assertEqual(json.loads(path.read_text())["mode"], "flight")
                    secure_origin = "https://flightboard.example.ts.net"
                    wrong_secure_origin = Request(base + "/api/settings", payload,
                                                  {"Content-Type": "application/json",
                                                   "Origin": "https://other.example.ts.net",
                                                   "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(wrong_secure_origin)
                    self.assertEqual(rejected.exception.code, 403)
                    proxied = Request(base + "/api/settings", payload,
                                      {"Content-Type": "application/json",
                                       "Origin": secure_origin,
                                       "Host": "flightboard.example.ts.net",
                                       "X-Flightboard-Key": "a" * 64})
                    with urlopen(proxied) as response:
                        self.assertEqual(response.status, 200)
                    power_payload = json.dumps({"display_enabled": False}).encode()
                    power_request = Request(base + "/api/display", power_payload,
                                            {"Content-Type": "application/json",
                                             "Origin": secure_origin,
                                             "X-Flightboard-Key": "a" * 64})
                    with urlopen(power_request) as response:
                        powered_off = json.load(response)
                    self.assertFalse(powered_off["display_enabled"])
                    self.assertEqual(powered_off["flight"], "ACA150")
                    self.assertFalse(json.loads(path.read_text())["display_enabled"])
                    # Saving unrelated form fields cannot undo a power toggle.
                    with urlopen(valid) as response:
                        self.assertFalse(json.load(response)["display_enabled"])
                    bad_power = Request(base + "/api/display", b'{"display_enabled":"off"}',
                                        {"Content-Type": "application/json",
                                         "Origin": base, "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(bad_power)
                    self.assertEqual(rejected.exception.code, 400)
                    bad_power_origin = Request(base + "/api/display", power_payload,
                                               {"Content-Type": "application/json",
                                                "Origin": "http://evil.example",
                                                "X-Flightboard-Key": "a" * 64})
                    with self.assertRaises(HTTPError) as rejected:
                        urlopen(bad_power_origin)
                    self.assertEqual(rejected.exception.code, 403)
                    power_on = Request(base + "/api/display",
                                       json.dumps({"display_enabled": True}).encode(),
                                       {"Content-Type": "application/json",
                                        "Origin": base, "X-Flightboard-Key": "a" * 64})
                    with urlopen(power_on) as response:
                        self.assertTrue(json.load(response)["display_enabled"])
                    clock = Request(base + "/api/settings", b'{"mode":"clock"}',
                                    {"Content-Type": "application/json",
                                     "Origin": base, "X-Flightboard-Key": "a" * 64})
                    with urlopen(clock) as response:
                        self.assertEqual(json.load(response)["mode"], "clock")
                    self.assertEqual(json.loads(path.read_text())["mode"], "clock")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
