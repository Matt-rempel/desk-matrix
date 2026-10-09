"""Layouts, palettes, block metadata, built-in screens and sample data."""

from __future__ import annotations

import copy

from render import ICONS

INK, MUTED, FAINT, AMBER = "#F4F2EE", "#8C8A84", "#5E5C58", "#FFB23F"

LAYOUTS = {
    "icon2": {"name": "Icon + 2 rows", "slots": [
        {"x": 0, "y": 0, "w": 7, "h": 16, "where": "Left column"},
        {"x": 8, "y": 0, "w": 24, "h": 7, "where": "Top right"},
        {"x": 8, "y": 9, "w": 24, "h": 7, "where": "Bottom right"}]},
    "two": {"name": "Two rows", "slots": [
        {"x": 0, "y": 0, "w": 32, "h": 7, "where": "Top row"},
        {"x": 0, "y": 9, "w": 32, "h": 7, "where": "Bottom row"}]},
    "bigsmall": {"name": "Big + small", "slots": [
        {"x": 0, "y": 0, "w": 32, "h": 10, "where": "Large top"},
        {"x": 0, "y": 11, "w": 32, "h": 5, "where": "Thin bottom"}]},
    "three": {"name": "Three rows", "slots": [
        {"x": 0, "y": 0, "w": 32, "h": 5, "where": "Row 1"},
        {"x": 0, "y": 6, "w": 32, "h": 5, "where": "Row 2"},
        {"x": 0, "y": 11, "w": 32, "h": 5, "where": "Row 3"}]},
    "split": {"name": "Side by side", "slots": [
        {"x": 0, "y": 0, "w": 15, "h": 16, "where": "Left half"},
        {"x": 17, "y": 0, "w": 15, "h": 16, "where": "Right half"}]},
    "full": {"name": "Full panel", "slots": [
        {"x": 0, "y": 0, "w": 32, "h": 16, "where": "Whole panel"}]},
}
for _id, _layout in LAYOUTS.items():
    _layout["id"] = _id

PALETTES = {
    "ember": {"name": "Ember", "primary": ["#FFD23F", "#FF5A36"], "secondary": "#8C8A84",
              "glow": "rgba(255,120,54,0.30)"},
    "phosphor": {"name": "Phosphor", "primary": "#7CFF8A", "secondary": "#2F8A48",
                 "glow": "rgba(124,255,138,0.22)"},
    "ice": {"name": "Ice", "primary": ["#E8F6FF", "#5AB8FF"], "secondary": "#5A7A99",
            "glow": "rgba(90,184,255,0.25)"},
    "paper": {"name": "Paper", "primary": "#F4F2EE", "secondary": "#8C8A84",
              "glow": "rgba(244,242,238,0.14)"},
    "neon": {"name": "Neon", "primary": ["#FF4DD8", "#6B7CFF"], "secondary": "#B98CFF",
             "glow": "rgba(200,90,255,0.28)"},
    "night": {"name": "Night red", "primary": "#FF3B2F", "secondary": "#7A1E18",
              "glow": "rgba(255,59,47,0.22)"},
}
for _id, _palette in PALETTES.items():
    _palette["id"] = _id

MOTIONS = {
    "still": {"name": "Still", "glyph": "■"},
    "breathe": {"name": "Breathe", "glyph": "◐"},
    "slide": {"name": "Slide in", "glyph": "→"},
    "sparkle": {"name": "Sparkle", "glyph": "✦"},
}
TRANSITIONS = {
    "cut": {"name": "Cut"},
    "slide": {"name": "Slide"},
    "dissolve": {"name": "Dissolve"},
    "wipe": {"name": "Pixel wipe"},
}
COLORS = [
    {"c": "#F4F2EE", "name": "White"}, {"c": "#FFB23F", "name": "Amber"},
    {"c": "#FF5A36", "name": "Tomato"}, {"c": "#FF7AB6", "name": "Pink"},
    {"c": "#B98CFF", "name": "Violet"}, {"c": "#7CB8FF", "name": "Sky"},
    {"c": "#5AD1A0", "name": "Mint"}, {"c": "#8C8A84", "name": "Grey"},
]


