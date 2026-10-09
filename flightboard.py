#!/usr/bin/env python3
"""Configurable aircraft display for a 32x16 HUB75 RGB matrix."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from settings import DEFAULT_PATH, STATE_DIR, Settings, effective_brightness, load_settings, rgb

SOURCE = "https://opendata.adsb.fi"
METADATA_SOURCE = "https://api.adsbdb.com/v0"
ADSB_LOCK = threading.Lock()
ADSB_NEXT_REQUEST = 0.0


def _adsb_json(request):
    """Serialize requests across both endpoints and space their start times."""
    global ADSB_NEXT_REQUEST
    with ADSB_LOCK:
        wait = ADSB_NEXT_REQUEST - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        ADSB_NEXT_REQUEST = time.monotonic() + 1.1
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)
DEFAULT_LAT = 51.08083  # Canada Olympic Park / WinSport, approximate venue center
DEFAULT_LON = -114.21714
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00001", "00010", "00100", "01000", "10000", "10000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}

# Seven-pixel marks are deliberately simple; full logos need a larger matrix.
ICONS = {
    "plane": ("0001000", "0001000", "0011100", "1111111", "0011100", "0101010", "1000001"),
    "maple": ("0010100", "0111110", "1111111", "0111110", "0011100", "0010100", "0001000"),
    "westjet": ("1000001", "1000001", "1010101", "1010101", "1010101", "1100011", "1000001"),
    "delta": ("0001000", "0011100", "0011100", "0110110", "0110110", "1111111", "1111111"),
}


@dataclass(frozen=True)
class Aircraft:
    callsign: str
    hex_code: str
    distance_nm: float
    altitude_ft: int | None
    speed_kt: int | None
    aircraft_type: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True)
class Metadata:
    route: str | None = None
    airline: str | None = None
    aircraft_type: str | None = None
    iata_callsign: str | None = None
    origin_position: tuple[float, float] | None = None
    destination_position: tuple[float, float] | None = None


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 3440.065 * 2 * math.asin(min(1, math.sqrt(a)))


def parse_aircraft(payload: dict, lat: float, lon: float,
                   radius_nm: int | None, allow_ground: bool = False) -> list[Aircraft]:
    result = []
    if not isinstance(payload, dict):
        return result
    rows = payload.get("ac")
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            callsign = str(row.get("flight") or "").strip().upper()
            seen = float(row.get("seen_pos", 999))
            position = (float(row["lat"]), float(row["lon"]))
            if (not callsign or not math.isfinite(seen) or seen > 30
                    or not all(math.isfinite(value) for value in position)
                    or not -90 <= position[0] <= 90 or not -180 <= position[1] <= 180):
                continue
            distance = distance_nm(lat, lon, *position)
            if radius_nm is not None and distance > radius_nm:
                continue
            raw_alt = row.get("alt_baro")
            altitude = (int(raw_alt) if isinstance(raw_alt, (int, float))
                        and math.isfinite(raw_alt) else None)
            raw_speed = row.get("gs")
            speed = (round(float(raw_speed)) if isinstance(raw_speed, (int, float))
                     and math.isfinite(raw_speed) else None)
            if not allow_ground and (altitude is None or (speed is not None and speed < 30)):
                continue
            aircraft_type = row.get("t")
            result.append(Aircraft(callsign, str(row.get("hex") or "").lower(),
                                   distance, altitude, speed,
                                   aircraft_type if isinstance(aircraft_type, str) else None,
                                   *position))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return sorted(result, key=lambda aircraft: aircraft.distance_nm)


def fetch_aircraft(lat: float, lon: float, radius_nm: int) -> list[Aircraft]:
    url = f"{SOURCE}/api/v3/lat/{lat}/lon/{lon}/dist/{radius_nm}"
    request = urllib.request.Request(url, headers={"User-Agent": "Flightboard/0.3 personal"})
    return parse_aircraft(_adsb_json(request), lat, lon, radius_nm)


def _fetch_callsign(callsign: str, lat: float, lon: float) -> Aircraft | None:
    url = f"{SOURCE}/api/v2/callsign/{urllib.parse.quote(callsign)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Flightboard/0.3 personal"})
    try:
        flights = parse_aircraft(_adsb_json(request), lat, lon, None, allow_ground=True)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return next((item for item in flights if item.callsign == callsign), None)


def fetch_tracked_aircraft(callsign: str, lat: float, lon: float) -> tuple[Aircraft | None, str]:
    """Look globally; translate a two-letter flight number when ADSBdb knows it."""
    found = _fetch_callsign(callsign, lat, lon)
    if found:
        return found, callsign
    if not re.fullmatch(r"[A-Z]{2}[0-9]{1,4}[A-Z]?", callsign):
        return None, callsign
    url = f"{METADATA_SOURCE}/callsign/{urllib.parse.quote(callsign)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Flightboard/0.3 personal"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
            route = (payload.get("response") or {}) if isinstance(payload, dict) else {}
            route = (route.get("flightroute") or {}) if isinstance(route, dict) else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, callsign
        raise
    alias = route.get("callsign_icao") if isinstance(route, dict) else None
    if not isinstance(alias, str) or not re.fullmatch(r"[A-Z0-9]{2,10}", alias):
        return None, callsign
    return _fetch_callsign(alias, lat, lon), alias


def select_flights(flights: list[Aircraft], max_count: int = 3) -> list[Aircraft]:
    """Keep the nearest plane and make room for route-bearing flights."""
    if not flights:
        return []
    if max_count == 1:
        return flights[:1]
    selected = [flights[0]]
    for aircraft in flights[1:]:
        if re.fullmatch(r"[A-Z]{3}[0-9]{1,4}[A-Z]?", aircraft.callsign):
            selected.append(aircraft)
            if len(selected) == max_count:
                return selected
    for aircraft in flights[1:]:
        if aircraft not in selected:
            selected.append(aircraft)
            if len(selected) == max_count:
                break
    return selected


def parse_metadata(payload: dict) -> Metadata:
    if not isinstance(payload, dict):
        return Metadata()
    response = payload.get("response") or {}
    if not isinstance(response, dict):
        return Metadata()
    route = response.get("flightroute") or {}
    plane = response.get("aircraft") or {}
    if not isinstance(route, dict):
        route = {}
    if not isinstance(plane, dict):
        plane = {}
    origin = route.get("origin") or {}
    destination = route.get("destination") or {}
    origin_code = (origin.get("iata_code") or origin.get("icao_code")) if isinstance(origin, dict) else None
    destination_code = ((destination.get("iata_code") or destination.get("icao_code"))
                        if isinstance(destination, dict) else None)
    route_text = (f"{origin_code}-{destination_code}"
                  if isinstance(origin_code, str) and isinstance(destination_code, str) else None)
    airline = route.get("airline") or {}
    airline_name = airline.get("name") if isinstance(airline, dict) else None
    aircraft_type = plane.get("icao_type") or None
    iata_callsign = route.get("callsign_iata") or None

    def coordinates(airport):
        if not isinstance(airport, dict):
            return None
        lat, lon = airport.get("latitude"), airport.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return float(lat), float(lon)
        return None

    return Metadata(route_text, airline_name if isinstance(airline_name, str) else None,
                    aircraft_type if isinstance(aircraft_type, str) else None,
                    iata_callsign if isinstance(iata_callsign, str) else None,
                    coordinates(origin), coordinates(destination))


def lookup_metadata(aircraft: Aircraft) -> Metadata | None:
    if not re.fullmatch(r"[0-9a-f]{6}", aircraft.hex_code):
        return None
    if not re.fullmatch(r"[A-Z0-9]{2,10}", aircraft.callsign):
        return None
    hex_code = urllib.parse.quote(aircraft.hex_code)
    callsign = urllib.parse.quote(aircraft.callsign)
    url = f"{METADATA_SOURCE}/aircraft/{hex_code}?callsign={callsign}"
    request = urllib.request.Request(url, headers={"User-Agent": "YYC-flightboard/0.2 personal"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return parse_metadata(json.load(response))
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and re.fullmatch(r"[A-Z]{3}[0-9]{1,4}[A-Z]?", aircraft.callsign):
            # The route may be known even when the aircraft hex is not.
            route_url = f"{METADATA_SOURCE}/callsign/{callsign}"
            route_request = urllib.request.Request(route_url,
                                                   headers={"User-Agent": "YYC-flightboard/0.2 personal"})
            try:
                with urllib.request.urlopen(route_request, timeout=8) as response:
                    return parse_metadata(json.load(response))
            except urllib.error.HTTPError as route_exc:
                if route_exc.code == 404:
                    return None
                raise
        if exc.code == 404:
            return None
        raise


def text_width(text: str) -> int:
    return max(0, len(text) * 6 - 1)


def scroll_offset(text: str, elapsed: float, width: int = 32) -> int:
    overflow = max(0, text_width(text) - width)
    return -min(overflow, max(0, int((elapsed - 2.0) * 8)))


def clock_lines(settings: Settings, now: datetime | None = None) -> tuple[str, str]:
    """Return 24-hour time and a short date in the selected time zone."""
    zone = ZoneInfo(settings.timezone)
    local = (now or datetime.now(zone)).astimezone(zone)
    return local.strftime("%H:%M"), f"{local:%a %b} {local.day}".upper()


def clock_scroll_period(date_text: str) -> float:
    """Hold both ends of the date before restarting its scroll."""
    overflow = max(0, text_width(date_text) - 32)
    return 4.0 + overflow / 8.0


def text_pixels(text: str, x: int, y: int, color: tuple[int, int, int], min_x: int = 0):
    for char in text.upper():
        glyph = FONT.get(char, FONT[" "])
        for dy, row in enumerate(glyph):
            for dx, bit in enumerate(row):
                if bit == "1" and min_x <= x + dx < 32 and 0 <= y + dy < 16:
                    yield (x + dx, y + dy, color)
        x += 6


def frame(top: str, bottom: str, elapsed: float = 0, error: bool = False,
          settings: Settings | None = None, dots: int = 0, active_dot: int = 0,
          progress: float | None = None, icon: str | None = None):
    settings = settings or Settings()
    pixels = [(0, 0, 0)] * (32 * 16)
    text_start = 9 if icon and settings.icons_enabled else 0
    for x, y, color in text_pixels(top, text_start + scroll_offset(top, elapsed, 32 - text_start), 0,
                                   rgb(settings.accent_color) if error else rgb(settings.top_color),
                                   min_x=text_start):
        pixels[y * 32 + x] = color
    if text_start:
        symbol = ICONS.get(icon, ICONS["plane"])
        icon_color = {"maple": (255, 65, 57), "westjet": (58, 208, 219),
                      "delta": (235, 47, 56)}.get(icon, rgb(settings.accent_color))
        for y, row in enumerate(symbol):
            for x, bit in enumerate(row):
                if bit == "1":
                    pixels[y * 32 + x] = icon_color
    for x, y, color in text_pixels(bottom, scroll_offset(bottom, elapsed), 8,
                                   rgb(settings.bottom_color)):
        pixels[y * 32 + x] = color
    if progress is not None:
        lit = round(max(0, min(1, progress)) * 32)
        dim = tuple(round(channel * .16) for channel in rgb(settings.accent_color))
        for x in range(32):
            pixels[15 * 32 + x] = rgb(settings.accent_color) if x < lit else dim
    elif dots > 0:
        start = (32 - (dots * 4 - 2)) // 2
        dim = tuple(round(channel * .20) for channel in rgb(settings.accent_color))
        for i in range(dots):
            for x in (start + i * 4, start + i * 4 + 1):
                pixels[15 * 32 + x] = rgb(settings.accent_color) if i == active_dot else dim
    return pixels


def icon_for(aircraft: Aircraft, metadata: Metadata) -> str:
    callsign = aircraft.callsign
    iata = metadata.iata_callsign or ""
    if callsign.startswith("ACA") or iata.startswith("AC"):
        return "maple"
    if callsign.startswith(("WJA", "WEN")) or iata.startswith("WS"):
        return "westjet"
    if callsign.startswith("DAL") or iata.startswith("DL"):
        return "delta"
    return "plane"


def route_progress(aircraft: Aircraft, metadata: Metadata) -> float | None:
    """Approximate fraction along the great-circle route, without an ETA."""
    if not metadata.origin_position or not metadata.destination_position:
        return None
    if aircraft.lat is None or aircraft.lon is None:
        return None

    def vector(position):
        lat, lon = map(math.radians, position)
        return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))

    origin = vector(metadata.origin_position)
    destination = vector(metadata.destination_position)
    current = vector((aircraft.lat, aircraft.lon))
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    angle = math.acos(max(-1, min(1, dot(origin, destination))))
    if angle < 0.001:
        return None
    tangent = tuple((b - math.cos(angle) * a) / math.sin(angle)
                    for a, b in zip(origin, destination))
    along = math.atan2(dot(current, tangent), dot(current, origin))
    return max(0.0, min(1.0, along / angle))


def detail(aircraft: Aircraft, metadata: Metadata, page: int) -> tuple[str, str]:
    distance = f"{round(aircraft.distance_nm):02d}NM"
    altitude = f"{round(aircraft.altitude_ft / 1000)}KFT"
    if page == 0:
        return metadata.iata_callsign or aircraft.callsign, metadata.route or f"{distance} {altitude}"
    speed = f"{aircraft.speed_kt}KT" if aircraft.speed_kt is not None else "SPEED ?"
    plane = " ".join(part for part in (metadata.airline,
                                        metadata.aircraft_type or aircraft.aircraft_type) if part)
    return plane or aircraft.callsign, f"{distance} {altitude} {speed}"


def _write_status(value: dict, path: Path) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".status-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
            handle.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--label")
    parser.add_argument("--radius", type=int)
    parser.add_argument("--refresh", type=int, default=20)
    parser.add_argument("--rotate", type=int)
    parser.add_argument("--brightness", type=int)
    parser.add_argument("--mapping", default="regular")
    parser.add_argument("--software-pulse", action="store_true")
    parser.add_argument("--once", action="store_true", help="Print nearby flights; do not use GPIO")
    args = parser.parse_args()

    def configured() -> Settings:
        from dataclasses import replace
        from settings import validate_settings
        current = load_settings(args.settings)
        overrides = {name: getattr(args, name) for name in
                     ("lat", "lon", "label", "radius", "rotate", "brightness")
                     if getattr(args, name) is not None}
        return validate_settings(replace(current, **overrides).to_dict())

    if args.refresh < 5:
        parser.error("refresh must be at least 5 seconds")
    try:
        settings = configured()
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.once:
        for aircraft in fetch_aircraft(settings.lat, settings.lon, settings.radius):
            print(f"{aircraft.callsign:8} {aircraft.distance_nm:5.1f} NM  "
                  f"{str(aircraft.altitude_ft):>6} ft  {str(aircraft.speed_kt):>3} kt")
        return 0

    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    options = RGBMatrixOptions()
    options.rows = 16
    options.cols = 32
    options.chain_length = 1
    options.parallel = 1
    options.hardware_mapping = args.mapping
    options.brightness = effective_brightness(settings)
    options.drop_priv_user = "flightboard"
    options.drop_priv_group = "flightboard"
    sound_module_loaded = "snd_bcm2835 " in Path("/proc/modules").read_text()
    options.disable_hardware_pulsing = args.software_pulse or sound_module_loaded
    if sound_module_loaded and not args.software_pulse:
        print("Onboard audio is loaded; using software pulse timing", file=sys.stderr, flush=True)
    matrix = RGBMatrix(options=options)
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    canvas = matrix.CreateFrameCanvas()

    def show(top: str, bottom: str, elapsed: float, *, error: bool = False,
             dots: int = 0, active_dot: int = 0, progress: float | None = None,
             icon: str | None = None):
        nonlocal canvas
        pixels = frame(top, bottom, elapsed, error, settings, dots, active_dot, progress,
                       icon)
        for y in range(16):
            for x in range(32):
                canvas.SetPixel(x, y, *pixels[y * 32 + x])
        canvas = matrix.SwapOnVSync(canvas)

    executor = ThreadPoolExecutor(max_workers=3)
    flights: list[Aircraft] = []
    selected_flights: list[Aircraft] = []
    tracked: Aircraft | None = None
    resolved_flight = settings.flight
    metadata_cache: dict[tuple[str, str], tuple[float, Metadata | None]] = {}
    metadata_future: Future[Metadata | None] | None = None
    metadata_key: tuple[str, str] | None = None
    fetch_future: Future[list[Aircraft]] | None = None
    fetch_generation = 0
    track_future: Future[tuple[Aircraft | None, str]] | None = None
    track_generation = 0
    generation = 0
    next_lookup = next_fetch = next_status = 0.0
    next_track = time.monotonic() + 1.2
    next_settings_check = 0.0
    settings_mtime = args.settings.stat().st_mtime_ns if args.settings.exists() else None
    screen_end = screen_start = 0.0
    screen_top, screen_bottom = settings.label, "STARTING"
    screen_dots = screen_active_dot = 0
    screen_progress = None
    screen_icon = None
    next_credit = time.monotonic() + 60
    index = 0
    nearby_failed = False
    track_failed = False
    if settings.display_enabled and settings.mode != "clock":
        show(screen_top, screen_bottom, 0)
    else:
        matrix.Clear()
    try:
        while running:
            now = time.monotonic()
            if now >= next_settings_check:
                next_settings_check = now + 1
                mtime = args.settings.stat().st_mtime_ns if args.settings.exists() else None
                if mtime != settings_mtime:
                    try:
                        updated = configured()
                        settings_mtime = mtime
                        if updated != settings:
                            old = settings
                            settings = updated
                            if old.display_enabled and not settings.display_enabled:
                                matrix.Clear()
                            index = 0
                            screen_end = 0
                            next_status = 0
                            location_changed = ((old.lat, old.lon, old.radius) !=
                                                (settings.lat, settings.lon, settings.radius))
                            target_changed = ((old.mode, old.flight) !=
                                              (settings.mode, settings.flight))
                            if location_changed or target_changed:
                                generation += 1
                                next_fetch = now + 1.2
                                next_track = now + 1.2
                            if location_changed:
                                flights = []
                                selected_flights = []
                                nearby_failed = False
                            if target_changed:
                                resolved_flight = settings.flight
                                tracked = None
                                track_failed = False
                            if settings.mode == "clock":
                                flights = []
                                selected_flights = []
                                nearby_failed = False
                            selected_flights = select_flights(flights, settings.max_planes)
                    except (ValueError, json.JSONDecodeError) as exc:
                        print(f"settings error: {exc}", file=sys.stderr, flush=True)
                brightness = effective_brightness(settings)
                if matrix.brightness != brightness:
                    matrix.brightness = brightness

            if settings.mode != "clock" and fetch_future is None and now >= next_fetch:
                fetch_future = executor.submit(fetch_aircraft, settings.lat,
                                               settings.lon, settings.radius)
                fetch_generation = generation
                next_fetch = now + args.refresh
            if fetch_future is not None and fetch_future.done():
                try:
                    result = fetch_future.result()
                    if fetch_generation == generation:
                        flights = result
                        selected_flights = select_flights(flights, settings.max_planes)
                        nearby_failed = False
                except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
                    print(f"feed error: {exc}", file=sys.stderr, flush=True)
                    if fetch_generation == generation:
                        flights = []
                        selected_flights = []
                        nearby_failed = True
                        screen_end = 0
                fetch_future = None
                metadata_cache = {key: value for key, value in metadata_cache.items()
                                  if value[0] > now}

            if settings.mode == "flight" and track_future is None and now >= next_track:
                track_future = executor.submit(fetch_tracked_aircraft, resolved_flight,
                                               settings.lat, settings.lon)
                track_generation = generation
                next_track = now + args.refresh
            if track_future is not None and track_future.done():
                try:
                    result, alias = track_future.result()
                    if track_generation == generation:
                        tracked = result
                        resolved_flight = alias
                        track_failed = False
                        screen_end = 0
                except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
                    print(f"flight lookup error: {exc}", file=sys.stderr, flush=True)
                    if track_generation == generation:
                        tracked = None
                        track_failed = True
                        screen_end = 0
                track_future = None

            if metadata_future is not None and metadata_future.done():
                try:
                    found = metadata_future.result()
                    metadata_cache[metadata_key] = (now + (21600 if found else 3600), found)
                except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
                    print(f"metadata error: {exc}", file=sys.stderr, flush=True)
                    metadata_cache[metadata_key] = (now + 120, None)
                metadata_future = None
                metadata_key = None
            if settings.mode != "clock" and metadata_future is None and now >= next_lookup:
                candidates = ([tracked] if tracked else []) + selected_flights
                for aircraft in candidates:
                    key = (aircraft.hex_code, aircraft.callsign)
                    if key not in metadata_cache:
                        metadata_future = executor.submit(lookup_metadata, aircraft)
                        metadata_key = key
                        next_lookup = now + 5
                        break

            failed = (track_failed if settings.mode == "flight" else
                      nearby_failed if settings.mode == "nearby" else False)
            if settings.mode == "clock":
                clock_top, clock_bottom = clock_lines(settings)
                if screen_bottom != clock_bottom or screen_end == 0:
                    screen_start = now
                if screen_top != clock_top or screen_bottom != clock_bottom:
                    next_status = 0
                screen_top, screen_bottom = clock_top, clock_bottom
                screen_end = float("inf")
                screen_dots = screen_active_dot = 0
                screen_progress = None
                screen_icon = None
            elif now >= screen_end:
                screen_dots = screen_active_dot = 0
                screen_progress = None
                screen_icon = None
                if now >= next_credit:
                    screen_top, screen_bottom = "ADSB.FI", "LIVE DATA"
                    next_credit = now + 60
                elif settings.mode == "flight":
                    if tracked is None:
                        screen_top = settings.flight
                        screen_bottom = "WAITING" if not failed else "API DELAY"
                    else:
                        key = (tracked.hex_code, tracked.callsign)
                        info = metadata_cache.get(key, (0, None))[1] or Metadata()
                        screen_progress = route_progress(tracked, info)
                        if index % 2 == 0:
                            screen_top = info.iata_callsign or tracked.callsign
                            screen_bottom = info.route or "ROUTE UNKNOWN"
                            screen_icon = icon_for(tracked, info)
                        else:
                            screen_top = " ".join(part for part in
                                                  (info.airline, info.aircraft_type or tracked.aircraft_type)
                                                  if part) or tracked.callsign
                            altitude = (f"{round(tracked.altitude_ft / 1000)}KFT"
                                        if tracked.altitude_ft is not None else "GROUND")
                            speed = (f"{tracked.speed_kt}KT" if tracked.speed_kt is not None
                                     else "SPEED ?")
                            screen_bottom = f"{altitude} {speed}"
                        index += 1
                elif selected_flights:
                    current = (index // 2) % len(selected_flights)
                    aircraft = selected_flights[current]
                    key = (aircraft.hex_code, aircraft.callsign)
                    info = metadata_cache.get(key, (0, None))[1] or Metadata()
                    screen_top, screen_bottom = detail(aircraft, info, index % 2)
                    if index % 2 == 0:
                        screen_icon = icon_for(aircraft, info)
                    screen_dots, screen_active_dot = len(selected_flights), current
                    index += 1
                else:
                    screen_top = settings.label
                    screen_bottom = "API DELAY" if failed else "NO FLIGHTS"
                screen_start = now
                top_width = 23 if screen_icon and settings.icons_enabled else 32
                overflow = max(text_width(screen_top) - top_width,
                               text_width(screen_bottom) - 32)
                screen_end = now + max(settings.rotate, 4 + max(0, overflow) / 8)

            if settings.display_enabled:
                display_elapsed = now - screen_start
                if settings.mode == "clock":
                    display_elapsed %= clock_scroll_period(screen_bottom)
                show(screen_top, screen_bottom, display_elapsed,
                     error=screen_bottom == "API DELAY", dots=screen_dots,
                     active_dot=screen_active_dot, progress=screen_progress, icon=screen_icon)
            if now >= next_status:
                next_status = now + 5
                try:
                    _write_status({
                        "state": ("off" if not settings.display_enabled else
                                  "delayed" if failed else "live"),
                        "display_enabled": settings.display_enabled,
                        "mode": settings.mode,
                        "title": screen_top if settings.display_enabled else "DISPLAY OFF",
                        "detail": screen_bottom if settings.display_enabled else "Turn on in settings",
                        "progress_percent": (round(screen_progress * 100)
                                             if settings.display_enabled and screen_progress is not None
                                             else None),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "nearby": [{"callsign": item.callsign, "distance_nm": item.distance_nm,
                                    "altitude_ft": item.altitude_ft}
                                   for item in flights[:10]],
                    }, STATE_DIR / "status.json")
                except OSError as exc:
                    print(f"status error: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.1)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        matrix.Clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
