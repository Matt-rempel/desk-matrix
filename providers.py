"""Background data providers: weather, METAR, ISS, sun, calendar, JSON feeds, health.

`Providers.update(needs, feeds)` schedules due fetches on a small thread pool and
returns immediately; `Providers.snapshot()` returns a thread-safe copy of the last
good values in the shape of Contract 3 (docs/REDESIGN_PLAN.md). Standard library only.
"""

from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
import copy
from datetime import date, datetime, time as dtime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

USER_AGENT = "Flightboard/0.4 personal (desk matrix)"
MAX_BYTES = 1024 * 1024
FETCH_TIMEOUT = 10

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
METAR_URL = "https://aviationweather.gov/api/data/metar"
ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
CPU_TEMP_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
# Raspberry Pi firmware flags: bit 0 under-voltage now; bits 1-3 frequency capped,
# throttled or at the soft temperature limit now.
THROTTLED_PATH = Path("/sys/devices/platform/soc/soc:firmware/get_throttled")
NET_PROBE = ("1.1.1.1", 443)  # a TCP connect only, made while the offline alert is on

# Refresh intervals in seconds (plan: weather 15 min, METAR 10 min, ISS 30 s,
# calendar 15 min, feeds per feed with a 60 s floor).
INTERVALS = {"weather": 900, "metar": 600, "iss": 30, "calendar": 900, "net": 60}
FEED_MIN_INTERVAL = 60
FEED_DEFAULT_INTERVAL = 300
BACKOFF_BASE = 60
BACKOFF_CAP = 1800
NET_OK_WINDOW = 600
PRUNE_AFTER = 3600
ISS_OVERHEAD_KM = 1500
EARTH_RADIUS_KM = 6371.0
ICAO_RE = re.compile(r"[A-Z0-9]{4}")
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


# --------------------------------------------------------------------------- HTTP

def _read_limited(response, limit: int = MAX_BYTES) -> bytes:
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("response too large")
    return body


def _check_url(url: str) -> str:
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("URL must be http or https")
    return url