def _bool(default: bool) -> dict:
    return {"type": "bool", "default": default}


def _enum(default: str, *choices: str) -> dict:
    return {"type": "enum", "default": default, "choices": list(choices)}


def _str(default: str, max_len: int) -> dict:
    return {"type": "str", "default": default, "max_len": max_len}


def _int(default: int, low: int, high: int) -> dict:
    return {"type": "int", "default": default, "min": low, "max": high}


def _color() -> dict:
    return {"type": "color", "default": None}


def _block(name, glyph, category, options=None, min_w=8, min_h=5, needs=()):
    return {"name": name, "glyph": glyph, "category": category, "options": options or {},
            "min_w": min_w, "min_h": min_h, "needs": list(needs)}


ICON_NAMES = list(ICONS)

# World clock cities: short code shown on the panel, name for the settings page.
CITIES = {
    "HNL": ("Honolulu", "Pacific/Honolulu"), "ANC": ("Anchorage", "America/Anchorage"),
    "VAN": ("Vancouver", "America/Vancouver"), "LAX": ("Los Angeles", "America/Los_Angeles"),
    "CGY": ("Calgary", "America/Edmonton"), "DEN": ("Denver", "America/Denver"),
    "MEX": ("Mexico City", "America/Mexico_City"), "CHI": ("Chicago", "America/Chicago"),
    "TOR": ("Toronto", "America/Toronto"), "NYC": ("New York", "America/New_York"),
    "HFX": ("Halifax", "America/Halifax"), "SAO": ("São Paulo", "America/Sao_Paulo"),
    "UTC": ("UTC", "UTC"), "LDN": ("London", "Europe/London"), "LIS": ("Lisbon", "Europe/Lisbon"),
    "PAR": ("Paris", "Europe/Paris"), "BER": ("Berlin", "Europe/Berlin"), "ROM": ("Rome", "Europe/Rome"),
    "ATH": ("Athens", "Europe/Athens"), "IST": ("Istanbul", "Europe/Istanbul"),
    "CAI": ("Cairo", "Africa/Cairo"), "NBO": ("Nairobi", "Africa/Nairobi"),
    "JNB": ("Johannesburg", "Africa/Johannesburg"), "DXB": ("Dubai", "Asia/Dubai"),
    "DEL": ("Delhi", "Asia/Kolkata"), "BKK": ("Bangkok", "Asia/Bangkok"),
    "SIN": ("Singapore", "Asia/Singapore"), "HKG": ("Hong Kong", "Asia/Hong_Kong"),
    "SHA": ("Shanghai", "Asia/Shanghai"), "SEL": ("Seoul", "Asia/Seoul"),
    "TYO": ("Tokyo", "Asia/Tokyo"), "SYD": ("Sydney", "Australia/Sydney"),
    "AKL": ("Auckland", "Pacific/Auckland"),
}

