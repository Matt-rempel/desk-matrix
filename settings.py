"""Validated, persistent settings shared by the display and local web UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STATE_DIR = Path(os.environ.get("FLIGHTBOARD_STATE_DIR", Path(__file__).parent))
DEFAULT_PATH = STATE_DIR / "settings.json"
CALGARY_TIME = ZoneInfo("America/Edmonton")


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

    def to_dict(self) -> dict:
        return asdict(self)


def _number(value, low: float, high: float, name: str, integer: bool = False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return int(value) if integer else float(value)


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
    if mode not in ("nearby", "flight"):
        raise ValueError("Mode must be nearby or flight")
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
    for name in ("night_enabled", "icons_enabled"):
        if not isinstance(merged[name], bool):
            raise ValueError(f"{name} must be on or off")
    return Settings(
        label=label.strip().upper(),
        lat=_number(merged["lat"], -90, 90, "Latitude"),
        lon=_number(merged["lon"], -180, 180, "Longitude"),
        radius=_number(merged["radius"], 1, 250, "Radius", True),
        mode=mode,
        flight=flight,
        max_planes=_number(merged["max_planes"], 1, 5, "Plane count", True),
        rotate=_number(merged["rotate"], 8, 30, "Screen time", True),
        brightness=_number(merged["brightness"], 1, 100, "Brightness", True),
        night_enabled=merged["night_enabled"],
        night_start=merged["night_start"],
        night_end=merged["night_end"],
        night_brightness=_number(merged["night_brightness"], 1, 100, "Night brightness", True),
        timezone=timezone,
        icons_enabled=merged["icons_enabled"],
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


def effective_brightness(settings: Settings, now: datetime | None = None) -> int:
    if not settings.night_enabled:
        return settings.brightness
    local_time = ZoneInfo(settings.timezone)
    now = now or datetime.now(local_time)
    current = now.astimezone(local_time).strftime("%H:%M")
    start, end = settings.night_start, settings.night_end
    night = (start <= current < end) if start < end else (current >= start or current < end)
    return settings.night_brightness if night else settings.brightness


def rgb(color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(color[1:]))
