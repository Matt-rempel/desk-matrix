"""Validated, persistent settings shared by the display and local web UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from screens import validate_library

STATE_DIR = Path(os.environ.get("FLIGHTBOARD_STATE_DIR", Path(__file__).parent))
DEFAULT_PATH = STATE_DIR / "settings.json"
CALGARY_TIME = ZoneInfo("America/Edmonton")
# Fields kept only so library.py can migrate older installs; the lineup in
# library.json replaces them and the web form no longer edits them.
LEGACY_FIELDS = ("mode", "flight", "clock_screen_id", "custom_screens")


@dataclass(frozen=True)
class Settings:
    label: str = "WINS"
    lat: float = 51.08083
    lon: float = -114.21714
    radius: int = 25
    mode: str = "nearby"
    flight: str = ""
    max_planes: int = 3
    rotate: int = 10
    display_enabled: bool = True
    brightness: int = 85
    night_enabled: bool = False
    night_start: str = "22:00"
    night_end: str = "07:00"
    night_brightness: int = 30
    timezone: str = "America/Edmonton"
    top_color: str = "#FFFFFF"
    bottom_color: str = "#FFFF00"
    accent_color: str = "#FF7A35"
    icons_enabled: bool = True
    clock_screen_id: str = "clock-classic"
    custom_screens: tuple[dict, ...] = ()
    temp_unit: str = "C"
    distance_unit: str = "nm"
    brightness_follow_lineup: bool = True
    brightness_max: int = 100
    night_palette: bool = False
    calendar_ics_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _number(value, low: float, high: float, name: str, integer: bool = False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return int(value) if integer else float(value)


def valid_http_url(value, max_len: int = 512) -> bool:
    """An absolute http(s) URL with a host, no whitespace or control characters."""
    if not isinstance(value, str) or not 0 < len(value) <= max_len:
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    try:
        parts = urlsplit(value)
        # Reading the port raises ValueError for a malformed one.
        return (parts.scheme in ("http", "https") and bool(parts.hostname)
                and (parts.port is None or parts.port > 0))
    except ValueError:
        return False


def validate_settings(data: dict) -> Settings:
    if not isinstance(data, dict):
        raise ValueError("Settings must be an object")
    allowed = set(Settings.__dataclass_fields__)
    if set(data) - allowed:
        raise ValueError("Unknown setting")
    merged = {**Settings().to_dict(), **data}
    label = merged["label"]
    if (not isinstance(label, str) or not label.strip()
            or not re.fullmatch(r"[A-Za-z0-9 ]{1,8}", label)):
        raise ValueError("Location label must be 1–8 letters or numbers")
    mode = merged["mode"]
    if mode not in ("nearby", "flight", "clock"):
        raise ValueError("Mode must be nearby, flight, or clock")
    flight = merged["flight"]
    if not isinstance(flight, str) or (flight and not re.fullmatch(r"[A-Za-z0-9]{2,10}", flight)):
        raise ValueError("Flight must be a 2–10 character callsign or flight number")
    flight = flight.upper()
    if mode == "flight" and not flight:
        raise ValueError("Enter a flight number before selecting Follow a flight")
    colors = {}
    for name in ("top_color", "bottom_color", "accent_color"):
        value = merged[name]
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError(f"{name} must be a six-digit hex colour")
        colors[name] = value.upper()
    for name in ("night_start", "night_end"):
        value = merged[name]
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError(f"{name} must be HH:MM")
    if merged["night_start"] == merged["night_end"]:
        raise ValueError("Night start and end must differ")
    timezone = merged["timezone"]
    if not isinstance(timezone, str) or not 1 <= len(timezone) <= 64:
        raise ValueError("Time zone must be an IANA name such as America/Edmonton")
    try:
        ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Time zone must be an IANA name such as America/Edmonton") from None
    for name in ("display_enabled", "night_enabled", "icons_enabled",
                 "brightness_follow_lineup", "night_palette"):
        if not isinstance(merged[name], bool):
            raise ValueError(f"{name} must be on or off")
    if merged["temp_unit"] not in ("C", "F"):
        raise ValueError("Temperature unit must be C or F")
    if merged["distance_unit"] not in ("nm", "km"):
        raise ValueError("Distance unit must be nm or km")
    calendar_url = merged["calendar_ics_url"]
    if not isinstance(calendar_url, str):
        raise ValueError("Calendar link must be text")
    calendar_url = calendar_url.strip()
    if calendar_url and not valid_http_url(calendar_url):
        raise ValueError("Calendar link must be an http(s) address of at most 512 characters")
    custom_screens, clock_screen_id = validate_library(
        merged["custom_screens"], merged["clock_screen_id"])
    return Settings(
        label=label.strip().upper(),
        lat=_number(merged["lat"], -90, 90, "Latitude"),
        lon=_number(merged["lon"], -180, 180, "Longitude"),
        radius=_number(merged["radius"], 1, 250, "Radius", True),
        mode=mode,
        flight=flight,
        max_planes=_number(merged["max_planes"], 1, 5, "Plane count", True),
        rotate=_number(merged["rotate"], 8, 30, "Screen time", True),
        display_enabled=merged["display_enabled"],
        brightness=_number(merged["brightness"], 1, 100, "Brightness", True),
        night_enabled=merged["night_enabled"],
        night_start=merged["night_start"],
        night_end=merged["night_end"],
        night_brightness=_number(merged["night_brightness"], 1, 100, "Night brightness", True),
        timezone=timezone,
        icons_enabled=merged["icons_enabled"],
        clock_screen_id=clock_screen_id,
        custom_screens=custom_screens,
        temp_unit=merged["temp_unit"],
        distance_unit=merged["distance_unit"],
        brightness_follow_lineup=merged["brightness_follow_lineup"],
        brightness_max=_number(merged["brightness_max"], 1, 100, "Maximum brightness", True),
        night_palette=merged["night_palette"],
        calendar_ics_url=calendar_url,
        **colors,
    )


def load_settings(path: Path = DEFAULT_PATH) -> Settings:
    try:
        return validate_settings(json.loads(path.read_text()))
    except FileNotFoundError:
        return Settings()


def save_settings(settings: Settings, path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(settings.to_dict(), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def is_night(settings: Settings, now: datetime | None = None) -> bool:
    """True during the configured night hours (only when the night schedule is on)."""
    if not settings.night_enabled:
        return False
    local_time = ZoneInfo(settings.timezone)
    now = now or datetime.now(local_time)
    current = now.astimezone(local_time).strftime("%H:%M")
    start, end = settings.night_start, settings.night_end
    return (start <= current < end) if start < end else (current >= start or current < end)


def effective_brightness(settings: Settings, now: datetime | None = None,
                         moment_brightness: int | None = None) -> int:
    """The active moment's brightness when following the lineup, else day/night.

    Always capped by `brightness_max`.
    """
    if (settings.brightness_follow_lineup and isinstance(moment_brightness, int)
            and not isinstance(moment_brightness, bool) and 1 <= moment_brightness <= 100):
        value = moment_brightness
    else:
        value = settings.night_brightness if is_night(settings, now) else settings.brightness
    return max(1, min(value, settings.brightness_max))


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(color[1:]))
