"""Short-lived flight checks shared by the phone UI and matrix process.

The matrix process owns all network requests, preserving its provider rate limit.
Checking an editor draft never pins it or changes the saved screen/lineup.
"""
import json
import math
from pathlib import Path
import re
import tempfile
import time

REQUEST_NAME = "flight-check.json"
NEARBY_REQUEST_NAME = "nearby-check.json"
REQUEST_TTL_S = 120


def normalize_flight(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Enter a flight number or callsign, such as WS2231 or WJA2231")
    value = re.sub(r"[\s-]+", "", value).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", value) or not re.search(r"[A-Z]", value):
        raise ValueError("Enter a flight number or callsign, such as WS2231 or WJA2231")
    return value


def _active_request(directory: Path, name: str, now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    try:
        value = json.loads((directory / name).read_text()[:1024])
        expires = value["expires_at"]
        if (isinstance(expires, bool) or not isinstance(expires, (int, float))
                or not math.isfinite(expires) or not 0 < expires - now <= REQUEST_TTL_S):
            return None
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return None


def requested_flight(directory: Path, now: float | None = None) -> str | None:
    value = _active_request(directory, REQUEST_NAME, now)
    try:
        return normalize_flight(value["callsign"]) if value else None
    except (ValueError, KeyError):
        return None


def nearby_requested(directory: Path, now: float | None = None) -> bool:
    return _active_request(directory, NEARBY_REQUEST_NAME, now) is not None


def _request(directory: Path, name: str, fields: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".flight-check-",
                                     delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({**fields, "expires_at": time.time() + REQUEST_TTL_S}, stream)
    try:
        temporary.replace(directory / name)
    finally:
        temporary.unlink(missing_ok=True)


def request_flight(directory: Path, callsign: str) -> None:
    _request(directory, REQUEST_NAME, {"callsign": normalize_flight(callsign)})


def request_nearby(directory: Path) -> None:
    _request(directory, NEARBY_REQUEST_NAME, {})
