#!/usr/bin/env python3
"""Configurable desk display for a 32x16 HUB75 RGB matrix.

The main loop plays the lineup from library.json through player.py, with data
from providers.py and the aircraft provider below (adsb.fi + ADSBdb).
"""

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

import render
from settings import DEFAULT_PATH, STATE_DIR, Settings, effective_brightness, load_settings

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
# The 5x7 font now lives in render.py; these names stay for older callers and tests.
FONT = render.FONT
ICONS = {name: tuple(row.replace("#", "1").replace(".", "0") for row in render.ICONS[name])
         for name in ("plane", "maple", "westjet", "delta")}


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




def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2 (0 = north, clockwise)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _arrow_route(route: str | None) -> str | None:
    return route.replace("-", ">") if isinstance(route, str) and route else None


def _iso(epoch: float | None) -> str | None:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class AircraftProvider:
    """Fetches nearby and followed aircraft off the render thread for snapshot["aircraft"].

    `update(needs)` is called every frame: it collects finished fetches and
    starts due ones (`aircraft:nearby` and `aircraft:follow:<CALLSIGN>`), one
    metadata lookup at a time, on the `refresh` cadence. It never blocks.
    """

    NEARBY_LIMIT = 20
    KEEP_AFTER_ERROR_S = 120
    LOOKUP_SPACING_S = 5
    CALLSIGN_RE = re.compile(r"[A-Z0-9]{2,10}")

    def __init__(self, settings, refresh: float = 20, *, executor=None,
                 monotonic_fn=time.monotonic, now_fn=time.time, on_success=None):
        self.settings = settings
        self.refresh = refresh
        self._own_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="aircraft")
        self._mono = monotonic_fn
        self._now = now_fn
        self._on_success = on_success
        self._generation = 0
        self._nearby: list[Aircraft] | None = None
        self._nearby_at: float | None = None
        self._nearby_error: str | None = None
        self._nearby_future: Future | None = None
        self._nearby_generation = 0
        self._next_nearby = 0.0
        self._follow: dict[str, dict] = {}
        self._metadata: dict[tuple[str, str], tuple[float, Metadata | None]] = {}
        self._meta_future: Future | None = None
        self._meta_key: tuple[str, str] | None = None
        self._next_lookup = 0.0

    def set_settings(self, settings) -> None:
        old = self.settings
        self.settings = settings
        if (old.lat, old.lon, old.radius) != (settings.lat, settings.lon, settings.radius):
            self._generation += 1
            self._nearby, self._nearby_at, self._nearby_error = None, None, None
            self._next_nearby = 0.0

    @property
    def nearby(self) -> list[Aircraft]:
        return list(self._nearby or ())

    def _succeeded(self) -> None:
        if self._on_success:
            try:
                self._on_success()
            except Exception as exc:  # noqa: BLE001 - health reporting must not stop flights
                _log(f"health error: {exc}")

    def _poll(self, mono: float) -> None:
        future = self._nearby_future
        if future is not None and future.done():
            self._nearby_future = None
            try:
                result = future.result()
                if self._nearby_generation == self._generation:
                    self._nearby, self._nearby_at, self._nearby_error = result, self._now(), None
                    self._succeeded()
            except Exception as exc:  # noqa: BLE001
                _log(f"feed error: {exc}")
                if self._nearby_generation == self._generation:
                    self._nearby_error = str(exc) or type(exc).__name__
                    if self._nearby_at is None or self._now() - self._nearby_at > self.KEEP_AFTER_ERROR_S:
                        self._nearby = None
        for callsign, entry in self._follow.items():
            future = entry["future"]
            if future is None or not future.done():
                continue
            entry["future"] = None
            try:
                found, alias = future.result()
                entry.update(found=found, alias=alias, at=self._now(), error=None)
                self._succeeded()
            except Exception as exc:  # noqa: BLE001
                _log(f"flight lookup error ({callsign}): {exc}")
                entry.update(found=None, error=str(exc) or type(exc).__name__)
        if self._meta_future is not None and self._meta_future.done():
            try:
                found = self._meta_future.result()
                self._metadata[self._meta_key] = (mono + (21600 if found else 3600), found)
            except Exception as exc:  # noqa: BLE001
                _log(f"metadata error: {exc}")
                self._metadata[self._meta_key] = (mono + 120, None)
            self._meta_future, self._meta_key = None, None
            self._metadata = {k: v for k, v in self._metadata.items() if v[0] > mono}

    def update(self, needs) -> None:
        mono = self._mono()
        self._poll(mono)
        settings = self.settings
        follows = sorted({need[16:] for need in needs if need.startswith("aircraft:follow:")
                          and self.CALLSIGN_RE.fullmatch(need[16:])})
        for callsign in [c for c in self._follow if c not in follows]:
            if self._follow[callsign]["future"] is None:
                del self._follow[callsign]
        try:
            if "aircraft:nearby" in needs and self._nearby_future is None and mono >= self._next_nearby:
                self._nearby_future = self._executor.submit(fetch_aircraft, settings.lat,
                                                            settings.lon, settings.radius)
                self._nearby_generation = self._generation
                self._next_nearby = mono + self.refresh
            for callsign in follows:
                entry = self._follow.setdefault(callsign, {"found": None, "alias": callsign,
                                                           "future": None, "next": 0.0,
                                                           "at": None, "error": None})
                if entry["future"] is None and mono >= entry["next"]:
                    entry["future"] = self._executor.submit(fetch_tracked_aircraft, entry["alias"],
                                                            settings.lat, settings.lon)
                    entry["next"] = mono + self.refresh
            self._poll(mono)  # an inline executor has already finished
            if self._meta_future is None and mono >= self._next_lookup:
                candidates = [e["found"] for c, e in self._follow.items() if c in follows and e["found"]]
                if "aircraft:nearby" in needs:
                    candidates += select_flights(self.nearby, settings.max_planes)
                for aircraft in candidates:
                    key = (aircraft.hex_code, aircraft.callsign)
                    if key not in self._metadata:
                        self._meta_future = self._executor.submit(lookup_metadata, aircraft)
                        self._meta_key = key
                        self._next_lookup = mono + self.LOOKUP_SPACING_S
                        break
        except RuntimeError:  # executor shut down while stopping
            return
        self._poll(mono)

    def _info(self, aircraft: Aircraft) -> Metadata:
        return self._metadata.get((aircraft.hex_code, aircraft.callsign), (0, None))[1] or Metadata()

    def _nearby_entry(self, aircraft: Aircraft) -> dict:
        info = self._info(aircraft)
        bearing = (round(bearing_deg(self.settings.lat, self.settings.lon, aircraft.lat, aircraft.lon), 1)
                   if aircraft.lat is not None and aircraft.lon is not None else None)
        return {"callsign": aircraft.callsign, "route": _arrow_route(info.route),
                "distance_nm": round(aircraft.distance_nm, 1), "altitude_ft": aircraft.altitude_ft,
                "speed_kt": aircraft.speed_kt, "icon": icon_for(aircraft, info), "bearing_deg": bearing}

    def _tracked_entry(self, callsign: str, aircraft: Aircraft) -> dict:
        info = self._info(aircraft)
        route = _arrow_route(info.route)
        origin, destination = route.split(">", 1) if route else (None, None)
        progress = route_progress(aircraft, info)
        remaining = None
        if (info.destination_position and aircraft.lat is not None and aircraft.lon is not None
                and aircraft.speed_kt and aircraft.speed_kt >= 30):
            left = distance_nm(aircraft.lat, aircraft.lon, *info.destination_position)
            remaining = round(left / aircraft.speed_kt * 60)
        return {"callsign": callsign, "icao": aircraft.callsign, "route": route,
                "origin": origin, "destination": destination,
                "progress": round(progress, 3) if progress is not None else None,
                "remaining_min": remaining, "altitude_ft": aircraft.altitude_ft,
                "speed_kt": aircraft.speed_kt, "distance_nm": round(aircraft.distance_nm, 1),
                "icon": icon_for(aircraft, info)}

    def snapshot(self) -> dict | None:
        """snapshot["aircraft"], or None before anything was asked for."""
        if self._nearby is None and not self._follow and self._nearby_error is None:
            return None
        nearby = None
        if self._nearby is not None:
            selected = select_flights(self._nearby, self.settings.max_planes)
            ordered = selected + [a for a in self._nearby if a not in selected]
            nearby = [self._nearby_entry(a) for a in ordered[:self.NEARBY_LIMIT]]
        follow = {callsign: (self._tracked_entry(callsign, entry["found"]) if entry["found"] else None)
                  for callsign, entry in self._follow.items()}
        stamps = [self._nearby_at] + [entry["at"] for entry in self._follow.values()]
        errors = [self._nearby_error] + [entry["error"] for entry in self._follow.values()]
        return {"nearby": nearby, "tracked": next(iter(follow.values()), None) if follow else None,
                "follow": follow, "updated_at": _iso(max((s for s in stamps if s), default=None)),
                "error": next((e for e in errors if e), None)}

    def close(self) -> None:
        if self._own_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)