BLOCKS = {
    "time": _block("Time", "10:24", "time", {
        "h24": _bool(True), "colon_blink": _bool(False),
        "font": _enum("auto", "auto", "big", "5x7", "3x5")}, 17, 5),
    "date": _block("Date", "OCT 9", "time", {
        "style": _enum("long", "short", "long", "stack"), "accent": _color()}, 7, 5),
    "weekday": _block("Weekday", "FRI", "time", {}, 7, 5),
    "temp": _block("Temperature", "14°", "weather", {
        "which": _enum("now", "now", "high", "low", "hilo", "sky"),
        "accent": _color(), "icon_color": _color()}, 11, 5, ["weather"]),
    "weather_icon": _block("Sky icon", "SUN", "weather", {}, 7, 5, ["weather"]),
    "rain": _block("Rain soon", "20M", "weather", {
        "accent": _color(), "icon_color": _color()}, 11, 5, ["weather"]),
    "sun_time": _block("Sunrise / sunset", "6:51", "sky", {
        "event": _enum("next", "next", "sunrise", "sunset"), "h24": _bool(False)}, 17, 5, ["sun"]),
    "flight": _block("Flight", "WJA", "sky", {
        "source": _enum("nearby", "nearby", "follow"), "callsign": _str("", 8),
        "field": _enum("callsign", "callsign", "route", "detail"),
        "accent": _color(), "icon_color": _color()}, 11, 5, ["aircraft"]),
    "plane_count": _block("Plane count", "×7", "sky", {}, 7, 5, ["aircraft:nearby"]),
    "countdown": _block("Countdown", "12D", "focus", {
        "label": _str("", 12), "date": {"type": "date", "default": ""},
        "accent": _color()}, 11, 5),
    "timer": _block("Timer", "18:42", "focus", {
        "work_min": _int(25, 1, 120), "break_min": _int(5, 1, 60),
        "accent": _color()}, 17, 5, ["timers"]),
    "text": _block("Your text", "ABC", "play", {"text": _str("HELLO", 64)}, 7, 5),
    "progress": _block("Progress bar", "▰▰▱", "focus", {
        "source": _enum("day", "day", "year", "timer", "flight"), "callsign": _str("", 8)}, 8, 1),
    "spark": _block("Sparkline", "▁▃▅▇", "data", {
        "source": _enum("temp_hourly", "temp_hourly", "feed"),
        "feed_id": {"type": "feed", "default": ""}, "accent": _color()}, 8, 3),
    "icon": _block("Icon", "♥", "play", {
        "name": {"type": "enum", "default": "heart", "choices": ICON_NAMES}}, 7, 5),
    "art": _block("Pixel art", "▦", "play", {
        "art_id": {"type": "art", "default": "builtin-heart"}}, 7, 7),
    "feed": _block("Feed value", "42", "data", {
        "feed_id": {"type": "feed", "default": ""},
        "field": _enum("value", "value", "label"), "label": _str("", 16),
        "icon": {"type": "enum", "default": "", "choices": [""] + ICON_NAMES},
        "accent": _color(), "icon_color": _color()}, 8, 5, ["feed"]),
    "calendar_next": _block("Next event", "9:30", "focus", {
        "field": _enum("title", "time", "title"), "h24": _bool(False),
        "accent": _color()}, 11, 5, ["calendar"]),
    "metar": _block("METAR", "VFR", "weather", {
        "station": _str("", 4), "field": _enum("category", "station", "category", "wind"),
        "icon_color": _color()}, 11, 5, ["metar"]),
    "iss": _block("ISS", "ISS", "sky", {
        "field": _enum("distance", "distance", "direction", "label"),
        "accent": _color(), "icon_color": _color()}, 11, 5, ["iss"]),
    "health": _block("Pi health", "48°", "data", {
        "field": _enum("cpu", "cpu", "net", "feed"), "accent": _color()}, 11, 5, ["health"]),
    "world_clock": _block("World clock", "LDN", "time", {
        "city": {"type": "enum", "default": "LDN", "choices": list(CITIES),
                 "labels": {code: name for code, (name, _) in CITIES.items()}},
        "label": _str("", 4), "h24": _bool(True), "accent": _color()}, 17, 5),
    "analog_clock": _block("Analog clock", "◷", "time", {
        "accent": _color(), "face": _color()}, 15, 15),
    "fuzzy_time": _block("Time in words", "HALF", "time", {"accent": _color()}, 32, 16),
    "radar": _block("Radar", "◎", "sky", {"accent": _color()}, 15, 15, ["aircraft:nearby"]),
    "sun_arc": _block("Sun arc", "◠", "sky", {"h24": _bool(False)}, 32, 16, ["sun"]),
    "hourly_graph": _block("Next 12 hours", "▁▃▅", "weather", {"accent": _color()}, 16, 6, ["weather"]),
    "habit_week": _block("Habit week", "●●○", "focus", {
        "habit_id": _str("", 40), "label": _str("STREAK", 8), "accent": _color()}, 28, 10),
    "life": _block("Life", "⁘", "play", {}, 1, 1),
    "fire": _block("Ember", "▲", "play", {}, 1, 1),
    "none": _block("Empty", "—", "basic", {}, 1, 1),
}
for _id, _meta in BLOCKS.items():
    _meta["id"] = _id


