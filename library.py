"""library.json: custom screens, pixel art, feeds, habits, timers and the lineup.

Everything the web UI edits beyond device settings lives here. `apply_action`
is the single place that changes it; `validate_library` is strict so that a
bad request or a hand-edited file never reaches the player.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import time

import catalog
from settings import STATE_DIR, Settings, load_settings, valid_http_url

LIBRARY_PATH = STATE_DIR / "library.json"
VERSION = 1

MAX_SCREENS = 40
MAX_ART = 50
MAX_FEEDS = 10
MAX_MOMENTS = 12
MAX_ITEMS = 20
MAX_HABITS = 50
MAX_HABIT_DATES = 100
MAX_TIMERS = 50
HABIT_DAYS = 60
ART_SIZES = ((7, 7), (16, 16), (32, 16))
MAX_ART_COLORS = 16
MAX_ART_FRAMES = 8
SHOW_NOW_MAX_S = 24 * 3600

CUSTOM_ID_RE = re.compile(r"custom-[0-9a-f]{32}")
ART_ID_RE = re.compile(r"art-[0-9a-f]{16}")
FEED_ID_RE = re.compile(r"feed-[0-9a-f]{8}")
MOMENT_ID_RE = re.compile(r"m-[0-9a-f]{8}")
# Any screen id (built-in, legacy or custom); also the key format for timers.
SCREEN_REF_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")
TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ART_CHARS = frozenset(".0123456789abcdef")

SCREEN_KEYS = ("id", "name", "layout", "slots", "style", "based_on")
SLOT_KEYS = ("block", "color", "options")
ART_KEYS = ("id", "name", "w", "h", "palette", "frames", "fps")
FEED_KEYS = ("id", "name", "url", "path", "series_path", "prefix", "suffix", "interval_s")
MOMENT_KEYS = ("id", "name", "start", "end", "days", "brightness", "screens")
TIMER_KEYS = ("state", "phase", "work_min", "break_min", "ends_at", "remaining_s", "cycles")
LIBRARY_KEYS = ("version", "screens", "art", "feeds", "habits", "timers", "lineup", "pinned")

# Interruption settings: defaults plus (low, high) bounds for numeric fields.
INTERRUPT_DEFAULTS = {
    "plane_overhead": {"enabled": False, "radius_nm": 3, "max_alt_ft": 10000, "seconds": 20},
    "timer_done": {"enabled": True},
    "rain_soon": {"enabled": False, "minutes": 15},
    "iss_overhead": {"enabled": False},
}
INTERRUPT_BOUNDS = {
    "radius_nm": (1, 50), "max_alt_ft": (500, 50000), "seconds": (5, 300), "minutes": (5, 120),
}
WORK_MIN, BREAK_MIN = (1, 120), (1, 60)
DEFAULT_ITEM_SECONDS = 15


# ---------------------------------------------------------------- helpers

def _check(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(value, what: str, required=(), optional=()) -> dict:
    """An object with all `required` keys, some `optional` ones and nothing else."""
    _check(isinstance(value, dict), f"{what} must be an object")
    unknown = sorted(str(key) for key in set(value) - set(required) - set(optional))
    if unknown:
        raise ValueError(f"{what} has an unknown field: {unknown[0]}")
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError(f"{what} is missing {missing[0]}")
    return value


def _int(value, low: int, high: int, what: str) -> int:
    _check(not isinstance(value, bool) and isinstance(value, (int, float))
           and value == value and int(value) == value, f"{what} must be a whole number")
    _check(low <= value <= high, f"{what} must be between {low} and {high}")
    return int(value)


def _number(value, low: float, high: float, what: str) -> float:
    _check(not isinstance(value, bool) and isinstance(value, (int, float))
           and math.isfinite(value), f"{what} must be a number")
    _check(low <= value <= high, f"{what} must be between {low:g} and {high:g}")
    return value


def _bool(value, what: str) -> bool:
    _check(isinstance(value, bool), f"{what} must be true or false")
    return value


def _text(value, max_len: int, what: str, allow_empty: bool = True) -> str:
    _check(isinstance(value, str), f"{what} must be text")
    _check(len(value) <= max_len, f"{what} must be at most {max_len} characters")
    _check(allow_empty or value.strip(), f"{what} cannot be empty")
    _check(value.isprintable(), f"{what} contains invalid characters")
    return value


def _name(value, what: str = "Name") -> str:
    _check(isinstance(value, str), f"{what} must be text")
    value = value.strip()
    _check(1 <= len(value) <= 32, f"{what} must be 1–32 characters")
    _check(value.isprintable(), f"{what} contains invalid characters")
    return value


def _hex(value, what: str) -> str:
    _check(isinstance(value, str) and HEX_RE.fullmatch(value) is not None,
           f"{what} must be a six-digit hex color")
    return value.upper()


def _date(value, what: str) -> str:
    _check(isinstance(value, str) and DATE_RE.fullmatch(value) is not None,
           f"{what} must be a YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{what} must be a real date") from None
    return value


def _unique(ids: list, what: str) -> None:
    _check(len(ids) == len(set(ids)), f"{what} IDs must be unique")


def _new_id(prefix: str, hex_chars: int, taken) -> str:
    while True:
        candidate = prefix + secrets.token_hex(hex_chars // 2)
        if candidate not in taken:
            return candidate


def _blank_id(value) -> bool:
    return value is None or value == ""


# ---------------------------------------------------------------- screens

def validate_options(block_id: str, options) -> dict:
    """Check slot options against catalog.BLOCKS[block_id]["options"]."""
    specs = catalog.BLOCKS[block_id]["options"]
    what = catalog.BLOCKS[block_id]["name"]
    _check(isinstance(options, dict), f"{what} options must be an object")
    clean = {}
    for name, value in options.items():
        spec = specs.get(name)
        _check(spec is not None, f"{what} has no option named {name!r}")
        label = f"{what} option {name}"
        kind = spec["type"]
        if kind == "bool":
            clean[name] = _bool(value, label)
        elif kind == "int":
            clean[name] = _int(value, spec.get("min", -10**9), spec.get("max", 10**9), label)
        elif kind == "str":
            clean[name] = _text(value, spec.get("max_len", 64), label)
        elif kind == "enum":
            _check(isinstance(value, str) and value in spec["choices"],
                   f"{label} must be one of {', '.join(c or '(none)' for c in spec['choices'])}")
            clean[name] = value
        elif kind == "date":
            clean[name] = "" if value == "" else _date(value, label)
        elif kind == "color":
            clean[name] = None if value is None else _hex(value, label)
        elif kind in ("art", "feed"):
            clean[name] = _text(value, 64, label)
        else:  # pragma: no cover - catalog and validator out of sync
            raise ValueError(f"{label} has an unsupported type")
    return clean


def _slot_color(value, what: str):
    if value is None:
        return None
    if isinstance(value, list):
        _check(len(value) == 2, f"{what} gradient must have two colors")
        return [_hex(item, what) for item in value]
    return _hex(value, what)


def validate_screen(screen, *, preview: bool = False) -> dict:
    """Validate a custom screen (Contract 2) and return a clean copy.

    With `preview=True` (unsaved working copies sent to /api/preview) the id may
    be missing, empty, a built-in id or any custom id, and the name is optional.
    """
    _object(screen, "Screen", ("layout", "slots") if preview else SCREEN_KEYS,
            SCREEN_KEYS if preview else ())
    screen_id = screen.get("id")
    if preview:
        _check(_blank_id(screen_id) or (isinstance(screen_id, str)
               and SCREEN_REF_RE.fullmatch(screen_id) is not None), "Invalid screen ID")
        screen_id = screen_id or None
        name = screen.get("name")
        name = name.strip()[:32] if isinstance(name, str) and name.strip() else "Preview"
    else:
        _check(isinstance(screen_id, str) and CUSTOM_ID_RE.fullmatch(screen_id) is not None,
               "Invalid custom screen ID")
        name = _name(screen["name"], "Screen name")
    layout = catalog.LAYOUTS.get(screen["layout"]) if isinstance(screen["layout"], str) else None
    _check(layout is not None, "Unknown layout")
    slots = screen["slots"]
    _check(isinstance(slots, list) and len(slots) == len(layout["slots"]),
           f"The {layout['name']} layout needs {len(layout['slots'])} slots")
    clean_slots = []
    for index, slot in enumerate(slots, 1):
        _object(slot, f"Slot {index}", ("block",), SLOT_KEYS)
        block = slot["block"]
        _check(isinstance(block, str) and block in catalog.BLOCKS, f"Slot {index} has an unknown block")
        clean_slots.append({"block": block,
                            "color": _slot_color(slot.get("color"), f"Slot {index} color"),
                            "options": validate_options(block, slot.get("options", {}))})
    style = screen.get("style", {"palette": None, "motion": "still"})
    _object(style, "Style", (), ("palette", "motion"))
    palette = style.get("palette")
    _check(palette is None or (isinstance(palette, str) and palette in catalog.PALETTES),
           "Unknown palette")
    motion = style.get("motion", "still")
    _check(isinstance(motion, str) and motion in catalog.MOTIONS, "Unknown motion")
    based_on = screen.get("based_on")
    _check(based_on is None or (isinstance(based_on, str)
           and SCREEN_REF_RE.fullmatch(based_on) is not None), "Invalid based_on screen ID")
    return {"id": screen_id, "name": name, "layout": screen["layout"], "slots": clean_slots,
            "style": {"palette": palette, "motion": motion}, "based_on": based_on}


# ---------------------------------------------------------------- art and feeds

def validate_art(art) -> dict:
    _object(art, "Art", ART_KEYS)
    _check(isinstance(art["id"], str) and ART_ID_RE.fullmatch(art["id"]) is not None,
           "Invalid art ID")
    name = _name(art["name"], "Art name")
    w, h = _int(art["w"], 1, 32, "Art width"), _int(art["h"], 1, 16, "Art height")
    _check((w, h) in ART_SIZES, "Art must be 7×7, 16×16 or 32×16")
    palette = art["palette"]
    _check(isinstance(palette, list) and 1 <= len(palette) <= MAX_ART_COLORS,
           f"Art needs 1–{MAX_ART_COLORS} palette colors")
    palette = [_hex(color, "Art color") for color in palette]
    frames = art["frames"]
    _check(isinstance(frames, list) and 1 <= len(frames) <= MAX_ART_FRAMES,
           f"Art needs 1–{MAX_ART_FRAMES} frames")
    for frame in frames:
        _check(isinstance(frame, str) and len(frame) == w * h,
               f"Each art frame must have exactly {w * h} pixels")
        _check(set(frame) <= ART_CHARS, "Art pixels must be '.' or 0–9, a–f")
        used = {int(char, 16) for char in set(frame) - {"."}}
        _check(not used or max(used) < len(palette), "Art uses a color that is not in its palette")
    fps = _int(art["fps"], 1, 12, "Art speed")
    return {"id": art["id"], "name": name, "w": w, "h": h, "palette": palette,
            "frames": list(frames), "fps": fps}


def validate_feed(feed) -> dict:
    _object(feed, "Feed", ("id", "name", "url"), FEED_KEYS)
    _check(isinstance(feed["id"], str) and FEED_ID_RE.fullmatch(feed["id"]) is not None,
           "Invalid feed ID")
    name = _name(feed["name"], "Feed name")
    url = feed["url"].strip() if isinstance(feed["url"], str) else feed["url"]
    _check(valid_http_url(url), "Feed URL must be an http(s) address of at most 512 characters")
    clean = {"id": feed["id"], "name": name, "url": url}
    for key, max_len in (("path", 128), ("series_path", 128)):
        value = _text(feed.get(key, ""), max_len, f"Feed {key.replace('_', ' ')}").strip()
        _check(not value or all(value.split(".")), f"Feed {key.replace('_', ' ')} must be dotted, "
               "like data.0.price")
        clean[key] = value
    for key in ("prefix", "suffix"):
        clean[key] = _text(feed.get(key, ""), 8, f"Feed {key}")
    clean["interval_s"] = _int(feed.get("interval_s", 300), 60, 86400, "Feed interval")
    return clean


# ---------------------------------------------------------------- habits and timers

def _validate_habits(habits) -> dict:
    _check(isinstance(habits, dict), "Habits must be an object")
    _check(len(habits) <= MAX_HABITS, f"Keep at most {MAX_HABITS} habits")
    clean = {}
    for habit_id, dates in habits.items():
        _text(habit_id, 64, "Habit ID", allow_empty=False)
        _check(isinstance(dates, list) and len(dates) <= MAX_HABIT_DATES, "Habit dates must be a list")
        clean[habit_id] = sorted({_date(value, "Habit date") for value in dates})
    return clean


def validate_timer(timer) -> dict:
    _object(timer, "Timer", TIMER_KEYS)
    state, phase = timer["state"], timer["phase"]
    _check(state in ("idle", "running", "paused"), "Timer state must be idle, running or paused")
    _check(phase in ("work", "break"), "Timer phase must be work or break")
    ends_at = timer["ends_at"]
    if state == "running":
        ends_at = _number(ends_at, 0, 1e11, "Timer end time")
    else:
        _check(ends_at is None, "Only a running timer has an end time")
    return {"state": state, "phase": phase,
            "work_min": _int(timer["work_min"], *WORK_MIN, "Work minutes"),
            "break_min": _int(timer["break_min"], *BREAK_MIN, "Break minutes"),
            "ends_at": ends_at,
            "remaining_s": _int(timer["remaining_s"], 0, WORK_MIN[1] * 60, "Timer remaining seconds"),
            "cycles": _int(timer["cycles"], 0, 10**6, "Timer cycles")}


def _validate_timers(timers) -> dict:
    _check(isinstance(timers, dict), "Timers must be an object")
    _check(len(timers) <= MAX_TIMERS, f"Keep at most {MAX_TIMERS} timers")
    clean = {}
    for timer_id, timer in timers.items():
        _check(isinstance(timer_id, str) and SCREEN_REF_RE.fullmatch(timer_id) is not None,
               "Invalid timer ID")
        clean[timer_id] = validate_timer(timer)
    return clean


# ---------------------------------------------------------------- lineup

def default_lineup() -> dict:
    return {"always": [{"screen_id": "time-classic", "seconds": DEFAULT_ITEM_SECONDS}],
            "moments": [], "transition": "cut", "interrupts": copy.deepcopy(INTERRUPT_DEFAULTS)}


def _items(items, known: set, what: str) -> list:
    _check(isinstance(items, list) and len(items) <= MAX_ITEMS, f"{what} can hold at most {MAX_ITEMS} screens")
    clean = []
    for item in items:
        _object(item, f"{what} item", ("screen_id",), ("screen_id", "seconds"))
        screen_id = item["screen_id"]
        _check(isinstance(screen_id, str) and screen_id in known, f"{what} uses a screen that does not exist")
        clean.append({"screen_id": screen_id,
                      "seconds": _int(item.get("seconds", DEFAULT_ITEM_SECONDS), 5, 300, "Screen time")})
    return clean


def validate_lineup(lineup, known: set) -> dict:
    """Validate a lineup; `known` is every screen id it may reference."""
    _object(lineup, "Lineup", (), ("always", "moments", "transition", "interrupts"))
    always = _items(lineup.get("always", []), known, "Always on")
    moments = lineup.get("moments", [])
    _check(isinstance(moments, list) and len(moments) <= MAX_MOMENTS, f"Keep at most {MAX_MOMENTS} moments")
    clean_moments = []
    for moment in moments:
        _object(moment, "Moment", ("id", "name", "start", "end", "screens"), MOMENT_KEYS)
        _check(isinstance(moment["id"], str) and MOMENT_ID_RE.fullmatch(moment["id"]) is not None,
               "Invalid moment ID")
        name = _name(moment["name"], "Moment name")
        for key in ("start", "end"):
            _check(isinstance(moment[key], str) and TIME_RE.fullmatch(moment[key]) is not None,
                   f"Moment {key} must be HH:MM")
        _check(moment["start"] != moment["end"], "A moment's start and end must differ")
        days = moment.get("days", list(range(7)))
        _check(isinstance(days, list) and 1 <= len(days) <= 7, "Pick at least one day")
        days = [_int(day, 0, 6, "Day") for day in days]
        _check(len(days) == len(set(days)), "Days must not repeat")
        brightness = moment.get("brightness")
        if brightness is not None:
            brightness = _int(brightness, 1, 100, "Moment brightness")
        clean_moments.append({"id": moment["id"], "name": name, "start": moment["start"],
                              "end": moment["end"], "days": sorted(days), "brightness": brightness,
                              "screens": _items(moment["screens"], known, name)})
    _unique([moment["id"] for moment in clean_moments], "Moment")
    transition = lineup.get("transition", "cut")
    _check(isinstance(transition, str) and transition in catalog.TRANSITIONS, "Unknown transition")
    interrupts = lineup.get("interrupts", {})
    _object(interrupts, "Interruptions", (), INTERRUPT_DEFAULTS)
    clean_interrupts = {}
    for kind, defaults in INTERRUPT_DEFAULTS.items():
        value = {**defaults, **_object(interrupts.get(kind, {}), f"Interruption {kind}", (), defaults)}
        clean = {"enabled": _bool(value["enabled"], f"Interruption {kind} enabled")}
        for key in defaults:
            if key != "enabled":
                clean[key] = _int(value[key], *INTERRUPT_BOUNDS[key], f"Interruption {key.replace('_', ' ')}")
        clean_interrupts[kind] = clean
    return {"always": always, "moments": clean_moments, "transition": transition,
            "interrupts": clean_interrupts}


# ---------------------------------------------------------------- library

def default_library() -> dict:
    return {"version": VERSION, "screens": [], "art": [], "feeds": [], "habits": {},
            "timers": {}, "lineup": default_lineup(), "pinned": None}


def all_screen_ids(lib: dict) -> list[str]:
    """Custom screen ids, then built-in ids (legacy aliases are not included)."""
    return [screen["id"] for screen in lib.get("screens", ())] + list(catalog.BUILTINS)


def _known_ids(custom_ids) -> set:
    return set(custom_ids) | set(catalog.BUILTINS) | set(catalog.LEGACY_IDS)


def validate_library(data) -> dict:
    """Validate a whole library and return a clean copy (missing sections get defaults)."""
    _object(data, "Library", ("version",), LIBRARY_KEYS)
    _check(data["version"] == VERSION and not isinstance(data["version"], bool),
           f"Unsupported library version (expected {VERSION})")
    base = default_library()
    screens = data.get("screens", base["screens"])
    _check(isinstance(screens, list) and len(screens) <= MAX_SCREENS, f"Save at most {MAX_SCREENS} screens")
    screens = [validate_screen(screen) for screen in screens]
    _unique([screen["id"] for screen in screens], "Screen")
    art = data.get("art", base["art"])
    _check(isinstance(art, list) and len(art) <= MAX_ART, f"Save at most {MAX_ART} pieces of art")
    art = [validate_art(item) for item in art]
    _unique([item["id"] for item in art], "Art")
    feeds = data.get("feeds", base["feeds"])
    _check(isinstance(feeds, list) and len(feeds) <= MAX_FEEDS, f"Save at most {MAX_FEEDS} feeds")
    feeds = [validate_feed(feed) for feed in feeds]
    _unique([feed["id"] for feed in feeds], "Feed")
    known = _known_ids(screen["id"] for screen in screens)
    lineup = validate_lineup(data.get("lineup", base["lineup"]), known)
    pinned = data.get("pinned")
    if pinned is not None:
        _object(pinned, "Pinned screen", ("screen_id",), ("screen_id", "until"))
        _check(isinstance(pinned["screen_id"], str) and pinned["screen_id"] in known,
               "Pinned screen does not exist")
        until = pinned.get("until")
        if until is not None:
            until = _number(until, 0, 1e11, "Pinned until")
        pinned = {"screen_id": pinned["screen_id"], "until": until}
    return {"version": VERSION, "screens": screens, "art": art, "feeds": feeds,
            "habits": _validate_habits(data.get("habits", base["habits"])),
            "timers": _validate_timers(data.get("timers", base["timers"])),
            "lineup": lineup, "pinned": pinned}


def resolve_screen(lib: dict, screen_id) -> dict | None:
    """A copy of the screen with this id: custom, then built-in, then legacy alias."""
    if not isinstance(screen_id, str):
        return None
    for screen in lib.get("screens", ()) if isinstance(lib, dict) else ():
        if screen.get("id") == screen_id:
            return copy.deepcopy(screen)
    builtin = catalog.BUILTINS.get(screen_id) or catalog.BUILTINS.get(catalog.LEGACY_IDS.get(screen_id))
    return copy.deepcopy(builtin) if builtin else None


# ---------------------------------------------------------------- migration

def _stable_custom_id(seed: str) -> str:
    # Deterministic so the display and web services migrate to the same ids.
    return "custom-" + hashlib.sha256(seed.encode()).hexdigest()[:32]


def _legacy_row(row: dict, full: bool) -> dict:
    content, color = row.get("content"), row.get("color")
    color = color.upper() if isinstance(color, str) and HEX_RE.fullmatch(color) else None
    if content == "time":
        return {"block": "time", "color": color, "options": {"font": "5x7"} if full else {}}
    if content == "date":
        return {"block": "date", "color": color, "options": {"style": "long"}}
    return {"block": "weekday", "color": color, "options": {}}


def _legacy_screen(old: dict) -> dict | None:
    rows = old.get("rows") if isinstance(old, dict) else None
    if not isinstance(rows, (list, tuple)) or len(rows) not in (1, 2):
        return None
    full = len(rows) == 1
    try:
        return validate_screen({
            "id": old.get("id"), "name": old.get("name"), "layout": "full" if full else "two",
            "slots": [_legacy_row(row, full) for row in rows],
            "style": {"palette": None, "motion": "still"}, "based_on": None})
    except ValueError:
        return None


def migrate_from_settings(settings: Settings) -> dict:
    """Build the first library.json from pre-lineup settings (Contract 4, Migration)."""
    lib = default_library()
    for old in settings.custom_screens or ():
        screen = _legacy_screen(old)
        if screen and len(lib["screens"]) < MAX_SCREENS:
            lib["screens"].append(screen)
    seconds = max(5, min(300, int(settings.rotate or DEFAULT_ITEM_SECONDS)))
    mode = settings.mode
    selected = "time-classic"
    if mode == "clock":
        legacy_id = settings.clock_screen_id
        custom_ids = {screen["id"] for screen in lib["screens"]}
        if legacy_id == "clock-classic" and (settings.top_color.upper(), settings.bottom_color.upper()) \
                != ("#FFFFFF", "#FFFF00"):
            # Keep the clock colors an older install chose for the built-in clock.
            screen = _legacy_screen({"id": _stable_custom_id("clock-classic:" + settings.top_color
                                                             + settings.bottom_color),
                                     "name": "Clock & date", "rows": [
                                         {"content": "time", "color": settings.top_color},
                                         {"content": "date", "color": settings.bottom_color}]})
            lib["screens"].append(screen)
            selected = screen["id"]
        elif legacy_id in custom_ids:
            selected = legacy_id
        else:
            selected = catalog.LEGACY_IDS.get(legacy_id, "time-classic")
    elif mode == "flight" and settings.flight and len(settings.flight) <= 8:
        follow = copy.deepcopy(catalog.BUILTINS["sky-follow"])
        for slot in follow["slots"]:
            if slot["block"] == "flight":
                slot["options"] = {**slot["options"], "callsign": settings.flight.upper()}
        selected = _stable_custom_id("sky-follow:" + settings.flight.upper())
        lib["screens"].append(validate_screen({
            "id": selected, "name": f"Follow {settings.flight.upper()}", "layout": follow["layout"],
            "slots": follow["slots"], "style": follow["style"], "based_on": "sky-follow"}))
    elif mode in ("nearby", "flight"):
        selected = "sky-nearby"
    lib["screens"] = lib["screens"][:MAX_SCREENS]
    lib["lineup"]["always"] = [{"screen_id": selected, "seconds": seconds}]
    return validate_library(lib)


# ---------------------------------------------------------------- persistence

def load_library(path: Path = LIBRARY_PATH, settings: Settings | None = None) -> dict:
    """Read library.json, creating it from the legacy settings on first run.

    Raises ValueError (with the reason) when the file exists but is invalid.
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        if settings is None:
            try:
                settings = load_settings()
            except (OSError, ValueError):
                settings = Settings()
        lib = migrate_from_settings(settings)
        try:
            save_library(lib, path)
        except OSError:
            pass  # Still usable; the next writer will create the file.
        return lib
    try:
        return validate_library(json.loads(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON: {exc}") from None
    except ValueError as exc:
        raise ValueError(f"{path.name} is invalid: {exc}") from None


def save_library(lib: dict, path: Path = LIBRARY_PATH) -> None:
    lib = validate_library(lib)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".library-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(lib, handle, indent=1)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# ---------------------------------------------------------------- timers

def _phase_seconds(timer: dict, phase: str) -> int:
    return (timer["work_min"] if phase == "work" else timer["break_min"]) * 60


def advance_timer(timer: dict, now: float) -> dict:
    """Roll a running timer through every phase that ended before `now`.

    A work phase ending counts one cycle. Paused and idle timers are unchanged.
    """
    timer = dict(timer)
    if timer.get("state") != "running" or not isinstance(timer.get("ends_at"), (int, float)):
        return timer
    if timer["ends_at"] <= now:
        cycle = _phase_seconds(timer, "work") + _phase_seconds(timer, "break")
        # Skip whole work+break cycles at once so a long-forgotten timer is cheap.
        whole = int((now - timer["ends_at"]) // cycle)
        timer["ends_at"] += whole * cycle
        timer["cycles"] += whole
        while timer["ends_at"] <= now:
            if timer["phase"] == "work":
                timer["cycles"] += 1
                timer["phase"] = "break"
            else:
                timer["phase"] = "work"
            timer["ends_at"] += _phase_seconds(timer, timer["phase"])
    timer["remaining_s"] = max(0, min(int(math.ceil(timer["ends_at"] - now)), WORK_MIN[1] * 60))
    return timer


def _timer_defaults(lib: dict, timer_id: str) -> tuple[int, int]:
    screen = resolve_screen(lib, timer_id) or {}
    for slot in screen.get("slots") or ():
        if slot.get("block") == "timer":
            options = slot.get("options") or {}
            return int(options.get("work_min") or 25), int(options.get("break_min") or 5)
    return 25, 5


def _timer_action(lib: dict, data: dict, now: float) -> None:
    _object(data, "Timer request", ("action", "timer_id", "op"), ("action", "timer_id", "op",
                                                                    "work_min", "break_min"))
    timer_id = data["timer_id"]
    _check(isinstance(timer_id, str) and SCREEN_REF_RE.fullmatch(timer_id) is not None,
           "Invalid timer ID")
    op = data["op"]
    _check(op in ("start", "pause", "resume", "reset", "skip"),
           "Timer op must be start, pause, resume, reset or skip")
    existing = lib["timers"].get(timer_id)
    if existing is None:
        _check(len(lib["timers"]) < MAX_TIMERS, f"Keep at most {MAX_TIMERS} timers")
        work, rest = _timer_defaults(lib, timer_id)
        existing = {"state": "idle", "phase": "work", "work_min": work, "break_min": rest,
                    "ends_at": None, "remaining_s": work * 60, "cycles": 0}
    timer = advance_timer(existing, now)
    if "work_min" in data:
        timer["work_min"] = _int(data["work_min"], *WORK_MIN, "Work minutes")
    if "break_min" in data:
        timer["break_min"] = _int(data["break_min"], *BREAK_MIN, "Break minutes")
    if op == "start":
        total = _phase_seconds(timer, "work")
        timer.update(state="running", phase="work", ends_at=now + total, remaining_s=total, cycles=0)
    elif op == "pause":
        _check(timer["state"] == "running", "The timer is not running")
        timer.update(state="paused", ends_at=None)
    elif op == "resume":
        _check(timer["state"] == "paused", "The timer is not paused")
        timer.update(state="running", ends_at=now + timer["remaining_s"])
    elif op == "reset":
        timer.update(state="idle", phase="work", ends_at=None,
                     remaining_s=_phase_seconds(timer, "work"), cycles=0)
    else:  # skip
        _check(timer["state"] != "idle", "Start the timer first")
        if timer["phase"] == "work":
            timer.update(phase="break", cycles=timer["cycles"] + 1)
        else:
            timer["phase"] = "work"
        total = _phase_seconds(timer, timer["phase"])
        timer["remaining_s"] = total
        if timer["state"] == "running":
            timer["ends_at"] = now + total
    if timer["ends_at"] is not None:
        timer["ends_at"] = round(timer["ends_at"], 3)
    lib["timers"][timer_id] = timer


# ---------------------------------------------------------------- actions

def _fields(data: dict, action: str, *names: str, optional=()) -> dict:
    return _object(data, f"The {action} request", ("action", *names), ("action", *names, *optional))


def _upsert(items: list, item: dict, what: str, limit: int, is_new: bool) -> None:
    if is_new:
        _check(len(items) < limit, f"Save at most {limit} {what}")
        items.append(item)
        return
    index = next((i for i, old in enumerate(items) if old["id"] == item["id"]), None)
    _check(index is not None, f"That {what[:-1] if what.endswith('s') else what} no longer exists")
    items[index] = item


def _habit_window(now: float) -> tuple[date, date]:
    # Local dates are within a day of the UTC date in every time zone.
    today = datetime.fromtimestamp(now, timezone.utc).date()
    return today - timedelta(days=HABIT_DAYS), today + timedelta(days=1)


def apply_action(lib: dict, action: dict, now=time.time) -> dict:
    """Apply one Contract 6 library action and return the new, validated library."""
    _check(isinstance(action, dict), "Library request must be an object")
    name = action.get("action")
    _check(isinstance(name, str), "Library request needs an action")
    lib = validate_library(copy.deepcopy(lib))
    current = now() if callable(now) else float(now)

    if name == "save_screen":
        data = _fields(action, name, "screen")
        screen = data["screen"]
        _check(isinstance(screen, dict), "Screen must be an object")
        screen = dict(screen)
        is_new = _blank_id(screen.get("id"))
        if is_new:
            screen["id"] = _new_id("custom-", 32, set(all_screen_ids(lib)))
        elif screen["id"] in catalog.BUILTINS or screen["id"] in catalog.LEGACY_IDS:
            raise ValueError("Built-in screens can't be changed; save a copy instead")
        _upsert(lib["screens"], validate_screen(screen), "screens", MAX_SCREENS, is_new)
    elif name == "delete_screen":
        screen_id = _fields(action, name, "screen_id")["screen_id"]
        _check(any(screen["id"] == screen_id for screen in lib["screens"]),
               "Only your own screens can be deleted")
        lib["screens"] = [screen for screen in lib["screens"] if screen["id"] != screen_id]
        lineup = lib["lineup"]
        lineup["always"] = [item for item in lineup["always"] if item["screen_id"] != screen_id]
        for moment in lineup["moments"]:
            moment["screens"] = [item for item in moment["screens"] if item["screen_id"] != screen_id]
        if lib["pinned"] and lib["pinned"]["screen_id"] == screen_id:
            lib["pinned"] = None
        lib["timers"].pop(screen_id, None)
        lib["habits"].pop(screen_id, None)
    elif name == "save_art":
        art = _fields(action, name, "art")["art"]
        _check(isinstance(art, dict), "Art must be an object")
        art = dict(art)
        is_new = _blank_id(art.get("id"))
        if is_new:
            art["id"] = _new_id("art-", 16, {item["id"] for item in lib["art"]})
        _upsert(lib["art"], validate_art(art), "art", MAX_ART, is_new)
    elif name == "delete_art":
        art_id = _fields(action, name, "art_id")["art_id"]
        _check(any(item["id"] == art_id for item in lib["art"]), "That art no longer exists")
        lib["art"] = [item for item in lib["art"] if item["id"] != art_id]
    elif name == "save_feed":
        feed = _fields(action, name, "feed")["feed"]
        _check(isinstance(feed, dict), "Feed must be an object")
        feed = dict(feed)
        is_new = _blank_id(feed.get("id"))
        if is_new:
            feed["id"] = _new_id("feed-", 8, {item["id"] for item in lib["feeds"]})
        _upsert(lib["feeds"], validate_feed(feed), "feeds", MAX_FEEDS, is_new)
    elif name == "delete_feed":
        feed_id = _fields(action, name, "feed_id")["feed_id"]
        _check(any(item["id"] == feed_id for item in lib["feeds"]), "That feed no longer exists")
        lib["feeds"] = [item for item in lib["feeds"] if item["id"] != feed_id]
    elif name == "save_lineup":
        lineup = _fields(action, name, "lineup")["lineup"]
        lib["lineup"] = validate_lineup(lineup, _known_ids(s["id"] for s in lib["screens"]))
    elif name == "show_now":
        data = _fields(action, name, "screen_id", optional=("seconds",))
        screen_id = data["screen_id"]
        _check(isinstance(screen_id, str) and resolve_screen(lib, screen_id) is not None,
               "That screen does not exist")
        seconds = data.get("seconds")
        until = None
        if seconds is not None:
            until = round(current + _int(seconds, 5, SHOW_NOW_MAX_S, "Show-now seconds"), 3)
        lib["pinned"] = {"screen_id": screen_id, "until": until}
    elif name == "unpin":
        _fields(action, name)
        lib["pinned"] = None
    elif name == "timer":
        _timer_action(lib, action, current)
    elif name == "habit":
        data = _fields(action, name, "habit_id", "date", "done")
        habit_id = _text(data["habit_id"], 64, "Habit ID", allow_empty=False)
        day = date.fromisoformat(_date(data["date"], "Habit date"))
        done = _bool(data["done"], "done")
        oldest, newest = _habit_window(current)
        _check(oldest <= day <= newest, f"Habits keep the last {HABIT_DAYS} days only")
        dates = set(lib["habits"].get(habit_id, ()))
        if done:
            dates.add(day.isoformat())
        else:
            dates.discard(day.isoformat())
        dates = {value for value in dates if date.fromisoformat(value) >= oldest}
        if dates:
            _check(habit_id in lib["habits"] or len(lib["habits"]) < MAX_HABITS,
                   f"Keep at most {MAX_HABITS} habits")
            lib["habits"][habit_id] = sorted(dates)
        else:
            lib["habits"].pop(habit_id, None)
    else:
        raise ValueError("Unknown library action")
    return validate_library(lib)