# --- files ------------------------------------------------------------------------------

def _write_json(value, path: Path, mode: int = 0o644) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, default=str)
            handle.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_status(value: dict, path: Path) -> None:
    _write_json(value, path, 0o644)


def _age_s(stamp, now: float) -> int | None:
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, round(now - parsed.timestamp()))


def data_ages(data: dict, now: float | None = None) -> dict:
    """Seconds since each source last reported: {aircraft, weather, metar, iss, calendar}."""
    now = time.time() if now is None else now
    section = lambda key: data.get(key) if isinstance(data.get(key), dict) else {}
    weather = section("weather")
    metar = [entry.get("age_s") for entry in section("metar").values()
             if isinstance(entry, dict) and isinstance(entry.get("age_s"), (int, float))]
    return {"aircraft": _age_s(section("aircraft").get("updated_at"), now),
            "weather": (weather.get("age_s") if isinstance(weather.get("age_s"), (int, float))
                        else _age_s(weather.get("observed_at"), now)),
            "metar": max(metar) if metar else None,
            "iss": _age_s(section("iss").get("updated_at"), now),
            "calendar": _age_s(section("calendar").get("updated_at"), now)}


def build_status(settings, info: dict, pixels, data: dict, now: float | None = None) -> dict:
    """status.json for the web UI: the old keys plus the live frame and lineup state."""
    now = time.time() if now is None else now
    on = bool(settings.display_enabled)
    aircraft = data.get("aircraft") if isinstance(data.get("aircraft"), dict) else {}
    health = data.get("health") if isinstance(data.get("health"), dict) else {}
    tracked = aircraft.get("tracked") if isinstance(aircraft.get("tracked"), dict) else None
    progress = tracked.get("progress") if tracked else None
    pin = info.get("pin") if info.get("pinned") else None
    if info.get("interrupt"):
        detail_text = {"plane_overhead": "Plane overhead", "timer_done": "Timer done",
                       "rain_soon": "Rain soon", "iss_overhead": "ISS overhead"}.get(
                           info["interrupt"], info["interrupt"])
    elif pin:
        detail_text = "Pinned"
    else:
        detail_text = info.get("moment") or "Always on"
    return {
        "state": ("off" if not on else
                  "delayed" if aircraft.get("error") or health.get("net_ok") is False else "live"),
        "display_enabled": on,
        "mode": "lineup",
        "title": info.get("screen_name") if on else "DISPLAY OFF",
        "detail": detail_text if on else "Turn on in settings",
        "progress_percent": (round(progress * 100) if on and isinstance(progress, (int, float))
                             else None),
        "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "nearby": [{key: plane.get(key) for key in ("callsign", "distance_nm", "altitude_ft", "route")}
                   for plane in (aircraft.get("nearby") or [])[:10] if isinstance(plane, dict)],
        "frame": render.to_hex(pixels if on else [render.BLACK] * 512),
        "screen_id": info.get("screen_id"),
        "screen_name": info.get("screen_name"),
        "moment": None if pin else info.get("moment"),
        "pinned": pin,
        "data_age": data_ages(data, now),
        "feed_age_s": health.get("feed_age_s"),
    }


