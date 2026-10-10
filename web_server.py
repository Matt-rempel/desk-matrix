#!/usr/bin/env python3
"""Small, dependency-free settings page protected by a random pairing key."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import blocks
import catalog
from library import LIBRARY_PATH, apply_action, load_library, save_library, validate_art, validate_screen
from settings import (DEFAULT_PATH, LEGACY_FIELDS, STATE_DIR, load_settings, save_settings,
                      validate_settings)

HERE = Path(__file__).parent
WEB_DIR = HERE / "web"
STATUS_PATH = STATE_DIR / "status.json"
DATA_PATH = STATE_DIR / "data.json"
TOKEN_PATH = STATE_DIR / "web-token"
PUBLIC_HOST_PATH = STATE_DIR / "public-host"
SETTINGS_WRITE_LOCK = threading.Lock()
MAX_BODY = 64 * 1024
MAX_PREVIEW_SCREENS = 40
MAX_PREVIEW_ART = 8
DATA_MAX_AGE_S = 30 * 60
STATIC_RE = re.compile(r"/([a-z0-9-]+)\.(js|css|svg)")
STATIC_TYPES = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
                "svg": "image/svg+xml"}
PWA_FILES = {
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/offline.html": ("offline.html", "text/html; charset=utf-8"),
}
POST_ROUTES = ("/api/settings", "/api/display", "/api/library", "/api/preview")

_catalog_body: bytes | None = None
_data_cache: dict = {"key": None, "data": None}
_data_lock = threading.Lock()


def catalog_body() -> bytes:
    """GET /api/catalog never changes while the server runs; encode it once."""
    global _catalog_body
    if _catalog_body is None:
        _catalog_body = json.dumps(catalog.catalog_json()).encode()
    return _catalog_body


def _merge_data(base: dict, fresh: dict) -> dict:
    for key, value in fresh.items():
        if value is None:
            continue
        if key in ("feeds", "metar") and isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def preview_data() -> dict:
    """SAMPLE_DATA overlaid by STATE_DIR/data.json when it is under 30 minutes old.

    Parsed once per data.json version; callers get their own copy.
    """
    try:
        stat = DATA_PATH.stat()
        fresh = time.time() - stat.st_mtime < DATA_MAX_AGE_S
        key = (str(DATA_PATH), stat.st_mtime_ns, stat.st_size) if fresh else None
    except OSError:
        key = None
    with _data_lock:
        if _data_cache["data"] is not None and _data_cache["key"] == key:
            return copy.deepcopy(_data_cache["data"])
        data = catalog.sample_data()
        if key is not None:
            try:
                snapshot = json.loads(DATA_PATH.read_text())
                if isinstance(snapshot, dict):
                    _merge_data(data, snapshot)
            except (OSError, ValueError):
                pass
        _data_cache.update(key=key, data=data)
        return copy.deepcopy(data)


def frame_hex(pixels) -> str:
    return bytes(channel for pixel in pixels for channel in pixel).hex()


def render_previews(body, settings, lib: dict) -> list[str]:
    """Validate a /api/preview body and render each screen to a frame string."""
    if not isinstance(body, dict) or set(body) - {"screens", "elapsed", "art"} or "screens" not in body:
        raise ValueError("Send {screens: [...], elapsed?, art?}")
    screens = body["screens"]
    if not isinstance(screens, list) or len(screens) > MAX_PREVIEW_SCREENS:
        raise ValueError(f"Preview at most {MAX_PREVIEW_SCREENS} screens at once")
    elapsed = body.get("elapsed", 0)
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not 0 <= elapsed <= 86400:
        raise ValueError("elapsed must be 0–86400 seconds")
    art = {**catalog.BUILTIN_ART, **{item["id"]: item for item in lib["art"]}}
    drafts = body.get("art", [])
    if not isinstance(drafts, list) or len(drafts) > MAX_PREVIEW_ART:
        raise ValueError(f"Send at most {MAX_PREVIEW_ART} pieces of draft art")
    for draft in drafts:
        if not isinstance(draft, dict):
            raise ValueError("Art must be an object")
        art_id = draft.get("id")
        if art_id in (None, "", "draft"):
            clean = {**validate_art({**draft, "id": "art-" + "0" * 16}), "id": "draft"}
        else:
            clean = validate_art(draft)
        art[clean["id"]] = clean
    clean_screens = []
    for screen in screens:
        clean = validate_screen(screen, preview=True)
        # An unsaved copy of a built-in shows the original's timer and habit samples.
        clean["id"] = clean["id"] or clean["based_on"] or ""
        clean_screens.append(clean)
    sample = blocks.sample_context()
    zone = ZoneInfo(settings.timezone)
    ctx = blocks.RenderContext(
        now=datetime.now(zone), elapsed=float(elapsed), data=preview_data(),
        units={"temp": settings.temp_unit, "distance": settings.distance_unit}, art=art,
        habits={**sample.habits, **lib["habits"]}, timers={**sample.timers, **lib["timers"]})
    return [frame_hex(blocks.frame(screen, ctx)) for screen in clean_screens]


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
            self._json(401, {"error": "Enter the pairing key shown during installation"})
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

    def _static(self, path: str) -> bool:
        if path == "/":
            name, content_type = "index.html", "text/html; charset=utf-8"
        elif path in PWA_FILES:
            name, content_type = PWA_FILES[path]
        else:
            match = STATIC_RE.fullmatch(path)
            if not match:
                return False
            name, content_type = f"{match[1]}.{match[2]}", STATIC_TYPES[match[2]]
        try:
            body = (WEB_DIR / name).read_bytes()
        except OSError:
            return False
        self._send(200, content_type, body)
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            if not self._static(path):
                self._json(404, {"error": "Not found"})
            return
        if not self._authorized():
            return
        if path == "/api/settings":
            try:
                self._json(200, load_settings(DEFAULT_PATH).to_dict())
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(500, {"error": f"Settings file is invalid: {exc}"})
        elif path == "/api/catalog":
            self._send(200, "application/json; charset=utf-8", catalog_body())
        elif path == "/api/library":
            try:
                self._json(200, self._library())
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(500, {"error": str(exc)})
        elif path == "/api/status":
            try:
                self._json(200, json.loads(STATUS_PATH.read_text()))
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                self._json(200, {"state": "starting", "nearby": []})
        else:
            self._json(404, {"error": "Not found"})

    def _library(self) -> dict:
        try:
            settings = load_settings(DEFAULT_PATH)
        except (OSError, ValueError):
            settings = None
        with SETTINGS_WRITE_LOCK:  # A first load may create library.json.
            return load_library(LIBRARY_PATH, settings)

    def _origin_allowed(self) -> bool:
        # A browser must send an exact same-origin request. The custom key
        # header also prevents a cross-origin form from submitting settings.
        origin = urlsplit(self.headers.get("Origin", ""))
        if origin.scheme == "https":
            try:
                return origin.netloc == PUBLIC_HOST_PATH.read_text().strip()
            except OSError:
                return False
        return (origin.scheme == "http"
                and self.client_address[0] in ("127.0.0.1", "::1")
                and origin.netloc == self.headers.get("Host"))

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in POST_ROUTES:
            self._json(404, {"error": "Not found"})
            return
        if not self._authorized():
            return
        if not self._origin_allowed():
            self._json(403, {"error": "Cross-site request rejected"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._json(415, {"error": "Send JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._json(413, {"error": "Request is too large"})
            return
        try:
            if length <= 0:
                raise ValueError("Request is empty")
            data = json.loads(self.rfile.read(length))
            if path == "/api/preview":
                settings = load_settings(DEFAULT_PATH)
                frames = render_previews(data, settings, self._library())
                self._json(200, {"frames": frames})
                return
            with SETTINGS_WRITE_LOCK:
                current = load_settings(DEFAULT_PATH)
                if path == "/api/library":
                    library = apply_action(load_library(LIBRARY_PATH, current), data)
                    save_library(library, LIBRARY_PATH)
                    result = library
                else:
                    if path == "/api/display":
                        if (not isinstance(data, dict) or set(data) != {"display_enabled"}
                                or not isinstance(data["display_enabled"], bool)):
                            raise ValueError("Send display_enabled as on or off")
                        settings = replace(current, display_enabled=data["display_enabled"])
                    else:
                        if not isinstance(data, dict):
                            raise ValueError("Settings must be an object")
                        # The separate power button owns display_enabled, and the
                        # lineup in library.json replaced the legacy screen fields:
                        # saving form edits must not change either.
                        form = {key: value for key, value in data.items() if key not in LEGACY_FIELDS}
                        settings = validate_settings({**current.to_dict(), **form,
                                                      "display_enabled": current.display_enabled})
                    save_settings(settings, DEFAULT_PATH)
                    result = settings.to_dict()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except OSError as exc:
            self._json(500, {"error": f"Could not save: {exc}"})
            return
        self._json(200, result)

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