def _slot(block: str, color, **options) -> dict:
    return {"block": block, "color": color, "options": options}


def _screen(sid, name, layout, slots, family, tag, source, palette=None, motion="still"):
    return {"id": sid, "name": name, "layout": layout, "slots": slots,
            "style": {"palette": palette, "motion": motion}, "based_on": None,
            "family": family, "tag": tag, "source": source}


SAMPLE_FEEDS = {"market": "feed-market", "score": "feed-score",
                "transit": "feed-transit", "music": "feed-music"}

BUILTIN_SCREENS = [
    _screen("time-big", "Big digits", "bigsmall", [
        _slot("time", None), _slot("date", None, style="long")],
        "clock", "Time · date", "Offline", palette="ember"),
    _screen("time-classic", "Classic", "two", [
        _slot("time", INK), _slot("date", AMBER, style="short")],
        "clock", "Time · date", "Offline"),
    _screen("time-analog", "Analog", "split", [
        _slot("analog_clock", INK, accent=AMBER, face="#3A3A40"),
        _slot("date", INK, style="stack", accent=AMBER)],
        "dial", "Dial · weekday", "Offline"),
    _screen("time-words", "In words", "full", [
        _slot("fuzzy_time", INK, accent=AMBER)], "words", "Fuzzy time", "Offline"),
    _screen("time-world", "World clocks", "three", [
        _slot("world_clock", INK, city="LDN"), _slot("world_clock", INK, city="NYC"),
        _slot("world_clock", INK, city="TYO")],
        "world", "Three cities", "Offline"),
    _screen("time-world-one", "World clock", "full", [
        _slot("world_clock", INK, city="TYO", accent="#7CB8FF")],
        "world", "One city, big", "Offline"),
    _screen("time-daybar", "Day progress", "two", [
        _slot("time", INK), _slot("progress", "#7CD8FF", source="day")],
        "clock", "How much day is left", "Offline"),
    _screen("sky-nearby", "Nearby flight", "full", [
        _slot("flight", INK, source="nearby", accent="#8FD3FF", icon_color=AMBER)],
        "sky", "Cycles planes", "adsb.fi · ADSBdb"),
    _screen("sky-follow", "Follow a flight", "full", [
        _slot("flight", INK, source="follow", accent=MUTED, icon_color=AMBER)],
        "sky", "Route progress", "adsb.fi · ADSBdb"),
    _screen("sky-radar", "Radar", "full", [_slot("radar", "#7CFF8A")],
            "sky", "Planes in range", "adsb.fi"),
    _screen("sky-iss", "ISS now", "full", [
        _slot("iss", INK, accent=MUTED, icon_color="#C9D2FF")],
        "sky", "Where the station is", "wheretheiss.at"),
    _screen("sky-sun", "Sun arc", "full", [_slot("sun_arc", AMBER)],
            "sky", "Sunrise · sunset", "Offline"),
    _screen("weather-now", "Right now", "full", [
        _slot("temp", INK, which="now", accent=MUTED)],
        "weather", "Temp · high · low", "Open-Meteo"),
    _screen("weather-hourly", "Next 12 hours", "full", [
        _slot("hourly_graph", AMBER, accent="#FF5A36")],
        "weather", "Temperature curve", "Open-Meteo"),
    _screen("weather-rain", "Rain soon", "full", [
        _slot("rain", INK, accent=MUTED, icon_color="#7CB8FF")],
        "weather", "Minutes to rain", "Open-Meteo"),
    _screen("weather-metar", "METAR", "full", [
        _slot("metar", INK, station="CYYC", icon_color="#8FD3FF")],
        "weather", "Airport wind · rules", "aviationweather.gov"),
    _screen("focus-pomodoro", "Pomodoro", "full", [
        _slot("timer", "#FF6B5A", work_min=25, break_min=5)],
        "focus", "25 / 5 cycles", "Offline"),
    _screen("focus-countdown", "Countdown", "full", [
        _slot("countdown", "#FF8FC8", label="TOKYO", date="2026-10-21", accent=MUTED)],
        "focus", "Days until", "Offline"),
    _screen("focus-streak", "Habit streak", "full", [
        _slot("habit_week", "#5AE08A", label="STREAK", accent=MUTED)],
        "focus", "Tap to check off", "Offline"),
    _screen("focus-nextup", "Next up", "full", [
        _slot("calendar_next", INK, field="title", accent=MUTED)],
        "focus", "Calendar event", "Calendar (ICS)"),
    _screen("play-message", "Message", "bigsmall", [
        _slot("text", ["#FF7AB6", "#FFB23F"], text="HELLO"),
        _slot("text", MUTED, text="HAVE FUN")], "play", "Your words", "Offline"),
    _screen("play-pet", "Pixel pet", "full", [_slot("art", None, art_id="builtin-pet")],
            "play", "Sleeps at night", "Offline"),
    _screen("play-life", "Life", "full", [_slot("life", "#7CFF8A")],
            "play", "Conway, forever", "Offline"),
    _screen("play-fire", "Ember", "full", [_slot("fire", "#FF7A1F")],
            "play", "Ambient fire", "Offline"),
    _screen("play-music", "Now playing", "full", [
        _slot("feed", INK, feed_id=SAMPLE_FEEDS["music"], label="NOW", icon="note",
              accent=MUTED, icon_color="#B98CFF")], "play", "From your speaker", "JSON feed"),
    _screen("data-market", "Market", "full", [
        _slot("feed", "#5AE08A", feed_id=SAMPLE_FEEDS["market"], label="TSX", accent=INK)],
        "data", "Index · sparkline", "JSON feed"),
    _screen("data-score", "Score", "full", [
        _slot("feed", INK, feed_id=SAMPLE_FEEDS["score"], label="CGY EDM", accent="#FF9A3D")],
        "data", "Your team, live", "JSON feed"),
    _screen("data-transit", "Transit", "full", [
        _slot("feed", "#5AD1A0", feed_id=SAMPLE_FEEDS["transit"], label="201", icon="bus",
              accent=INK, icon_color="#5AD1A0")], "data", "Next departure", "JSON feed"),
    _screen("data-health", "Pi health", "full", [_slot("health", "#5AE08A", accent=AMBER)],
            "data", "Temp · network · feed", "This Pi"),
    _screen("night-clock", "Night clock", "full", [_slot("time", "#B3261E", font="5x7")],
            "clock", "Dim red time", "Offline"),
    _screen("time-simple", "Time only", "full", [_slot("time", "#FFFFFF", font="5x7")],
            "clock", "Time", "Offline"),
    _screen("time-weekday", "Time & weekday", "two", [
        _slot("time", "#FFFFFF"), _slot("weekday", "#FFB86C")], "clock", "Time · weekday", "Offline"),
]
BUILTINS = {screen["id"]: screen for screen in BUILTIN_SCREENS}