def brightness_for(settings, moment_brightness: int | None) -> int:
    try:
        return effective_brightness(settings, moment_brightness=moment_brightness)
    except TypeError:  # settings.py from before the lineup
        return effective_brightness(settings)


# --- main loop ----------------------------------------------------------------------------

FRAME_S = 0.05
RELOAD_S = 1.0
SNAPSHOT_S = 1.0
STATUS_S = 2.0
DATA_S = 30.0


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--library", type=Path, help="library.json (default: next to settings)")
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
    args = parser.parse_args(argv)
    if args.refresh < 5:
        parser.error("refresh must be at least 5 seconds")
    args.parser = parser
    return args


def configured(args) -> Settings:
    """Settings from disk with command-line overrides applied and validated."""
    from dataclasses import replace
    from settings import validate_settings
    current = load_settings(args.settings)
    overrides = {name: getattr(args, name) for name in
                 ("lat", "lon", "label", "radius", "rotate", "brightness")
                 if getattr(args, name, None) is not None}
    return validate_settings(replace(current, **overrides).to_dict())


def library_path(args) -> Path:
    if getattr(args, "library", None):
        return args.library
    try:
        import library
        return Path(library.LIBRARY_PATH)
    except (ImportError, AttributeError):
        return STATE_DIR / "library.json"


def load_library(path: Path, settings) -> dict:
    """library.load_library when available (validates and migrates); raises on bad files."""
    try:
        import library
    except ImportError:
        _log("library.py is missing; playing the default lineup")
        return {}
    return library.load_library(path, settings)


