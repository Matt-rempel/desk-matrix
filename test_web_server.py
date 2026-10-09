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
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