def _get_text(url: str, timeout: float = FETCH_TIMEOUT) -> str:
    """GET `url` and return the body as text (≤ 1 MB)."""
    request = urllib.request.Request(_check_url(url), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return _read_limited(response).decode("utf-8", errors="replace")


def _get_json(url: str, timeout: float = FETCH_TIMEOUT):
    """GET `url` and decode the JSON body (≤ 1 MB)."""
    request = urllib.request.Request(_check_url(url), headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = _read_limited(response).decode("utf-8")
    return json.loads(body) if body.strip() else None  # e.g. HTTP 204 for an unknown station


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return "timeout" if isinstance(reason, TimeoutError) else f"network: {reason}"[:80]
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "bad JSON"
    return (str(exc) or type(exc).__name__)[:80]


def iso_utc(value: float | datetime | None) -> str | None:
    """Epoch seconds or aware datetime → `YYYY-MM-DDTHH:MM:SSZ`."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromtimestamp(value, timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _zone(name) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(name) if isinstance(name, str) and name else timezone.utc
    except (ValueError, ZoneInfoNotFoundError):
        return timezone.utc


def _num(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


# ----------------------------------------------------------------------- weather

def wmo_icon(code, is_day: bool = True) -> str | None:
    """Map a WMO weather code to sun|cloud|rain|snow|storm|fog|moon."""
    code = _num(code)
    if code is None:
        return None
    code = int(code)
    if code in (0, 1):
        return "sun" if is_day else "moon"
    if code in (2, 3):
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if 95 <= code <= 99:
        return "storm"
    return "cloud"


def weather_url(lat: float, lon: float, tz: str) -> str:
    query = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "current": "temperature_2m,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min",
        "hourly": "temperature_2m,precipitation",
        "minutely_15": "precipitation",
        "forecast_days": 2, "timezone": tz or "GMT", "timeformat": "unixtime"})
    return f"{WEATHER_URL}?{query}"


def _rain_in_min(times, amounts, step_s: int, now: float) -> int | None:
    for stamp, amount in zip(times or (), amounts or ()):
        stamp, amount = _num(stamp), _num(amount)
        if stamp is None or amount is None or amount < 0.1:
            continue
        start = stamp - step_s  # Open-Meteo sums precipitation over the preceding interval
        if stamp <= now or start > now + 7200:
            continue
        return max(0, round((start - now) / 60))
    return None


def parse_weather(payload: dict, now: float) -> dict:
    """Open-Meteo forecast JSON (timeformat=unixtime) → weather snapshot entry."""
    current = payload.get("current") or {}
    observed = _num(current.get("time"))
    result = {
        "temp_c": _num(current.get("temperature_2m")),
        "code": wmo_icon(current.get("weather_code"), bool(current.get("is_day", 1))),
        "high_c": None, "low_c": None, "hourly_c": [], "rain_in_min": None,
        "observed_at": iso_utc(observed if observed is not None else now),
    }
    daily = payload.get("daily") or {}
    days = daily.get("time") or []
    index = 0
    for i, start in enumerate(days):
        start = _num(start)
        if start is not None and start <= now < start + 86400:
            index = i
            break
    for key, name in (("high_c", "temperature_2m_max"), ("low_c", "temperature_2m_min")):
        values = daily.get(name) or []
        result[key] = _num(values[index]) if index < len(values) else None
    hourly = payload.get("hourly") or {}
    hour_start = now - now % 3600
    temps = []
    for stamp, value in zip(hourly.get("time") or [], hourly.get("temperature_2m") or []):
        stamp, value = _num(stamp), _num(value)
        if stamp is not None and value is not None and stamp >= hour_start:
            temps.append(value)
    result["hourly_c"] = temps[:12]
    minutely = payload.get("minutely_15") or {}
    if minutely.get("time") and minutely.get("precipitation"):
        result["rain_in_min"] = _rain_in_min(minutely["time"], minutely["precipitation"], 900, now)
    else:
        result["rain_in_min"] = _rain_in_min(hourly.get("time"), hourly.get("precipitation"), 3600, now)
    return result


# ------------------------------------------------------------------------- METAR

def _visibility_sm(value) -> float | None:
    number = _num(value)
    if number is not None:
        return number
    if not isinstance(value, str):
        return None
    text = value.strip().upper().replace("SM", "").lstrip("PM").rstrip("+")
    match = re.fullmatch(r"(?:(\d+)\s+)?(\d+)/(\d+)|(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    if match.group(4):
        return float(match.group(4))
    whole = int(match.group(1) or 0)
    return whole + int(match.group(2)) / max(1, int(match.group(3)))


def flight_category(visibility_sm: float | None, ceiling_ft: float | None) -> str | None:
    """FAA flight category from visibility (statute miles) and ceiling (feet AGL)."""
    if visibility_sm is None and ceiling_ft is None:
        return None
    vis = math.inf if visibility_sm is None else visibility_sm
    ceil = math.inf if ceiling_ft is None else ceiling_ft
    if ceil < 500 or vis < 1:
        return "LIFR"
    if ceil < 1000 or vis < 3:
        return "IFR"
    if ceil <= 3000 or vis <= 5:
        return "MVFR"
    return "VFR"


def _ceiling_ft(report: dict) -> float | None:
    bases = [_num(layer.get("base")) for layer in report.get("clouds") or []
             if isinstance(layer, dict) and str(layer.get("cover", "")).upper() in ("BKN", "OVC", "OVX")]
    vertical = _num(report.get("vertVis"))
    if vertical is not None:
        bases.append(vertical * 100 if vertical < 100 else vertical)
    bases = [base for base in bases if base is not None]
    return min(bases) if bases else None


def parse_metar(payload, station: str) -> dict:
    """aviationweather.gov METAR JSON → snapshot entry for `station`."""
    reports = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    report = next((r for r in reports if isinstance(r, dict)
                   and str(r.get("icaoId", "")).upper() == station), None)
    if report is None:
        report = next((r for r in reports if isinstance(r, dict)), None)
    if report is None:
        raise ValueError("no METAR for station")
    category = str(report.get("fltCat") or "").upper()
    if category not in ("VFR", "MVFR", "IFR", "LIFR"):
        category = flight_category(_visibility_sm(report.get("visib")), _ceiling_ft(report))
    wind_dir = report.get("wdir")
    if isinstance(wind_dir, str) and wind_dir.strip().upper() == "VRB":
        wind_dir = "VRB"
    else:
        wind_dir = _num(wind_dir)
        wind_dir = int(wind_dir) % 360 if wind_dir is not None else None
    observed = _num(report.get("obsTime"))
    if observed is None and isinstance(report.get("reportTime"), str):
        try:
            parsed = datetime.fromisoformat(report["reportTime"].replace("Z", "+00:00").replace(" ", "T"))
            observed = (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
        except ValueError:
            observed = None
    speed, gust = _num(report.get("wspd")), _num(report.get("wgst"))
    return {
        "station": str(report.get("icaoId") or station).upper(),
        "category": category,
        "wind_dir": wind_dir,
        "wind_kt": int(speed) if speed is not None else None,
        "gust_kt": int(gust) if gust else None,
        "observed_at": iso_utc(observed),
    }


# --------------------------------------------------------------------------- ISS

def great_circle(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Return (distance km, initial bearing degrees) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    distance = 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return distance, (math.degrees(math.atan2(y, x)) + 360) % 360


def compass8(bearing: float) -> str:
    return DIRECTIONS[int((bearing % 360 + 22.5) // 45) % 8]


def parse_iss(payload: dict, lat: float, lon: float, now: float) -> dict:
    iss_lat, iss_lon = _num(payload.get("latitude")), _num(payload.get("longitude"))
    if iss_lat is None or iss_lon is None:
        raise ValueError("ISS position missing")
    distance, bearing = great_circle(lat, lon, iss_lat, iss_lon)
    stamp = _num(payload.get("timestamp"))
    return {
        "distance_km": round(distance),
        "bearing_deg": round(bearing),
        "direction": compass8(bearing),
        "overhead": distance <= ISS_OVERHEAD_KM,
        "updated_at": iso_utc(stamp if stamp is not None else now),
    }


# --------------------------------------------------------------------------- sun

def _julian(dt: datetime) -> float:
    return dt.timestamp() / 86400 + 2440587.5


def _from_julian(jd: float) -> datetime:
    return datetime.fromtimestamp((jd - 2440587.5) * 86400, timezone.utc)


def sun_times(lat: float, lon: float, day: date, tz) -> tuple[datetime | None, datetime | None, str | None]:
    """Sunrise and sunset (UTC) for local `day` via the NOAA/Wikipedia sunrise equation.

    Returns (sunrise, sunset, None), or (None, None, "day"|"night") at polar day/night.
    """
    local_noon = datetime.combine(day, dtime(12), tz)
    n = round(_julian(local_noon) - 2451545.0 + lon / 360)
    j_star = n - lon / 360
    m = (357.5291 + 0.98560028 * j_star) % 360
    mr = math.radians(m)
    c = 1.9148 * math.sin(mr) + 0.02 * math.sin(2 * mr) + 0.0003 * math.sin(3 * mr)
    ecl = math.radians((m + c + 180 + 102.9372) % 360)
    transit = 2451545.0 + j_star + 0.0053 * math.sin(mr) - 0.0069 * math.sin(2 * ecl)
    decl = math.asin(math.sin(ecl) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    cos_w = ((math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(decl))
             / (math.cos(phi) * math.cos(decl)))
    if cos_w < -1:
        return None, None, "day"
    if cos_w > 1:
        return None, None, "night"
    w = math.degrees(math.acos(cos_w))
    return _from_julian(transit - w / 360), _from_julian(transit + w / 360), None


def sun_info(lat: float, lon: float, tz_name: str, now: datetime) -> dict:
    """Snapshot entry for the sun at `now` (aware datetime)."""
    tz = _zone(tz_name)
    today = now.astimezone(tz).date()
    rise, sset, polar = sun_times(lat, lon, today, tz)
    progress = None
    if polar == "day":
        midnight = datetime.combine(today, dtime(0), tz)
        progress = min(1.0, max(0.0, (now - midnight).total_seconds() / 86400))
    elif rise and sset and rise <= now < sset:
        progress = (now - rise).total_seconds() / max(1.0, (sset - rise).total_seconds())
    # During polar day/night the next event is the one that ends it.
    wanted = {"day": ("sunset",), "night": ("sunrise",)}.get(polar, ("sunrise", "sunset"))
    next_event = next_at = None
    for offset in range(0, 190):
        r, s, _ = sun_times(lat, lon, today + timedelta(days=offset), tz) if offset else (rise, sset, polar)
        events = sorted(e for e in ((r, "sunrise"), (s, "sunset"))
                        if e[0] is not None and e[0] > now and e[1] in wanted)
        if events:
            next_at, next_event = events[0]
            break
    return {
        "sunrise": iso_utc(rise), "sunset": iso_utc(sset),
        "next_event": next_event, "next_at": iso_utc(next_at),
        "daylight_progress": None if progress is None else round(progress, 4),
        "polar": polar,
    }


# ---------------------------------------------------------------------- calendar

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split_property(line: str) -> tuple[str, dict, str]:
    quoted = False
    for i, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ":" and not quoted:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return line.upper(), {}, ""
    parts = head.split(";")
    params = {}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        params[key.upper()] = val.strip('"')
    return parts[0].upper(), params, value


def _unescape(text: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), text)


def _ics_datetime(value: str, params: dict, default_tz) -> tuple[datetime, bool]:
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        day = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(day, dtime(0), default_tz), True
    utc = value.endswith("Z")
    parsed = datetime.strptime(value.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if utc:
        return parsed.replace(tzinfo=timezone.utc), False
    tz = default_tz
    if params.get("TZID"):
        try:
            tz = ZoneInfo(params["TZID"])
        except (ValueError, ZoneInfoNotFoundError):
            tz = default_tz
    return parsed.replace(tzinfo=tz), False


def _parse_rrule(value: str, default_tz) -> dict | None:
    parts = dict(p.partition("=")[::2] for p in value.upper().split(";") if "=" in p)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return None
    rule = {"freq": freq, "interval": 1, "count": None, "until": None, "byday": None}
    try:
        rule["interval"] = max(1, int(parts.get("INTERVAL", 1)))
        if "COUNT" in parts:
            rule["count"] = max(0, int(parts["COUNT"]))
        if "UNTIL" in parts:
            until, all_day = _ics_datetime(parts["UNTIL"], {}, default_tz)
            rule["until"] = until + timedelta(days=1) - timedelta(seconds=1) if all_day else until
    except ValueError:
        return None
    if parts.get("BYDAY"):
        days = {_WEEKDAYS[d[-2:]] for d in parts["BYDAY"].split(",") if d[-2:] in _WEEKDAYS}
        rule["byday"] = sorted(days) or None
    return rule


def parse_ics(text: str, default_tz=timezone.utc) -> list[dict]:
    """Parse VEVENTs into dicts: start (aware), all_day, title, rrule, exdates."""
    events: list[dict] = []
    current: dict | None = None
    for line in _unfold(text):
        name, params, value = _split_property(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            current = {"start": None, "all_day": False, "title": "Event", "rrule": None,
                       "exdates": set(), "cancelled": False}
        elif name == "END" and value.upper() == "VEVENT":
            if current and current["start"] is not None and not current["cancelled"]:
                events.append(current)
                if len(events) >= 5000:
                    break
            current = None
        elif current is None:
            continue
        elif name == "DTSTART":
            try:
                current["start"], current["all_day"] = _ics_datetime(value, params, default_tz)
            except ValueError:
                current["start"] = None
        elif name == "SUMMARY":
            current["title"] = _unescape(value).strip()[:64] or "Event"
        elif name == "RRULE":
            current["rrule"] = _parse_rrule(value, default_tz) or "unsupported"
        elif name == "EXDATE":
            for item in value.split(","):
                try:
                    current["exdates"].add(_ics_datetime(item, params, default_tz)[0])
                except ValueError:
                    pass
        elif name == "STATUS" and value.strip().upper() == "CANCELLED":
            current["cancelled"] = True
    return events


def _occurrences(event: dict, window_start: datetime, window_end: datetime):
    """Yield occurrences of a recurring event in ascending order up to `window_end`."""
    start: datetime = event["start"]
    rule = event["rrule"]
    tz = start.tzinfo
    first, clock = start.date(), start.timetz().replace(tzinfo=None)
    step = rule["interval"] * (7 if rule["freq"] == "WEEKLY" else 1)
    if rule["freq"] == "WEEKLY":
        days = rule["byday"] or [first.weekday()]
        anchor = first - timedelta(days=first.weekday())
    else:
        days = None
        anchor = first
    k = 0
    if rule["count"] is None:  # skip ahead; COUNT needs every occurrence counted
        k = max(0, (window_start.date() - anchor).days // step - 1)
    seen = 0
    for _ in range(100000):
        base = anchor + timedelta(days=step * k)
        candidates = [base + timedelta(days=d) for d in days] if days is not None else [base]
        for day in candidates:
            if day < first:
                continue
            if rule["freq"] == "DAILY" and rule["byday"] and day.weekday() not in rule["byday"]:
                continue
            occurrence = datetime.combine(day, clock, tz)
            if rule["until"] is not None and occurrence > rule["until"]:
                return
            seen += 1
            if rule["count"] is not None and seen > rule["count"]:
                return
            if occurrence > window_end:
                return
            if occurrence not in event["exdates"]:
                yield occurrence
        k += 1


def next_event(events: list[dict], now: datetime, days: int = 7) -> dict | None:
    """Earliest event starting at or after `now` and within `days`."""
    end = now + timedelta(days=days)
    best: tuple[datetime, dict] | None = None
    for event in events:
        rule = event.get("rrule")
        if isinstance(rule, dict):
            starts = (o for o in _occurrences(event, now, end) if o >= now)
            start = next(starts, None)
        else:
            start = event["start"]
            if not now <= start <= end:
                start = None
        if start is not None and (best is None or start < best[0]):
            best = (start, event)
    if best is None:
        return None
    return {"start": iso_utc(best[0]), "title": best[1]["title"], "all_day": best[1]["all_day"]}


# ------------------------------------------------------------------------- feeds

def extract_path(data, path: str | None):
    """Follow a dotted path (`data.0.price`) through dicts and lists; KeyError if absent."""
    if not path:
        return data
    for part in str(path).split("."):
        if isinstance(data, list):
            try:
                data = data[int(part)]
            except (ValueError, IndexError):
                raise KeyError(part) from None
        elif isinstance(data, dict) and part in data:
            data = data[part]
        else:
            raise KeyError(part)
    return data


def format_number(value: float) -> str:
    """Compact number text: trailing zeros dropped, ≤ 6 characters where sensible."""
    if not math.isfinite(value):
        return "--"
    plain = f"{value:.0f}"
    if len(plain.lstrip("-")) > 6:
        for div, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(value) >= div:
                scaled = value / div
                for digits in (2, 1, 0):
                    text = f"{scaled:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{scaled:.0f}"
                    if len(text) + 1 <= 6:
                        return text + suffix
                return f"{scaled:.0f}{suffix}"
    for digits in (4, 3, 2, 1):
        text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
        if len(text) <= 6:
            return "0" if text == "-0" else text
    return "0" if plain == "-0" else plain


def format_value(value, prefix: str = "", suffix: str = "") -> str:
    if isinstance(value, bool):
        text = "ON" if value else "OFF"
    elif isinstance(value, (int, float)):
        text = format_number(float(value))
    elif isinstance(value, str):
        number = _num(value) if re.fullmatch(r"\s*-?(?:0|[1-9]\d*)(?:\.\d+)?\s*", value) else None
        text = format_number(number) if number is not None else value.strip()
    elif value is None:
        text = "--"
    else:
        text = json.dumps(value, separators=(",", ":"))
    return f"{prefix or ''}{text[:64]}{suffix or ''}"


def extract_series(data, path: str | None) -> list[float]:
    if not path:
        return []
    values = extract_path(data, path)
    if not isinstance(values, list):
        raise ValueError("series is not a list")
    series = [v for v in (_num(item) for item in values) if v is not None]
    return series[-32:]


def parse_feed(payload, feed: dict) -> dict:
    try:
        value = extract_path(payload, feed.get("path"))
    except KeyError:
        raise ValueError("path not found") from None
    try:
        series = extract_series(payload, feed.get("series_path"))
    except (KeyError, ValueError):
        series = []
    return {"value": format_value(value, feed.get("prefix") or "", feed.get("suffix") or ""),
            "series": series}


# ------------------------------------------------------------------------ health

def cpu_temp_c(path: Path = CPU_TEMP_PATH) -> float | None:
    try:
        raw = path.read_text().strip()
    except OSError:
        return None
    value = _num(raw)
    if value is None:
        return None
    return round(value / 1000 if abs(value) > 200 else value, 1)


def throttle_flags(path: Path = THROTTLED_PATH) -> dict | None:
    """Under-voltage and throttling right now, from the Pi firmware; None elsewhere."""
    try:
        value = int(path.read_text().strip(), 16)
    except (OSError, ValueError):
        return None
    return {"under_voltage": bool(value & 0x1), "throttled": bool(value & 0xE)}


def disk_free_pct(path) -> float | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return round(usage.free * 100 / usage.total, 1) if usage.total else None


def probe_network(address=NET_PROBE, timeout: float = 4.0) -> dict:
    """Raise OSError when the internet cannot be reached."""
    with socket.create_connection(address, timeout=timeout):
        return {}


# --------------------------------------------------------------------- providers

class _Source:
    __slots__ = ("key", "data", "fetched_at", "next_due", "failures",
                 "error", "last_needed", "config", "busy")

    def __init__(self, key: str):
        self.key = key
        self.data: dict | None = None
        self.fetched_at: float | None = None  # wall clock of last success
        self.next_due = 0.0  # monotonic
        self.failures = 0
        self.busy = False
        self.error: str | None = None
        self.last_needed = 0.0
        self.config = None


class Providers:
    """Schedules background fetches for the data needs of the active screens."""

    def __init__(self, settings, state_dir=None, *, executor: Executor | None = None,
                 now_fn=time.time, monotonic_fn=time.monotonic, cpu_path: Path = CPU_TEMP_PATH,
                 throttled_path: Path = THROTTLED_PATH):
        self._lock = threading.Lock()
        self._own_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(max_workers=3, thread_name_prefix="providers")
        self._now = now_fn
        self._mono = monotonic_fn
        self._cpu_path = cpu_path
        self._sources: dict[str, _Source] = {}
        self._needs: set[str] = set()
        self._generation = 0
        self._net_ok_at: float | None = None
        self._offline_since: float | None = None  # wall clock of the first failed probe
        self._throttled_path = throttled_path
        self._net_attempted = False
        self._calendar_cache: tuple[float, dict | None] | None = None
        self._calendar_lock = threading.Lock()
        self._closed = False
        self._settings = settings
        self._state_dir = Path(state_dir) if state_dir else None
        self._seed_from_state()

    # -- settings ---------------------------------------------------------------
    def _location(self, settings=None) -> tuple[float, float, str]:
        settings = settings or self._settings
        return (float(getattr(settings, "lat", 0.0)), float(getattr(settings, "lon", 0.0)),
                str(getattr(settings, "timezone", "UTC") or "UTC"))

    def set_settings(self, settings) -> None:
        """Swap settings; a new location or calendar URL invalidates dependent caches."""
        with self._lock:
            old_loc, old_cal = self._location(), getattr(self._settings, "calendar_ics_url", "")
            self._settings = settings
            changed = []
            if self._location(settings) != old_loc:
                changed += ["weather", "iss", "calendar"]  # calendar uses the timezone
            if getattr(settings, "calendar_ics_url", "") != old_cal:
                changed.append("calendar")
            if changed:
                self._generation += 1
                for key in set(changed):
                    self._sources.pop(key, None)
                self._calendar_cache = None

    def _seed_from_state(self) -> None:
        """Reuse fresh last-known values from data.json so a restart is not blank."""
        if not self._state_dir:
            return
        try:
            path = self._state_dir / "data.json"
            if self._now() - path.stat().st_mtime > 1800:
                return
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(saved, dict):
            return
        for key in ("weather", "iss"):
            if isinstance(saved.get(key), dict):
                self._source(key).data = dict(saved[key])
        for station, entry in (saved.get("metar") or {}).items() if isinstance(saved.get("metar"), dict) else ():
            if isinstance(entry, dict) and ICAO_RE.fullmatch(str(station)):
                self._source(f"metar:{station}").data = dict(entry)
        for feed_id, entry in (saved.get("feeds") or {}).items() if isinstance(saved.get("feeds"), dict) else ():
            if isinstance(entry, dict):
                source = self._source(f"feed:{feed_id}")
                source.data = {"value": entry.get("value"), "series": list(entry.get("series") or [])}

    def _source(self, key: str) -> _Source:
        source = self._sources.get(key)
        if source is None:
            source = self._sources[key] = _Source(key)
        return source

    # -- scheduling --------------------------------------------------------------
    def update(self, needs: set[str], feeds: list[dict] | None = None) -> None:
        """Schedule fetches that are due for `needs`; never blocks."""
        feeds_by_id = {f.get("id"): f for f in feeds or () if isinstance(f, dict)}
        jobs = []
        with self._lock:
            if self._closed:
                return
            mono = self._mono()
            self._needs = set(needs)
            for need in needs:
                job = self._job_for(need, feeds_by_id)
                if job is None:
                    continue
                key, interval, fetch, config = job
                source = self._source(key)
                source.last_needed = mono
                if source.config != config:
                    if source.config is not None:
                        source.data, source.fetched_at, source.error = None, None, None
                    source.config, source.next_due, source.failures = config, 0.0, 0
                if source.busy or mono < source.next_due:
                    continue
                source.next_due = mono + interval
                jobs.append((source, fetch, interval))
            for key in [k for k, s in self._sources.items() if ":" in k
                        and not s.busy and mono - s.last_needed > PRUNE_AFTER and s.last_needed]:
                del self._sources[key]
            generation = self._generation
            for source, _, _ in jobs:
                source.busy = True
        for source, fetch, interval in jobs:  # submit outside the lock (executor may be inline)
            try:
                self._executor.submit(self._run, source, fetch, interval, generation)
            except RuntimeError:
                with self._lock:
                    source.busy = False
                    source.next_due = 0.0

    def _job_for(self, need: str, feeds_by_id: dict):
        lat, lon, tz = self._location()
        if need == "weather":
            url = weather_url(lat, lon, tz)
            return "weather", INTERVALS["weather"], lambda: self._fetch_weather(url), (lat, lon, tz)
        if need == "iss":
            return "iss", INTERVALS["iss"], lambda: parse_iss(_get_json(ISS_URL), lat, lon, self._now()), (lat, lon)
        if need == "calendar":
            url = str(getattr(self._settings, "calendar_ics_url", "") or "")
            if not url.startswith(("http://", "https://")):
                return None
            return "calendar", INTERVALS["calendar"], lambda: self._fetch_calendar(url, tz), (url, tz)
        if need.startswith("metar:"):
            station = _source_key(need)[6:]
            if not ICAO_RE.fullmatch(station):
                return None
            url = f"{METAR_URL}?{urllib.parse.urlencode({'ids': station, 'format': 'json'})}"
            return f"metar:{station}", INTERVALS["metar"], lambda: parse_metar(_get_json(url), station), station
        if need.startswith("feed:"):
            feed = feeds_by_id.get(need[5:])
            if not feed or not str(feed.get("url", "")).startswith(("http://", "https://")):
                return None
            interval = _num(feed.get("interval_s")) or FEED_DEFAULT_INTERVAL
            interval = max(FEED_MIN_INTERVAL, int(interval))
            config = tuple(str(feed.get(k) or "") for k in ("url", "path", "series_path", "prefix", "suffix"))
            feed = dict(feed)
            return need, interval, lambda: parse_feed(_get_json(feed["url"]), feed), config
        if need == "net":
            return "net", INTERVALS["net"], probe_network, None
        return None  # sun and health are computed in snapshot(); aircraft/timers live elsewhere

    def _fetch_weather(self, url: str) -> dict:
        return parse_weather(_get_json(url), self._now())

    def _fetch_calendar(self, url: str, tz_name: str) -> dict:
        return {"events": parse_ics(_get_text(url), _zone(tz_name))}

    def _run(self, source: _Source, fetch, interval: float, generation: int) -> None:
        try:
            data, error = fetch(), None
        except Exception as exc:  # noqa: BLE001 - a provider must never kill the pool
            data, error = None, _error_text(exc)
        with self._lock:
            source.busy = False
            if generation != self._generation or self._sources.get(source.key) is not source:
                return
            self._net_attempted = True
            mono = self._mono()
            if error is None:
                source.data, source.fetched_at, source.error, source.failures = data, self._now(), None, 0
                source.next_due = mono + interval
                self._net_ok_at = mono
                self._offline_since = None
                if source.key == "calendar":
                    self._calendar_cache = None
            else:
                source.failures += 1
                source.error = error
                source.next_due = mono + min(BACKOFF_CAP, BACKOFF_BASE * 2 ** (source.failures - 1))
                if source.key == "net":
                    # Keep probing every minute: the alert needs to know when it is back.
                    source.next_due = mono + INTERVALS["net"]
                    if self._offline_since is None:
                        self._offline_since = self._now()

    def mark_network_ok(self) -> None:
        """Let other providers (e.g. aircraft) report a successful fetch for health.net_ok."""
        with self._lock:
            self._net_attempted, self._net_ok_at = True, self._mono()
            self._offline_since = None

    # -- snapshot ----------------------------------------------------------------
    def snapshot(self) -> dict:
        """Thread-safe copy of all values; ages, sun and health are computed now."""
        now = self._now()
        now_dt = datetime.fromtimestamp(now, timezone.utc)
        with self._lock:
            lat, lon, tz = self._location()
            sources = {k: (copy.deepcopy(s.data), s.fetched_at, s.error)
                       for k, s in self._sources.items() if s.data is not None or s.error}
            needs = set(self._needs)
            mono = self._mono()
            net_ok = (self._net_ok_at is not None and mono - self._net_ok_at <= NET_OK_WINDOW)
            if not net_ok and not self._net_attempted:
                net_ok = None
            offline_since = self._offline_since
        snap: dict = {}
        weather = sources.get("weather", (None,))[0]
        if weather:
            weather["age_s"] = _age(weather.get("observed_at"), now)
            snap["weather"] = weather
        metar = {}
        for key, (data, _, _) in sources.items():
            if key.startswith("metar:") and data:
                data["age_s"] = _age(data.get("observed_at"), now)
                metar[key[6:]] = data
        if metar:
            snap["metar"] = metar
        if sources.get("iss", (None,))[0]:
            snap["iss"] = sources["iss"][0]
        calendar, fetched, _ = sources.get("calendar", (None, None, None))
        if calendar is not None:
            snap["calendar"] = {"next": self._calendar_next(calendar["events"], now, now_dt),
                                "updated_at": iso_utc(fetched)}
        feeds = {}
        for key, (data, fetched, error) in sources.items():
            if key.startswith("feed:"):
                data = data or {}
                feeds[key[5:]] = {"value": data.get("value"), "series": data.get("series") or [],
                                  "updated_at": iso_utc(fetched), "error": error}
        if feeds:
            snap["feeds"] = feeds
        try:
            snap["sun"] = sun_info(lat, lon, tz, now_dt)
        except (ValueError, OverflowError):
            snap["sun"] = None
        ages = []
        for need in needs:
            entry = sources.get(_source_key(need))
            if entry and entry[1] is not None:
                ages.append(now - entry[1])
        power = throttle_flags(self._throttled_path) or {}
        snap["health"] = {"cpu_temp_c": cpu_temp_c(self._cpu_path), "net_ok": net_ok,
                          "feed_age_s": round(max(ages)) if ages else None,
                          "under_voltage": power.get("under_voltage"), "throttled": power.get("throttled"),
                          "disk_free_pct": disk_free_pct(self._state_dir or "/"),
                          "offline_s": round(now - offline_since) if offline_since is not None else 0}
        return snap

    def _calendar_next(self, events: list[dict], now: float, now_dt: datetime) -> dict | None:
        with self._calendar_lock:
            return self._calendar_next_locked(events, now, now_dt)

    def _calendar_next_locked(self, events: list[dict], now: float, now_dt: datetime) -> dict | None:
        cache = self._calendar_cache
        if cache is not None:
            computed, value = cache
            start = value and datetime.fromisoformat(value["start"].replace("Z", "+00:00")).timestamp()
            if now - computed < 60 and (start is None or start >= now) and computed <= now:
                return dict(value) if value else None
        value = next_event(events, now_dt)
        self._calendar_cache = (now, value)
        return dict(value) if value else None

    def close(self) -> None:
        with self._lock:
            self._closed = True
        if self._own_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)


def _source_key(need: str) -> str:
    return "metar:" + need[6:].strip().upper() if need.startswith("metar:") else need


def _age(stamp: str | None, now: float) -> int | None:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, round(now - parsed.timestamp()))
