#!/usr/bin/env python3
"""Small, dependency-free settings page protected by a random pairing key."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from settings import DEFAULT_PATH, STATE_DIR, load_settings, save_settings, validate_settings

HERE = Path(__file__).parent
STATUS_PATH = STATE_DIR / "status.json"
TOKEN_PATH = STATE_DIR / "web-token"
PUBLIC_HOST_PATH = STATE_DIR / "public-host"


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        return request, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        try:
            expected = TOKEN_PATH.read_text().strip()
        except OSError:
            self._json(503, {"error": "Pairing key is not configured"})
            return False
        supplied = self.headers.get("X-Flightboard-Key", "")
        if len(supplied) != 64 or not secrets.compare_digest(supplied, expected):
            self._json(401, {"error": "Enter the pairing key shown during activation"})
            return False
        return True

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; "
                         "script-src 'self'; style-src 'self'; form-action 'self'; "
                         "base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value):
        self._send(status, "application/json; charset=utf-8", json.dumps(value).encode())

    def do_GET(self):
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if self.path in files:
            name, content_type = files[self.path]
            self._send(200, content_type, (HERE / name).read_bytes())
        elif self.path.startswith("/api/") and not self._authorized():
            return
        elif self.path == "/api/settings":
            try:
                self._json(200, load_settings(DEFAULT_PATH).to_dict())
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(500, {"error": f"Settings file is invalid: {exc}"})
        elif self.path == "/api/status":
            try:
                self._json(200, json.loads(STATUS_PATH.read_text()))
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                self._json(200, {"state": "starting", "nearby": []})
        else:
            self._json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/settings":
            self._json(404, {"error": "Not found"})
            return
        if not self._authorized():
            return
        # A browser must send an exact same-origin request. The custom key
        # header also prevents a cross-origin form from submitting settings.
        origin = urlsplit(self.headers.get("Origin", ""))
        if origin.scheme == "https":
            try:
                allowed_origin = origin.netloc == PUBLIC_HOST_PATH.read_text().strip()
            except OSError:
                allowed_origin = False
        else:
            allowed_origin = (origin.scheme == "http"
                              and self.client_address[0] in ("127.0.0.1", "::1")
                              and origin.netloc == self.headers.get("Host"))
        if not allowed_origin:
            self._json(403, {"error": "Cross-site request rejected"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._json(415, {"error": "Send JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Settings request is too large or empty")
            data = json.loads(self.rfile.read(length))
            settings = validate_settings(data)
            save_settings(settings, DEFAULT_PATH)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except OSError as exc:
            self._json(500, {"error": f"Could not save settings: {exc}"})
            return
        self._json(200, settings.to_dict())

    def log_message(self, format, *args):
        print("flightboard web:", format % args, flush=True)


def main():
    if not TOKEN_PATH.is_file():
        raise SystemExit("Missing pairing key; run the activation script")
    host = os.environ.get("FLIGHTBOARD_BIND_HOST", "127.0.0.1")
    server = BoundedHTTPServer((host, 8765), Handler)
    print(f"Flightboard settings backend: {host}:8765", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