def _mtime(path: Path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def run(matrix, args, *, stop_after: int | None = None, stop_event: threading.Event | None = None,
        state_dir: Path | None = None, providers=None, aircraft=None,
        monotonic=time.monotonic, sleep=time.sleep) -> int:
    """Drive `matrix` (an RGBMatrix or a fake with the same methods) until stopped.

    `stop_after` ends the loop after that many frames (tests).
    """
    from player import Player
    from providers import Providers

    state_dir = Path(state_dir or STATE_DIR)
    settings = configured(args)
    lib_path = library_path(args)
    settings_mtime, lib_mtime = _mtime(args.settings), _mtime(lib_path)
    try:
        lib = load_library(lib_path, settings)
    except (OSError, ValueError) as exc:
        _log(f"library error: {exc}")
        lib = {}
    player = Player(lib, settings)
    providers = providers or Providers(settings, state_dir)
    aircraft = aircraft or AircraftProvider(settings, args.refresh,
                                            on_success=providers.mark_network_ok)
    canvas = matrix.CreateFrameCanvas()
    shown = None
    brightness = None
    snapshot: dict = {}
    data: dict = {}
    pixels, info = [render.BLACK] * 512, {}
    next_reload = next_snapshot = next_status = 0.0
    next_data = monotonic() + DATA_S
    frames = 0
    matrix.Clear()
    try:
        while not (stop_event and stop_event.is_set()):
            now = monotonic()
            if now >= next_reload:
                next_reload = now + RELOAD_S
                mtime = _mtime(args.settings)
                if mtime != settings_mtime:
                    settings_mtime = mtime
                    try:
                        updated = configured(args)
                    except (ValueError, OSError) as exc:
                        _log(f"settings error: {exc}")
                    else:
                        if updated != settings:
                            settings = updated
                            player.set_settings(settings)
                            providers.set_settings(settings)
                            aircraft.set_settings(settings)
                            next_snapshot = next_status = now
                mtime = _mtime(lib_path)
                if mtime != lib_mtime:
                    lib_mtime = mtime
                    try:
                        lib = load_library(lib_path, settings)
                        player.set_library(lib)
                        next_status = now
                    except (OSError, ValueError) as exc:
                        _log(f"library error: {exc}")
            needs = player.needs()
            providers.update(needs, lib.get("feeds") or [])
            aircraft.update(needs)
            if now >= next_snapshot:
                next_snapshot = now + SNAPSHOT_S
                snapshot = providers.snapshot()
            data = dict(snapshot)
            planes = aircraft.snapshot()
            if planes is not None:
                data["aircraft"] = planes
            try:
                pixels, info = player.tick(now, data)
            except Exception as exc:  # noqa: BLE001 - one bad screen must not stop the panel
                _log(f"render error: {exc}")
            if settings.display_enabled:
                wanted = brightness_for(settings, info.get("moment_brightness"))
                if wanted != brightness:
                    brightness = matrix.brightness = wanted
                    shown = None  # brightness applies when pixels are set
                if pixels != shown:
                    for y in range(16):
                        row = y * 32
                        for x in range(32):
                            canvas.SetPixel(x, y, *pixels[row + x])
                    canvas = matrix.SwapOnVSync(canvas)
                    shown = pixels
            elif shown is not None or brightness is not None:
                matrix.Clear()
                shown = brightness = None
            if now >= next_status:
                next_status = now + STATUS_S
                try:
                    _write_status(build_status(settings, info, pixels, data), state_dir / "status.json")
                except OSError as exc:
                    _log(f"status error: {exc}")
            if now >= next_data:
                next_data = now + DATA_S
                try:
                    _write_json(data, state_dir / "data.json", 0o640)
                except (OSError, TypeError, ValueError) as exc:
                    _log(f"data error: {exc}")
            frames += 1
            if stop_after is not None and frames >= stop_after:
                break
            sleep(max(0.0, now + (FRAME_S if settings.display_enabled else 4 * FRAME_S) - monotonic()))
    finally:
        aircraft.close()
        providers.close()
        matrix.Clear()
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        settings = configured(args)
    except (ValueError, json.JSONDecodeError) as exc:
        args.parser.error(str(exc))
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
    stop_event = threading.Event()

    def stop(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    # The library loads after RGBMatrix dropped root, so a migrated library.json
    # belongs to the flightboard user like the web server's files.
    return run(matrix, args, stop_event=stop_event)


if __name__ == "__main__":
    raise SystemExit(main())