SHELVES = [
    {"id": "time", "title": "Time", "source": "Offline",
     "blurb": "Clocks that read from across the room.",
     "items": ["time-big", "time-classic", "time-analog", "time-words", "time-world",
               "time-world-one", "time-daybar", "night-clock"]},
    {"id": "sky", "title": "Sky", "source": "adsb.fi · ADSBdb",
     "blurb": "Planes, the ISS, and the sun from your spot on the map.",
     "items": ["sky-nearby", "sky-follow", "sky-radar", "sky-iss", "sky-sun"]},
    {"id": "weather", "title": "Weather", "source": "Uses location",
     "blurb": "Glanceable conditions, with the reading time kept visible.",
     "items": ["weather-now", "weather-hourly", "weather-rain", "weather-metar"]},
    {"id": "focus", "title": "Focus", "source": "Offline",
     "blurb": "Timers and countdowns you start from your phone.",
     "items": ["focus-pomodoro", "focus-countdown", "focus-streak", "focus-nextup"]},
    {"id": "play", "title": "Play", "source": "Offline",
     "blurb": "Messages, pets and ambient light for when nothing needs saying.",
     "items": ["play-message", "play-pet", "play-life", "play-fire", "play-music"]},
    {"id": "data", "title": "Data", "source": "Needs a feed",
     "blurb": "Numbers that change during the day.",
     "items": ["data-market", "data-score", "data-transit", "data-health"]},
]

