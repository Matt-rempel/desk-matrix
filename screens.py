"""Clock screen presets and validation for saved screen layouts."""

from __future__ import annotations

import re

BUILTIN_SCREENS = (
    {"id": "clock-classic", "name": "Clock & date", "rows": [
        {"content": "time", "color": "#FFFFFF"},
        {"content": "date", "color": "#FFFF00"},
    ]},
    {"id": "clock-simple", "name": "Time only", "rows": [
        {"content": "time", "color": "#FFFFFF"},
    ]},
    {"id": "clock-weekday", "name": "Time & weekday", "rows": [
        {"content": "time", "color": "#FFFFFF"},
        {"content": "weekday", "color": "#FFB86C"},
    ]},
)
BUILTIN_IDS = frozenset(screen["id"] for screen in BUILTIN_SCREENS)
ROW_CONTENT = frozenset(("time", "date", "weekday"))
MAX_CUSTOM_SCREENS = 20


def validate_screen(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"id", "name", "rows"}:
        raise ValueError("Screen must have an ID, name, and rows")
    screen_id = value["id"]
    if (not isinstance(screen_id, str)
            or not re.fullmatch(r"custom-[0-9a-f]{32}", screen_id)):
        raise ValueError("Invalid custom screen ID")
    name = value["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32:
        raise ValueError("Screen name must be 1–32 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("Screen name contains invalid characters")
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) not in (1, 2):
        raise ValueError("Choose one or two rows")
    clean_rows = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"content", "color"}:
            raise ValueError("Each row needs content and a color")
        if row["content"] not in ROW_CONTENT:
            raise ValueError("Rows can show time, date, or weekday")
        color = row["color"]
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Row color must be a six-digit hex color")
        clean_rows.append({"content": row["content"], "color": color.upper()})
    return {"id": screen_id, "name": name.strip(), "rows": clean_rows}


def validate_library(custom_screens, selected_id) -> tuple[tuple[dict, ...], str]:
    if not isinstance(custom_screens, (list, tuple)) or len(custom_screens) > MAX_CUSTOM_SCREENS:
        raise ValueError("Save at most 20 custom screens")
    screens = tuple(validate_screen(screen) for screen in custom_screens)
    ids = [screen["id"] for screen in screens]
    if len(ids) != len(set(ids)):
        raise ValueError("Custom screen IDs must be unique")
    if not isinstance(selected_id, str) or selected_id not in BUILTIN_IDS.union(ids):
        raise ValueError("Selected clock screen does not exist")
    return screens, selected_id


def builtins_with_legacy_colors(top_color: str, bottom_color: str) -> tuple[dict, ...]:
    """Keep the original clock colors for installations upgraded from older settings."""
    classic = {**BUILTIN_SCREENS[0], "rows": [
        {"content": "time", "color": top_color},
        {"content": "date", "color": bottom_color},
    ]}
    return (classic, *BUILTIN_SCREENS[1:])


def resolve_screen(selected_id: str, custom_screens: tuple[dict, ...],
                   top_color: str = "#FFFFFF", bottom_color: str = "#FFFF00") -> dict:
    for screen in (*builtins_with_legacy_colors(top_color, bottom_color), *custom_screens):
        if screen["id"] == selected_id:
            return screen
    return BUILTIN_SCREENS[0]
