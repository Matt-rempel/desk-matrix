import http.client
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import catalog
import web_server

KEY = "a" * 64
CUSTOM_SCREEN = {"id": "", "name": "Desk", "layout": "two",
                 "slots": [{"block": "time", "color": "#FFFFFF", "options": {}},
                           {"block": "temp", "color": None, "options": {"which": "now"}}],
                 "style": {"palette": "ice", "motion": "still"}, "based_on": None}


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.settings_path = root / "settings.json"
        self.library_path = root / "library.json"
        self.data_path = root / "data.json"
        (root / "web-token").write_text(KEY)
        (root / "public-host").write_text("flightboard.example.ts.net\n")
        patches = [
            patch.object(web_server, "DEFAULT_PATH", self.settings_path),
            patch.object(web_server, "LIBRARY_PATH", self.library_path),
            patch.object(web_server, "DATA_PATH", self.data_path),
            patch.object(web_server, "STATUS_PATH", root / "status.json"),
            patch.object(web_server, "TOKEN_PATH", root / "web-token"),
            patch.object(web_server, "PUBLIC_HOST_PATH", root / "public-host"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        web_server._data_cache.update(key=None, data=None)
        self.server = web_server.BoundedHTTPServer(("127.0.0.1", 0), web_server.Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def get(self, path, key=KEY):
        headers = {"X-Flightboard-Key": key} if key else {}
        with urlopen(Request(self.base + path, headers=headers)) as response:
            return response.status, response.headers, response.read()

    def get_json(self, path):
        return json.loads(self.get(path)[2])

    def post(self, path, value, origin=None, key=KEY, content_type="application/json", raw=None):
        headers = {"Content-Type": content_type, "Origin": origin or self.base}
        if key:
            headers["X-Flightboard-Key"] = key
        body = raw if raw is not None else json.dumps(value).encode()
        with urlopen(Request(self.base + path, body, headers)) as response:
            return json.load(response)

    def assertStatus(self, code, call, *args, **kwargs):
        with self.assertRaises(HTTPError) as rejected:
            call(*args, **kwargs)
        self.assertEqual(rejected.exception.code, code)
        return json.loads(rejected.exception.read() or b"{}")


class StaticFileTests(ServerTestCase):
    def test_serves_web_directory_with_types_and_csp(self):
        status, headers, body = self.get("/", key=None)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(body, (web_server.WEB_DIR / "index.html").read_bytes())
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn(b'rel="manifest" href="/manifest.webmanifest"', body)
        self.assertIn(b'rel="apple-touch-icon" href="/apple-touch-icon.png"', body)
        for name, content_type in (("app.js", "text/javascript; charset=utf-8"),
                                   ("app.css", "text/css; charset=utf-8"),
                                   ("icon.svg", "image/svg+xml"),
                                   ("sw.js", "text/javascript; charset=utf-8"),
                                   ("view-lineup.js", "text/javascript; charset=utf-8")):
            status, headers, body = self.get("/" + name + "?v=2", key=None)
            self.assertEqual(headers["Content-Type"], content_type)
            self.assertEqual(body, (web_server.WEB_DIR / name).read_bytes())

    def test_pwa_assets_are_public_but_no_settings_are_cached(self):
        status, headers, body = self.get("/manifest.webmanifest", key=None)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/manifest+json")
        manifest = json.loads(body)
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual({icon["sizes"] for icon in manifest["icons"]}, {"192x192", "512x512"})
        for name, size in (("icon-192.png", 192), ("icon-512.png", 512),
                           ("apple-touch-icon.png", 180)):
            status, headers, body = self.get("/" + name, key=None)
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(int.from_bytes(body[16:20], "big"), size)
            self.assertEqual(int.from_bytes(body[20:24], "big"), size)
        self.assertIn(b"Tailscale", self.get("/offline.html", key=None)[2])
        worker = self.get("/sw.js", key=None)[2]
        self.assertIn(b"event.request.mode !== 'navigate'", worker)
        self.assertNotIn(b"/api/", worker)

    def test_rejects_unknown_and_traversal_paths(self):
        for path in ("/nope.js", "/index.html", "/web_server.py", "/settings.json", "/web-token",
                     "/../web_server.js", "/%2e%2e/web-token", "/..%2fweb_server.py", "/App.js",
                     "/sub/app.js", "/app.js/", "/.js", "/app.json", "//etc/passwd", "/api"):
            with self.subTest(path=path):
                conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                conn.request("GET", path)
                response = conn.getresponse()
                body = response.read()
                conn.close()
                self.assertEqual(response.status, 404)
                self.assertNotIn(KEY.encode(), body)


class ApiTests(ServerTestCase):
    def test_auth_required_on_every_api_route(self):
        for path in ("/api/catalog", "/api/library", "/api/settings", "/api/status"):
            with self.subTest(path=path):
                self.assertStatus(401, self.get, path, key=None)
                self.assertStatus(401, self.get, path, key="b" * 64)
        for path in ("/api/library", "/api/preview", "/api/settings", "/api/display"):
            with self.subTest(path=path):
                self.assertStatus(401, self.post, path, {}, key=None)
                self.assertStatus(403, self.post, path, {}, origin="http://evil.example")
                self.assertStatus(403, self.post, path, {}, origin="https://other.example.ts.net")
                self.assertStatus(415, self.post, path, {}, content_type="text/plain")
        self.assertStatus(404, self.post, "/api/screens", {"action": "clone"})
        self.assertStatus(404, self.get, "/api/screens")

    def test_body_limit(self):
        def raw_post(length, body):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            conn.putrequest("POST", "/api/library")
            for name, value in (("Content-Type", "application/json"), ("Origin", self.base),
                                ("X-Flightboard-Key", KEY), ("Content-Length", str(length))):
                conn.putheader(name, value)
            conn.endheaders()
            conn.send(body)
            response = conn.getresponse()
            data = json.loads(response.read())
            conn.close()
            return response.status, data

        self.assertEqual(raw_post(64 * 1024 + 1, b"{}")[0], 413)
        self.assertEqual(raw_post(0, b"")[0], 400)
        # A request just under the limit is read (and rejected only for its content).
        padding = json.dumps({"action": "unpin", "pad": "x" * (60 * 1024)}).encode()
        status, data = raw_post(len(padding), padding)
        self.assertEqual(status, 400)
        self.assertIn("unknown field", data["error"])

    def test_catalog(self):
        value = self.get_json("/api/catalog")
        for key in ("layouts", "palettes", "blocks", "icons", "motions", "transitions", "builtins", "shelves"):
            self.assertIn(key, value)
        self.assertEqual(value, json.loads(json.dumps(catalog.catalog_json())))

    def test_library_round_trip(self):
        self.settings_path.write_text(json.dumps({"mode": "flight", "flight": "ACA150"}))
        lib = self.get_json("/api/library")
        self.assertTrue(self.library_path.exists())
        self.assertEqual(lib["screens"][0]["name"], "Follow ACA150")
        self.assertEqual(lib["lineup"]["always"][0]["screen_id"], lib["screens"][0]["id"])
        lib = self.post("/api/library", {"action": "save_screen", "screen": CUSTOM_SCREEN})
        new_id = lib["screens"][-1]["id"]
        self.assertRegex(new_id, r"^custom-[0-9a-f]{32}$")
        lib = self.post("/api/library", {"action": "show_now", "screen_id": new_id})
        self.assertEqual(lib["pinned"], {"screen_id": new_id, "until": None})
        lib = self.post("/api/library", {"action": "timer", "timer_id": "focus-pomodoro", "op": "start",
                                         "work_min": 25, "break_min": 5})
        self.assertEqual(lib["timers"]["focus-pomodoro"]["state"], "running")
        lib = self.post("/api/library", {"action": "delete_screen", "screen_id": new_id})
        self.assertIsNone(lib["pinned"])
        self.assertEqual(self.get_json("/api/library"), lib)
        self.assertEqual(json.loads(self.library_path.read_text()), lib)
        error = self.assertStatus(400, self.post, "/api/library", {"action": "explode"})
        self.assertIn("Unknown library action", error["error"])
        self.assertStatus(400, self.post, "/api/library", {"action": "save_screen",
                                                           "screen": {**CUSTOM_SCREEN, "layout": "x"}})
        self.assertStatus(400, self.post, "/api/library", None, raw=b"{bad json")
        self.assertEqual(self.get_json("/api/library"), lib)
        # A corrupt file is reported, never silently replaced.
        self.library_path.write_text('{"version": 7}')
        error = self.assertStatus(500, self.get, "/api/library")
        self.assertIn("library.json is invalid", error["error"])
        self.assertStatus(400, self.post, "/api/library", {"action": "unpin"})

    def test_preview(self):
        builtins = [{key: screen[key] for key in ("id", "name", "layout", "slots", "style", "based_on")}
                    for screen in catalog.BUILTIN_SCREENS[:20]]
        screens = builtins + [CUSTOM_SCREEN] * 20
        started = time.perf_counter()
        frames = self.post("/api/preview", {"screens": screens, "elapsed": 1.5})["frames"]
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(len(frames), 40)
        for frame in frames:
            self.assertRegex(frame, r"^[0-9a-f]{3072}$")
        self.assertTrue(any(set(frame) != {"0"} for frame in frames))
        self.assertEqual(self.post("/api/preview", {"screens": []})["frames"], [])
        # Builtin ids, missing ids and missing names are all fine for working copies.
        loose = dict(CUSTOM_SCREEN)
        del loose["id"], loose["name"]
        self.assertEqual(len(self.post("/api/preview", {"screens": [loose]})["frames"]), 1)
        for bad in ({"screens": [CUSTOM_SCREEN] * 41}, {"screens": "x"}, {}, {"screens": [], "x": 1},
                    {"screens": [], "elapsed": -1}, {"screens": [{**CUSTOM_SCREEN, "layout": "nope"}]},
                    {"screens": [{**CUSTOM_SCREEN, "id": "../x"}]}, []):
            with self.subTest(bad=bad):
                self.assertStatus(400, self.post, "/api/preview", bad)

    def test_preview_uses_units_fresh_data_and_draft_art(self):
        temp = {"id": "", "name": "T", "layout": "full",
                "slots": [{"block": "temp", "color": "#FFFFFF", "options": {"which": "now"}}],
                "style": {"palette": None, "motion": "still"}, "based_on": None}
        celsius = self.post("/api/preview", {"screens": [temp]})["frames"][0]
        self.data_path.write_text(json.dumps({"weather": {**catalog.SAMPLE_DATA["weather"], "temp_c": -30.0}}))
        cold = self.post("/api/preview", {"screens": [temp]})["frames"][0]
        self.assertNotEqual(celsius, cold)
        stale = time.time() - 31 * 60
        os.utime(self.data_path, (stale, stale))
        self.assertEqual(self.post("/api/preview", {"screens": [temp]})["frames"][0], celsius)
        self.post("/api/settings", {"temp_unit": "F"})
        self.assertNotEqual(self.post("/api/preview", {"screens": [temp]})["frames"][0], celsius)

        drawing = {"id": "", "name": "Dot", "w": 7, "h": 7, "palette": ["#FF0000"],
                   "frames": ["0" * 49], "fps": 1}
        art_screen = {**temp, "slots": [{"block": "art", "color": None, "options": {"art_id": "draft"}}]}
        empty = self.post("/api/preview", {"screens": [art_screen]})["frames"][0]
        drawn = self.post("/api/preview", {"screens": [art_screen], "art": [drawing]})["frames"][0]
        self.assertNotEqual(empty, drawn)
        self.assertIn("ff0000", drawn)
        self.assertStatus(400, self.post, "/api/preview", {"screens": [art_screen],
                                                           "art": [{**drawing, "frames": ["z" * 49]}]})

    def test_preview_uses_saved_timers_for_builtins(self):
        pomodoro = {key: catalog.BUILTINS["focus-pomodoro"][key]
                    for key in ("id", "name", "layout", "slots", "style", "based_on")}
        sample = self.post("/api/preview", {"screens": [pomodoro]})["frames"][0]
        copy = {**pomodoro, "id": "", "based_on": "focus-pomodoro"}
        self.assertEqual(self.post("/api/preview", {"screens": [copy]})["frames"][0], sample)
        self.post("/api/library", {"action": "timer", "timer_id": "focus-pomodoro", "op": "reset"})
        self.assertNotEqual(self.post("/api/preview", {"screens": [pomodoro]})["frames"][0], sample)

    def test_status_passes_through(self):
        self.assertEqual(self.get_json("/api/status")["state"], "starting")
        status = {"state": "running", "frame": "00" * 1536, "screen_id": "time-big", "moment": None}
        (Path(self.directory.name) / "status.json").write_text(json.dumps(status))
        self.assertEqual(self.get_json("/api/status"), status)


class SettingsApiTests(ServerTestCase):
    def test_settings_api_validates_and_persists(self):
        self.assertEqual(self.get_json("/api/settings")["temp_unit"], "C")
        saved = self.post("/api/settings", {"brightness": 70, "temp_unit": "F", "distance_unit": "km",
                                            "brightness_max": 80, "brightness_follow_lineup": False,
                                            "night_palette": True,
                                            "calendar_ics_url": "https://cal.example.com/a.ics"})
        self.assertEqual((saved["brightness"], saved["temp_unit"], saved["brightness_max"]), (70, "F", 80))
        self.assertEqual(json.loads(self.settings_path.read_text())["calendar_ics_url"],
                         "https://cal.example.com/a.ics")
        for bad in ({"temp_unit": "K"}, {"brightness_max": 0}, {"calendar_ics_url": "ftp://x"},
                    {"unknown": 1}, ["brightness"]):
            with self.subTest(bad=bad):
                self.assertStatus(400, self.post, "/api/settings", bad)
        # Legacy library fields from a form are ignored, not applied or rejected.
        saved = self.post("/api/settings", {"mode": "flight", "flight": "", "clock_screen_id": "x",
                                            "custom_screens": "x", "label": "home"})
        self.assertEqual((saved["mode"], saved["flight"], saved["label"]), ("nearby", "", "HOME"))
        # Secure origins must match the public host file.
        proxied = self.post("/api/settings", {"rotate": 12}, origin="https://flightboard.example.ts.net")
        self.assertEqual(proxied["rotate"], 12)

    def test_display_toggle_is_separate_from_the_form(self):
        off = self.post("/api/display", {"display_enabled": False})
        self.assertFalse(off["display_enabled"])
        self.assertFalse(self.post("/api/settings", {"display_enabled": True,
                                                     "brightness": 50})["display_enabled"])
        self.assertStatus(400, self.post, "/api/display", {"display_enabled": "off"})
        self.assertStatus(400, self.post, "/api/display", {"display_enabled": True, "x": 1})
        self.assertTrue(self.post("/api/display", {"display_enabled": True})["display_enabled"])
        self.assertTrue(json.loads(self.settings_path.read_text())["display_enabled"])


if __name__ == "__main__":
    unittest.main()