LEGACY_IDS = {"clock-classic": "time-classic", "clock-simple": "time-simple",
              "clock-weekday": "time-weekday"}


def _art_frame(w: int, h: int, cells: dict[tuple[int, int], str]) -> str:
    return "".join(cells.get((x, y), ".") for y in range(h) for x in range(w))


def _pet_art() -> dict:
    cat = (".o........o.", ".oo......oo.", ".oooooooooo.", "oooooooooooo",
           "ooddooooddoo", "oooooppooooo", "oooooooooooo", ".oooooooooo.")
    index = {"o": "0", "d": "1", "p": "2"}
    body = {(10 + i, 5 + j): index[c] for j, row in enumerate(cat) for i, c in enumerate(row) if c in index}
    big_z = {(24 + i, j): "3" for j, mask in enumerate((7, 1, 2, 4, 7)) for i in range(3) if (mask >> (2 - i)) & 1}
    small_z = {(28, 3): "3", (29, 3): "3", (29, 2): "3", (28, 1): "3", (29, 1): "3"}
    drift = {(x - 1, y + 1): "3" for (x, y) in big_z}
    return {"id": "builtin-pet", "name": "Sleepy cat", "w": 32, "h": 16, "fps": 1,
            "palette": ["#FF9A3D", "#5A2E10", "#FF7AB6", FAINT],
            "frames": [_art_frame(32, 16, {**body, **big_z, **small_z}), _art_frame(32, 16, {**body, **drift})]}


def _heart_art() -> dict:
    cells = {}
    for j in range(16):
        for i in range(16):
            x, y = (i - 7.5) / 6.4, -(j - 6.6) / 6.4
            if (x * x + y * y - 1) ** 3 - x * x * y ** 3 <= 0:
                cells[(i, j)] = "0" if j < 16 * 0.45 else "1"
    for point in ((4, 4), (5, 4), (4, 5)):
        cells[point] = "2"
    return {"id": "builtin-heart", "name": "Heart", "w": 16, "h": 16, "fps": 1,
            "palette": ["#FF7AB6", "#FF3D5A", "#FFD1E6"], "frames": [_art_frame(16, 16, cells)]}


BUILTIN_ART = {art["id"]: art for art in (_pet_art(), _heart_art())}

SAMPLE_NOW = "2026-10-09T10:24:00-06:00"
SAMPLE_DATA = {
    "weather": {"temp_c": 14.0, "high_c": 18.0, "low_c": 6.0, "code": "sun",
                "hourly_c": [8.0, 9.0, 11.0, 13.0, 14.0, 15.0, 15.0, 14.0, 12.0, 10.0, 9.0, 8.0],
                "rain_in_min": 20, "observed_at": "2026-10-09T16:20:00Z", "age_s": 240},
    "metar": {"CYYC": {"station": "CYYC", "category": "VFR", "wind_dir": 290, "wind_kt": 12,
                       "gust_kt": None, "observed_at": "2026-10-09T16:00:00Z", "age_s": 1440}},
    "sun": {"sunrise": "2026-10-09T13:52:00Z", "sunset": "2026-10-10T00:51:00Z",
            "next_event": "sunset", "next_at": "2026-10-10T00:51:00Z", "daylight_progress": 0.805},
    "iss": {"distance_km": 1240.0, "bearing_deg": 315.0, "direction": "NW", "overhead": False,
            "updated_at": "2026-10-09T16:24:00Z"},
    "calendar": {"next": {"start": "2026-10-10T03:30:00Z", "title": "SYNC"},
                 "updated_at": "2026-10-09T16:15:00Z"},
    "feeds": {
        SAMPLE_FEEDS["market"]: {"value": "+0.8%", "series": [
            4, 5, 4, 6, 7, 6, 5, 6, 8, 9, 8, 7, 8, 10, 9, 11, 10, 9, 10, 12, 13, 12, 11, 12,
            14, 13, 15, 14, 16, 15, 17, 18], "updated_at": "2026-10-09T16:20:00Z", "error": None},
        SAMPLE_FEEDS["score"]: {"value": "3-2 P3", "series": [],
                                "updated_at": "2026-10-09T16:20:00Z", "error": None},
        SAMPLE_FEEDS["transit"]: {"value": "4 MIN", "series": [],
                                  "updated_at": "2026-10-09T16:22:00Z", "error": None},
        SAMPLE_FEEDS["music"]: {"value": "SIDE A", "series": [],
                                "updated_at": "2026-10-09T16:23:00Z", "error": None},
    },
    "health": {"cpu_temp_c": 48.0, "net_ok": True, "feed_age_s": 6},
    "aircraft": {
        "nearby": [
            {"callsign": "WJA123", "route": "YYC>YVR", "distance_nm": 3.2, "altitude_ft": 12000,
             "icon": "plane", "bearing_deg": 37.0},
            {"callsign": "ACA150", "route": "YYC>YYZ", "distance_nm": 5.5, "altitude_ft": 24000,
             "icon": "plane", "bearing_deg": 233.0},
            {"callsign": "WEN3373", "route": "YYC>YXE", "distance_nm": 6.1, "altitude_ft": 9000,
             "icon": "plane", "bearing_deg": 158.0},
            {"callsign": "FLE512", "route": "YEG>YYC", "distance_nm": 7.4, "altitude_ft": 15000,
             "icon": "plane", "bearing_deg": 323.0},
            {"callsign": "SWG401", "route": "YYC>CUN", "distance_nm": 8.8, "altitude_ft": 31000,
             "icon": "plane", "bearing_deg": 95.0},
            {"callsign": "DAL1854", "route": "MSP>YYC", "distance_nm": 9.6, "altitude_ft": 36000,
             "icon": "plane", "bearing_deg": 280.0},
            {"callsign": "JZA8211", "route": "YYC>YXX", "distance_nm": 10.0, "altitude_ft": 18000,
             "icon": "plane", "bearing_deg": 12.0},
        ],
        "tracked": {"callsign": "AC150", "route": "YYC>YVR", "origin": "YYC", "destination": "YVR",
                    "progress": 0.62, "remaining_min": 72, "altitude_ft": 34000, "speed_kt": 450},
        "updated_at": "2026-10-09T16:24:00Z",
    },
}

SAMPLE_TIMERS = {"focus-pomodoro": {"state": "paused", "phase": "work", "work_min": 25,
                                    "break_min": 5, "ends_at": None, "remaining_s": 1122, "cycles": 2}}
SAMPLE_HABITS = {"focus-streak": ["2026-09-%02d" % d for d in range(28, 31)]
                 + ["2026-10-%02d" % d for d in range(1, 10)]}


def sample_data() -> dict:
    """A deep copy of SAMPLE_DATA safe to mutate."""
    return copy.deepcopy(SAMPLE_DATA)


def catalog_json() -> dict:
    """The JSON body for GET /api/catalog."""
    return copy.deepcopy({
        "layouts": LAYOUTS, "palettes": PALETTES, "blocks": BLOCKS,
        "icons": {name: list(rows) for name, rows in ICONS.items()},
        "motions": MOTIONS, "transitions": TRANSITIONS, "colors": COLORS,
        "builtins": BUILTIN_SCREENS, "shelves": SHELVES, "legacy_ids": LEGACY_IDS,
        "art": list(BUILTIN_ART.values()),
    })

