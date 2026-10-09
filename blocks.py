"""Turn a screen (layout + blocks) into layers and pixels for the panel."""

from __future__ import annotations

import math
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, NamedTuple

import catalog
from render import ICONS, fit_text, hex_color, jround, measure, mix, rasterize

WHITE = "#FFFFFF"
INK, MUTED, FAINT, AMBER = catalog.INK, catalog.MUTED, catalog.FAINT, catalog.AMBER
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
HOUR_WORDS = ("TWELVE", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
              "NINE", "TEN", "ELEVEN")
WEATHER = {"sun": ("SUNNY", "SUN", "#FFC83D"), "cloud": ("CLOUDY", "CLOUD", "#C9D2FF"),
           "rain": ("RAINY", "RAIN", "#7CB8FF"), "snow": ("SNOWY", "SNOW", "#E8F6FF"),
           "storm": ("STORMY", "STORM", "#FFB23F"), "fog": ("FOGGY", "FOG", "#A3A19B"),
           "moon": ("CLEAR", "CLEAR", "#C9D2FF")}
FLIGHT_CATEGORY = {"VFR": "#5AE08A", "MVFR": "#7CB8FF", "IFR": "#FF5A5A", "LIFR": "#FF7AB6"}
ICON_TEXT = {"heart": "<3", "star": "+", "check": "OK", "note": "!"}
FIRE_RAMP = ("#FF3D1F", "#FF7A1F", "#FFB83D", "#FFE9A0")
FLIGHT_ROTATE_S = 10.0
LIFE_RATE, LIFE_CYCLE = 4, 240


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int

    def sub(self, dx: int, dy: int, w: int, h: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, w, h)

    @property
    def full(self) -> bool:
        return self.w >= 32 and self.h >= 16

    @property
    def icon_fits(self) -> bool:
        return self.w >= 7 and self.h >= 7


@dataclass
class RenderContext:
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    elapsed: float = 0.0
    data: dict = field(default_factory=dict)
    units: dict = field(default_factory=lambda: {"temp": "C", "distance": "nm"})
    art: dict = field(default_factory=dict)
    habits: dict = field(default_factory=dict)
    timers: dict = field(default_factory=dict)


def _valid_color(value) -> bool:
    if isinstance(value, str):
        return bool(COLOR_RE.fullmatch(value))
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, str) and COLOR_RE.fullmatch(v) for v in value))


def solid(color) -> str:
    return color[0] if isinstance(color, (list, tuple)) else color


def dim(color, amount: float = 0.45) -> str:
    return hex_color(mix("#000000", solid(color), amount))


def paint(color) -> dict:
    return {"grad": list(color)} if isinstance(color, (list, tuple)) else {"c": color}


def T(r: Rect, strings, color, **extra) -> dict:
    """Auto-fit text in a rect, trying each candidate string."""
    strings = [strings] if isinstance(strings, str) else list(strings)
    return {"t": "text", "f": "auto", "s": strings, "x": r.x, "y": r.y, "w": r.w, "h": r.h,
            **paint(color), **extra}


def long_text(r: Rect, text: str, color, **extra) -> dict:
    """Fit text, or scroll it in the largest font the rect's height allows."""
    if not fit_text([text], r.w, r.h)[2]:
        return T(r, [text], color, **extra)
    font = "5x7" if r.h >= 7 else "3x5"
    return {"t": "text", "f": font, "s": text, "x": r.x, "y": r.y, "w": r.w, "h": r.h,
            "scroll": True, **paint(color), **extra}


def icon(name: str, x: int, y: int, color, w: int | None = None, h: int | None = None) -> dict:
    layer = {"t": "icon", "n": name if name in ICONS else "plane", "x": x, "y": y, "c": solid(color)}
    if w:
        layer.update(w=w, h=h)
    return layer


@dataclass
class Slot:
    rect: Rect
    block: str
    color: object
    options: dict
    palette: dict | None
    forced: bool
    screen_id: str
    ctx: RenderContext

    def opt(self, name: str):
        spec = catalog.BLOCKS.get(self.block, {}).get("options", {}).get(name, {})
        value, default = self.options.get(name), spec.get("default")
        kind = spec.get("type")
        if value is None:
            return default
        if kind == "bool":
            return bool(value)
        if kind == "int":
            try:
                return max(spec.get("min", value), min(spec.get("max", value), int(value)))
            except (TypeError, ValueError):
                return default
        if kind == "enum":
            return value if value in spec.get("choices", ()) else default
        if kind == "color":
            return value if _valid_color(value) else default
        return value if isinstance(value, str) else default

    def accent(self, default) -> object:
        value = None if self.forced else self.opt("accent")
        if value:
            return value
        return self.palette["secondary"] if self.palette else default

    def icon_color(self, default) -> str:
        value = None if self.forced else self.opt("icon_color")
        if value:
            return solid(value)
        return solid(self.palette["primary"]) if self.palette else default

    def placeholder(self, strings, rect: Rect | None = None) -> list[dict]:
        return [T(rect or self.rect, strings, dim(self.color))]

    @property
    def data(self) -> dict:
        return self.ctx.data or {}

    def source(self, key: str) -> dict | None:
        value = self.data.get(key)
        return value if isinstance(value, dict) else None

    def local(self, value) -> datetime | None:
        return parse_time(value, self.ctx.now.tzinfo)


def parse_time(value, tz=None) -> datetime | None:
    if isinstance(value, (int, float)):
        moment = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    else:
        return None
    return moment.astimezone(tz) if tz else moment


def clock_text(moment: datetime, h24: bool) -> str:
    if h24:
        return f"{moment.hour:02d}:{moment.minute:02d}"
    return f"{moment.hour % 12 or 12}:{moment.minute:02d}"


def temp_value(celsius, units: dict) -> int | None:
    if not isinstance(celsius, (int, float)):
        return None
    return jround(celsius * 9 / 5 + 32 if units.get("temp") == "F" else celsius)


def distance_text(nm, units: dict) -> tuple[str, str] | None:
    if not isinstance(nm, (int, float)):
        return None
    km = units.get("distance") == "km"
    value = nm * 1.852 if km else nm
    text = f"{value:.1f}" if value < 10 else str(jround(value))
    return text, "KM" if km else "NM"


def minutes_text(minutes) -> str:
    minutes = max(0, int(minutes))
    return f"{minutes}M" if minutes < 100 else f"{minutes // 60}H{minutes % 60:02d}"


def age_text(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}S"
    if seconds < 3600:
        return f"{seconds // 60}M"
    return f"{seconds // 3600}H"


def rnd(i: float) -> float:
    value = math.sin(i * 127.1 + 311.7) * 43758.5453
    return value - math.floor(value)


# --- time -----------------------------------------------------------------

def b_time(s: Slot) -> list[dict]:
    now, r = s.ctx.now, s.rect
    value = clock_text(now, s.opt("h24"))
    if s.opt("colon_blink") and now.second % 2:
        value = value.replace(":", " ")
    font = s.opt("font")
    if font != "auto" and measure(value, font)[1] <= r.h:
        return [{"t": "text", "f": font, "s": value, "x": r.x, "y": r.y, "w": r.w, "h": r.h,
                 "scroll": True, **paint(s.color)}]
    return [T(r, [value], s.color)]


def b_date(s: Slot) -> list[dict]:
    now, r = s.ctx.now, s.rect
    wd, mon, day = WEEKDAYS[now.weekday()][:3], MONTHS[now.month - 1], str(now.day)
    style = s.opt("style")
    if style == "stack" and r.h >= 14:
        return [T(r.sub(0, 0, r.w, 7), _weekday_strings(now, r.w), s.color),
                T(r.sub(0, 9, r.w, 7), [day], s.accent(s.color))]
    if style == "short":
        return [T(r, [f"{wd} {day}", f"{mon} {day}", day], s.color)]
    return [T(r, [f"{wd} {mon} {day}", f"{mon} {day}", f"{wd} {day}", day], s.color)]


def _weekday_strings(now: datetime, width: int) -> list[str]:
    name = WEEKDAYS[now.weekday()]
    return [name, name[:3]] + ([name[0]] if width < measure(name[:3], "3x5")[0] else [])


def b_weekday(s: Slot) -> list[dict]:
    return [T(s.rect, _weekday_strings(s.ctx.now, s.rect.w), s.color)]


def b_analog(s: Slot) -> list[dict]:
    r, now = s.rect, s.ctx.now
    radius = (min(r.w, r.h) - 1) // 2
    if radius < 3:
        return b_time(s)
    wide = r.w >= 2 * radius + 1 + 12
    cx = r.x + radius if wide else r.x + (r.w - 1) // 2
    cy = r.y + (r.h - 1) // 2
    face = s.opt("face") if not s.forced and s.opt("face") else dim(s.color, 0.25)
    layers = [{"t": "analog", "cx": cx, "cy": cy, "r": radius, "hr": now.hour, "mn": now.minute,
               "c": solid(face), "hc": solid(s.color), "mc": solid(s.accent(s.color))}]
    side = r.sub(2 * radius + 1, 0, r.w - 2 * radius - 1, 7 if r.h >= 16 else r.h)
    if wide:
        layers.append(T(side, _weekday_strings(now, side.w)[1:], s.color))
    if wide and r.h >= 16:
        layers.append(T(side._replace(y=r.y + 9), [str(now.day)], s.accent(s.color)))
    return layers


def fuzzy_words(now: datetime) -> tuple[str, str, list[str]]:
    """Return (prefix, middle, last-line candidates) for a time in words."""
    minutes = now.minute + now.second / 60
    quarter = int((minutes + 7.5) // 15)
    diff = minutes - quarter * 15
    prefix = "NEARLY" if diff < -1 else "AFTER" if diff > 1 else "IT'S"
    hour = now.hour % 12
    after = (hour + 1) % 12
    if quarter in (0, 4):
        h = hour if quarter == 0 else after
        return prefix, HOUR_WORDS[h], ["O'CLOCK"]
    if quarter == 3:
        return prefix, "QUARTER", [f"TO {HOUR_WORDS[after]}", f"TO {after or 12}"]
    middle = "QUARTER" if quarter == 1 else "HALF"
    return prefix, middle, [f"PAST {HOUR_WORDS[hour]}", f"PAST {hour or 12}"]


def b_fuzzy(s: Slot) -> list[dict]:
    r = s.rect
    prefix, middle, last = fuzzy_words(s.ctx.now)
    if r.h >= 16:
        return [T(r.sub(0, 0, r.w, 5), [prefix], dim(s.color, 0.38)),
                T(r.sub(0, 6, r.w, 5), [middle], s.color),
                T(r.sub(0, 11, r.w, 5), last, s.accent(s.color))]
    return [T(r, [f"{middle} {last[0]}", f"{middle} {last[-1]}", middle], s.color)]


# --- weather --------------------------------------------------------------

def b_temp(s: Slot) -> list[dict]:
    weather, r, units = s.source("weather"), s.rect, s.ctx.units
    now = temp_value((weather or {}).get("temp_c"), units)
    high = temp_value((weather or {}).get("high_c"), units)
    low = temp_value((weather or {}).get("low_c"), units)
    which = s.opt("which")
    code = (weather or {}).get("code")
    words = WEATHER.get(code, ("--", "--", MUTED))
    hilo = [f"H{high} L{low}", f"{high}/{low}"] if high is not None and low is not None else ["--"]
    if r.full and which in ("now", "sky"):
        value = [f"{now}°"] if now is not None else ["--°"]
        return [icon(code if code in WEATHER else "cloud", r.x, r.y,
                     s.icon_color(words[2]) if code in WEATHER else dim(s.color)),
                T(r.sub(8, 0, r.w - 8, 7), value, s.color if now is not None else dim(s.color)),
                T(r.sub(0, 10, r.w, 5), hilo, s.accent(MUTED))]
    unit = units.get("temp", "C")
    options = {"now": [f"{now}°{unit}", f"{now}°"] if now is not None else None,
               "high": [f"H{high}", f"{high}°"] if high is not None else None,
               "low": [f"L{low}", f"{low}°"] if low is not None else None,
               "hilo": hilo if high is not None and low is not None else None,
               "sky": [f"{now}° {words[0]}", f"{now}° {words[1]}", f"{now}°"] if now is not None else None}
    strings = options.get(which)
    return [T(r, strings, s.color)] if strings else s.placeholder(["--°", "--"])


def b_weather_icon(s: Slot) -> list[dict]:
    weather, r = s.source("weather"), s.rect
    code = (weather or {}).get("code")
    if code not in WEATHER:
        if r.icon_fits:
            return [icon("cloud", r.x, r.y, dim(s.color), r.w, r.h)]
        return s.placeholder(["--"])
    if r.icon_fits:
        return [icon(code, r.x, r.y, s.color, r.w, r.h)]
    return [T(r, [WEATHER[code][0], WEATHER[code][1]], s.color)]


def b_rain(s: Slot) -> list[dict]:
    weather, r = s.source("weather"), s.rect
    if not weather:
        return s.placeholder(["--"])
    minutes = weather.get("rain_in_min")
    if isinstance(minutes, (int, float)):
        value = "NOW" if minutes <= 0 else minutes_text(minutes)
        label = "RAINING" if minutes <= 0 else "RAIN IN"
        small = [f"RAIN {value}", value]
    else:
        value, label, small = "DRY", "NO RAIN", ["NO RAIN", "DRY"]
    if not r.full:
        return [T(r, small, s.color)]
    return [icon("rain", r.x, r.y, s.icon_color("#7CB8FF")),
            T(r.sub(8, 1, r.w - 8, 5), [label, label.split()[0]], s.accent(MUTED)),
            T(r.sub(8, 9, r.w - 8, 7), [value], s.color)]


def b_hourly(s: Slot) -> list[dict]:
    weather, r = s.source("weather"), s.rect
    temps = [temp_value(v, s.ctx.units) for v in (weather or {}).get("hourly_c") or ()]
    temps = [v for v in temps if v is not None]
    if not temps:
        return s.placeholder(["NO DATA", "--"])
    layers = []
    if r.h >= 12:
        layers.append(T(r.sub(0, 0, r.w, 5), [f"NEXT {len(temps)}H", "NEXT"], MUTED))
        r = r.sub(0, 6, r.w, r.h - 6)
    return layers + [spark(r, temps, s.color, s.accent(None))]


def spark(r: Rect, values: list[float], color, top=None) -> dict:
    values = values[:max(1, r.w)]
    bw = max(1, r.w // len(values))
    total = min(r.w, bw * len(values))
    c2 = top if top else (color[1] if isinstance(color, (list, tuple)) else None)
    layer = {"t": "spark", "x": r.x + (r.w - total) // 2, "y": r.y, "w": total, "h": r.h,
             "d": values, "c": solid(color)}
    if c2:
        layer["c2"] = solid(c2)
    return layer


def b_metar(s: Slot) -> list[dict]:
    r = s.rect
    station = str(s.opt("station") or "").strip().upper()
    if not station:
        return s.placeholder(["SET UP", "SET"])
    report = ((s.source("metar") or {}).get(station))
    if not isinstance(report, dict):
        return s.placeholder([station, "--"])
    category = str(report.get("category") or "--").upper()
    cat_color = FLIGHT_CATEGORY.get(category, MUTED)
    kt, gust = report.get("wind_kt"), report.get("gust_kt")
    if not isinstance(kt, (int, float)):
        wind = ["--"]
    elif kt == 0:
        wind = ["CALM"]
    elif gust:
        wind = [f"{kt}G{gust}KT", f"{kt}G{gust}", f"{kt}KT"]
    else:
        wind = [f"{kt}KT", str(kt)]
    if r.full:
        return [T(r.sub(0, 0, r.w, 5), [station], s.color, a="l"),
                T(r.sub(0, 0, r.w, 5), [category], cat_color, a="r"),
                icon("wind", r.x, r.y + 8, s.icon_color("#8FD3FF")),
                T(r.sub(9, 8, r.w - 9, 7), wind, s.color)]
    field_ = s.opt("field")
    if field_ == "station":
        return [T(r, [station], s.color)]
    if field_ == "wind":
        return [T(r, wind, s.color)]
    return [T(r, [category], cat_color)]


# --- sky ------------------------------------------------------------------

def _callsign(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _plane(s: Slot) -> tuple[dict | None, str]:
    aircraft = s.source("aircraft") or {}
    if s.opt("source") == "follow":
        wanted = _callsign(s.opt("callsign"))
        tracked = aircraft.get("tracked")
        if isinstance(tracked, dict) and (not wanted or _callsign(tracked.get("callsign")) == wanted):
            return tracked, "follow"
        return None, "follow" if wanted else "setup"
    nearby = [p for p in aircraft.get("nearby") or () if isinstance(p, dict)]
    if not nearby:
        return None, "nearby"
    return nearby[int(s.ctx.elapsed // FLIGHT_ROTATE_S) % len(nearby)], "nearby"


def _flight_strings(s: Slot, plane: dict, mode: str) -> dict[str, list[str]]:
    callsign = _callsign(plane.get("callsign")) or "----"
    prefix = re.match(r"[A-Z]*", callsign).group() or callsign
    route = str(plane.get("route") or "").upper()
    if mode == "follow":
        remaining = plane.get("remaining_min")
        rem = minutes_text(remaining) if isinstance(remaining, (int, float)) else "--"
        detail = [f"{rem} LEFT", rem]
    else:
        dist = distance_text(plane.get("distance_nm"), s.ctx.units)
        alt = plane.get("altitude_ft")
        alt_text = f"{jround(alt / 1000)}K" if isinstance(alt, (int, float)) else ""
        dist_text = "".join(dist) if dist else "--"
        detail = [f"{dist_text} {alt_text}".strip(), dist_text]
    return {"callsign": [callsign, prefix], "route": [route] if route else detail, "detail": detail}


def b_flight(s: Slot) -> list[dict]:
    r = s.rect
    plane, mode = _plane(s)
    if mode == "setup":
        return s.placeholder(["SET UP", "SET"])
    if plane is None:
        if not r.full:
            return s.placeholder(["NO PLANES", "NONE", "--"])
        label = ["IN RANGE"] if mode == "nearby" else [_callsign(s.opt("callsign")) or "--"]
        return [icon("plane", r.x, r.y, dim(s.icon_color(AMBER))),
                T(r.sub(8, 0, r.w - 8, 7), ["NONE", "--"] if mode == "nearby" else ["NOT SEEN", "--"], dim(s.color)),
                T(r.sub(0, 10, r.w, 5), label, dim(s.accent(MUTED)))]
    strings = _flight_strings(s, plane, mode)
    if not r.full:
        return [T(r, strings[s.opt("field")], s.color)]
    if mode == "follow":
        return _follow_card(s, plane, strings)
    return [icon(plane.get("icon") or "plane", r.x, r.y, s.icon_color(AMBER)),
            T(r.sub(8, 0, r.w - 8, 7), strings["callsign"], s.color),
            T(r.sub(0, 10, r.w, 5), strings["route"], s.accent("#8FD3FF"))]


def _follow_card(s: Slot, plane: dict, strings: dict) -> list[dict]:
    r = s.rect
    progress = plane.get("progress")
    value = max(0.0, min(1.0, float(progress))) if isinstance(progress, (int, float)) else 0.0
    accent = s.accent(MUTED)
    marker = max(r.x + 1, min(r.x + r.w - 2, r.x + jround(value * r.w)))
    layers = [T(r.sub(0, 0, r.w, 5), strings["callsign"][:1], s.color, a="l"),
              T(r.sub(0, 0, r.w, 5), strings["detail"][-1:], accent, a="r"),
              {"t": "bar", "x": r.x, "y": r.y + 7, "w": r.w, "h": 1, "v": value,
               "c": s.icon_color(AMBER), "bg": "#2A2A2E"}]
    if isinstance(progress, (int, float)):
        layers.append({"t": "px", "x": marker - 1, "y": r.y + 6, "rows": [".#.", "###", ".#."],
                       "pal": {"#": solid(s.color)}})
    origin = str(plane.get("origin") or "").upper()
    destination = str(plane.get("destination") or "").upper()
    if not (origin and destination) and ">" in str(plane.get("route") or ""):
        origin, destination = str(plane["route"]).upper().split(">", 1)
    layers += [T(r.sub(0, 11, r.w, 5), [origin or "---"], accent, a="l"),
               T(r.sub(0, 11, r.w, 5), [destination or "---"], accent, a="r")]
    return layers


def b_plane_count(s: Slot) -> list[dict]:
    r = s.rect
    nearby = (s.source("aircraft") or {}).get("nearby")
    if not isinstance(nearby, list):
        return s.placeholder(["--"])
    count = str(len(nearby))
    if r.w >= 16 and r.h >= 7:
        return [icon("plane", r.x, r.y, s.color, 8, r.h), T(r.sub(8, 0, r.w - 8, r.h), [count], s.color)]
    return [T(r, [count], s.color)]


def _bearing(plane: dict) -> float:
    value = plane.get("bearing_deg")
    if isinstance(value, (int, float)):
        return float(value)
    return zlib.crc32(_callsign(plane.get("callsign")).encode()) % 360


def b_radar(s: Slot) -> list[dict]:
    r = s.rect
    nearby = (s.source("aircraft") or {}).get("nearby")
    radius = (min(r.w, r.h) - 1) // 2
    if radius < 4:
        return [T(r, [str(len(nearby))], s.color)] if isinstance(nearby, list) else s.placeholder(["--"])
    wide = r.w >= 2 * radius + 1 + 12
    cx = r.x + radius if wide else r.x + (r.w - 1) // 2
    cy = r.y + (r.h - 1) // 2
    color = solid(s.color)
    ring = dim(color, 0.25) if isinstance(nearby, list) else dim(color, 0.15)
    sweep = math.radians(45 + s.ctx.elapsed * 90)
    layers = [{"t": "circle", "cx": cx, "cy": cy, "r": radius, "c": ring},
              {"t": "circle", "cx": cx, "cy": cy, "r": radius // 2, "c": ring, "dotted": True},
              {"t": "line", "x1": cx, "y1": cy, "x2": cx + math.sin(sweep) * radius,
               "y2": cy - math.cos(sweep) * radius, "c": dim(color, 0.4)}]
    points = [[cx, cy, color]]
    planes = nearby if isinstance(nearby, list) else []
    dists = [p.get("distance_nm") for p in planes if isinstance(p, dict)
             and isinstance(p.get("distance_nm"), (int, float))]
    reach = max([5.0] + dists) * 1.05
    for index, plane in enumerate(p for p in planes if isinstance(p, dict)):
        dist = plane.get("distance_nm")
        if not isinstance(dist, (int, float)):
            continue
        angle, length = math.radians(_bearing(plane)), dist / reach * (radius - 1)
        tone = hex_color(mix(color, WHITE, 0.45)) if index == 0 else color
        points.append([jround(cx + math.sin(angle) * length), jround(cy - math.cos(angle) * length), tone])
    layers.append({"t": "pts", "p": points})
    count = str(len(planes)) if isinstance(nearby, list) else "--"
    side = r.sub(2 * radius + 2, 0, r.w - 2 * radius - 2, r.h)
    if wide and r.h >= 15:
        layers += [T(side._replace(y=r.y + 1, h=7), [count], s.color),
                   T(side._replace(y=r.y + 10, h=5), ["NEAR"], s.accent(dim(color, 0.7)))]
    elif wide:
        layers.append(T(side, [count], s.color))
    return layers


def b_iss(s: Slot) -> list[dict]:
    r, iss = s.rect, s.source("iss")
    km = (iss or {}).get("distance_km")
    if not isinstance(km, (int, float)):
        return s.placeholder(["--"]) if not r.full else [
            icon("iss", r.x + 1, r.y + 1, dim(s.icon_color("#C9D2FF"))),
            T(r.sub(10, 1, r.w - 10, 5), ["ISS"], dim(s.icon_color("#C9D2FF")), a="l"),
            T(r.sub(0, 9, r.w, 7), ["--"], dim(s.color))]
    direction = str(iss.get("direction") or "--").upper()
    if iss.get("overhead"):
        value = ["OVERHEAD", "ABOVE", "UP"]
    else:
        number, unit = distance_text(km / 1.852, s.ctx.units)
        number = str(jround(float(number)))
        value = [f"{number}{unit}", number]
    if r.full:
        brand = s.icon_color("#C9D2FF")
        return [icon("iss", r.x + 1, r.y + 1, brand),
                T(r.sub(10, 1, r.w - 10, 5), ["ISS"], brand, a="l"),
                T(r.sub(10, 1, r.w - 10, 5), [direction], s.accent(MUTED), a="r"),
                T(r.sub(0, 9, r.w, 7), value, s.color)]
    field_ = s.opt("field")
    if field_ == "direction":
        return [T(r, [direction], s.color)]
    if field_ == "label":
        return [T(r, ["ISS"], s.color)]
    return [T(r, value, s.color)]


def _sun_event(s: Slot, event: str) -> tuple[str, datetime] | None:
    sun = s.source("sun") or {}
    if event == "next":
        event = sun.get("next_event") if sun.get("next_event") in ("sunrise", "sunset") else "sunset"
        moment = s.local(sun.get("next_at")) or s.local(sun.get(event))
    else:
        moment = s.local(sun.get(event))
    return ("RISE" if event == "sunrise" else "SET", moment) if moment else None


def b_sun_time(s: Slot) -> list[dict]:
    found = _sun_event(s, s.opt("event"))
    if not found:
        return s.placeholder(["--:--", "--"])
    label, moment = found
    text = clock_text(moment, s.opt("h24"))
    return [T(s.rect, [f"{label} {text}", text], s.color)]


def b_sun_arc(s: Slot) -> list[dict]:
    r = s.rect
    if r.w < 24 or r.h < 12:
        return b_sun_time(s)
    found = _sun_event(s, "next")
    cx, horizon = r.x + (r.w - 1) // 2, r.y + r.h - 7
    radius = min(8, horizon - r.y - 1, (r.w - 1) // 2)
    line = dim(s.color, 0.35 if found else 0.2)
    layers = [{"t": "arc", "cx": cx, "cy": horizon, "r": radius, "c": line, "dotted": True},
              {"t": "rect", "x": r.x, "y": horizon, "w": r.w, "h": 1, "c": line}]
    progress = (s.source("sun") or {}).get("daylight_progress")
    if isinstance(progress, (int, float)) and 0 < progress < 1:
        angle = math.pi * (1 - progress)
        sx, sy = cx + radius * math.cos(angle), horizon - radius * math.sin(angle)
        layers.append({"t": "rect", "x": jround(sx) - 1, "y": jround(sy) - 1, "w": 2, "h": 2,
                       "c": solid(s.color)})
    label = r.sub(0, r.h - 5, r.w, 5)
    if not found:
        return layers + [T(label, ["--:--"], dim(s.color))]
    name, moment = found
    text = clock_text(moment, s.opt("h24"))
    return layers + [T(label, [f"{name} {text}", text], s.color)]


# --- focus ----------------------------------------------------------------

def b_countdown(s: Slot) -> list[dict]:
    r = s.rect
    try:
        target = date.fromisoformat(str(s.opt("date"))[:10])
    except ValueError:
        return s.placeholder(["SET UP", "SET"])
    days = (target - s.ctx.now.date()).days
    label = str(s.opt("label") or "").strip().upper()
    if days > 0:
        value = [f"{days} DAY" if days == 1 else f"{days} DAYS", f"{days}D"]
    elif days == 0:
        value = ["TODAY", "NOW"]
    else:
        value = ["DONE", "--"]
    if r.full:
        top = [f"{label} IN", label] if label and days > 0 else [label or "COUNTDOWN", "DAYS"]
        return [T(r.sub(0, 1, r.w, 5), top, s.accent(MUTED)), T(r.sub(0, 8, r.w, 7), value, s.color)]
    if label and days > 0:
        return [T(r, [f"{label} {value[-1]}", *value], s.color)]
    return [T(r, value, s.color)]


def timer_state(s: Slot, timer_id: str | None = None) -> tuple[int, float, int, str]:
    """Return (remaining seconds, progress 0-1, cycles, phase) for a timer."""
    timer = s.ctx.timers.get(timer_id or s.screen_id) or {}
    work = timer.get("work_min") or s.opt("work_min") or 25
    rest = timer.get("break_min") or s.opt("break_min") or 5
    phase = timer.get("phase") if timer.get("phase") in ("work", "break") else "work"
    total = (work if phase == "work" else rest) * 60
    state = timer.get("state")
    if state == "running" and isinstance(timer.get("ends_at"), (int, float)):
        remaining = timer["ends_at"] - s.ctx.now.timestamp()
    elif state == "paused" and isinstance(timer.get("remaining_s"), (int, float)):
        remaining = timer["remaining_s"]
    else:
        remaining = total
    remaining = max(0, min(int(math.ceil(remaining)), 99 * 60 + 59))
    cycles = timer.get("cycles") if isinstance(timer.get("cycles"), int) else 0
    return remaining, 1 - remaining / total if total else 0.0, cycles, phase


def b_timer(s: Slot) -> list[dict]:
    r = s.rect
    remaining, progress, cycles, phase = timer_state(s)
    color = s.color if phase == "work" else s.accent("#5AD1A0")
    value = f"{remaining // 60}:{remaining % 60:02d}"
    if not r.full:
        return [T(r, [value], color)]
    return [T(r.sub(0, 0, r.w, 10), [value], color),
            {"t": "bar", "x": r.x + 1, "y": r.y + 12, "w": r.w - 2, "h": 2, "v": progress,
             "c": solid(color), "bg": dim(color, 0.23)},
            {"t": "dots", "x": r.x + (r.w - 10) // 2, "y": r.y + 15, "n": 4, "size": 1, "gap": 2,
             "on": [1 if i < cycles % 4 else 0 for i in range(4)], "c": solid(color),
             "off": dim(color, 0.23)}]


def b_habit(s: Slot) -> list[dict]:
    r = s.rect
    habit_id = str(s.opt("habit_id") or s.screen_id)
    done = {str(d) for d in s.ctx.habits.get(habit_id) or ()}
    today = s.ctx.now.date()
    monday = today - timedelta(days=today.weekday())
    week = [1 if (monday + timedelta(days=i)).isoformat() in done else 0 for i in range(7)]
    day = today if today.isoformat() in done else today - timedelta(days=1)
    streak = 0
    while day.isoformat() in done and streak < 999:
        streak, day = streak + 1, day - timedelta(days=1)
    if r.w < 27 or r.h < 10:
        return [T(r, [f"{streak} DAYS", f"{streak}D", str(streak)], s.color)]
    x = r.x + (r.w - 27) // 2
    dots = {"t": "dots", "n": 7, "size": 3, "gap": 1, "on": week, "c": solid(s.color),
            "off": dim(s.color, 0.2), "x": x}
    letters = {"t": "text", "f": "3x5", "s": "MTWTFSS", "x": x, "w": 27, "a": "l", "c": FAINT}
    today_letter = {"t": "text", "f": "3x5", "s": "MTWTFSS"[today.weekday()], "x": x + 4 * today.weekday(),
                    "w": 3, "a": "l", "c": MUTED}
    if r.h >= 16:
        label = str(s.opt("label") or "").upper()
        return [T(r.sub(0, 0, r.w, 5), [label] if label else [""], s.accent(MUTED), a="l"),
                T(r.sub(0, 0, r.w, 5), [str(streak)], s.color, a="r"),
                {**dots, "y": r.y + 6}, {**letters, "y": r.y + 11}, {**today_letter, "y": r.y + 11}]
    return [{**dots, "y": r.y}, {**letters, "y": r.y + 5}, {**today_letter, "y": r.y + 5}]


def b_progress(s: Slot) -> list[dict]:
    r, now = s.rect, s.ctx.now
    source = s.opt("source")
    value, label = None, ""
    if source == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        value, label = (now - start).total_seconds() / 86400, "DAY"
    elif source == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        days = 366 if (now.year % 4 == 0 and (now.year % 100 or now.year % 400 == 0)) else 365
        value, label = (now - start).total_seconds() / (days * 86400), "YEAR"
    elif source == "timer":
        value, label = timer_state(s)[1], "TIMER"
    else:
        tracked = (s.source("aircraft") or {}).get("tracked") or {}
        wanted = _callsign(s.opt("callsign"))
        if isinstance(tracked, dict) and (not wanted or _callsign(tracked.get("callsign")) == wanted):
            progress = tracked.get("progress")
            value = float(progress) if isinstance(progress, (int, float)) else None
        label = "FLIGHT"
    bg = dim(s.color, 0.23)
    layers = []
    if r.h >= 12:
        text = [f"{label} {jround(value * 100)}%", f"{jround(value * 100)}%"] if value is not None else ["--"]
        layers.append(T(r.sub(0, 0, r.w, 7), text, s.color if value is not None else dim(s.color)))
        bar = r.sub(1, 9, r.w - 2, 3)
    elif r.h >= 6:
        bar = r.sub(1, 1, r.w - 2, 3)
    else:
        height = min(3, r.h)
        bar = r.sub(0, (r.h - height) // 2, r.w, height)
    layers.append({"t": "bar", "x": bar.x, "y": bar.y, "w": bar.w, "h": bar.h,
                   "v": value or 0.0, "c": solid(s.color), "bg": bg})
    if r.h >= 6 and source in ("day", "year") and bar.y + 4 < r.y + r.h:
        layers.append({"t": "pts", "p": [[bar.x + jround(i * (bar.w - 1) / 4), bar.y + 4, FAINT]
                                         for i in range(5)]})
    return layers


def b_calendar(s: Slot) -> list[dict]:
    r, calendar = s.rect, s.source("calendar")
    if calendar is None:
        return s.placeholder(["--"])
    event = calendar.get("next")
    start = s.local(event.get("start")) if isinstance(event, dict) else None
    if not start:
        return s.placeholder(["NO EVENTS", "FREE"])
    clock = clock_text(start, s.opt("h24"))
    when = clock if start.date() == s.ctx.now.date() else f"{WEEKDAYS[start.weekday()][:3]} {clock}"
    times = [f"NEXT {when}", when, clock]
    title = str(event.get("title") or "EVENT").upper()
    if r.full:
        return [T(r.sub(0, 0, r.w, 5), times, s.accent(MUTED)), long_text(r.sub(0, 8, r.w, 7), title, s.color)]
    if s.opt("field") == "time":
        return [T(r, times, s.color)]
    return [long_text(r, title, s.color)]


# --- data -----------------------------------------------------------------

def b_feed(s: Slot) -> list[dict]:
    r = s.rect
    feed_id = str(s.opt("feed_id") or "")
    label = str(s.opt("label") or "").upper()
    if not feed_id:
        return s.placeholder(["SET UP", "SET"])
    feed = (s.source("feeds") or {}).get(feed_id)
    value = feed.get("value") if isinstance(feed, dict) else None
    series = [v for v in (feed or {}).get("series") or () if isinstance(v, (int, float))] if feed else []
    value_color = s.color if value is not None else dim(s.color)
    text = str(value).upper() if value is not None else ("ERROR" if (feed or {}).get("error") else "--")
    if not r.full:
        if s.opt("field") == "label":
            return [T(r, [label or "--"], s.color)]
        return [long_text(r, text, value_color)]
    accent = s.accent(MUTED)
    name = s.opt("icon")
    if name in ICONS:
        return [icon(name, r.x, r.y, s.icon_color(solid(s.color))),
                T(r.sub(9, 1, r.w - 9, 5), [label], accent, a="l"),
                long_text(r.sub(0, 9, r.w, 7), text, value_color)]
    if len(series) >= 2:
        return [T(r.sub(0, 0, r.w, 5), [label], accent, a="l"),
                T(r.sub(0, 0, r.w, 5), [text], value_color, a="r" if label else "c"),
                {"t": "spark", "line": True, "x": r.x, "y": r.y + 7, "w": r.w, "h": r.h - 7,
                 "d": series[-r.w:], "c": solid(s.color), "fill": dim(s.color, 0.2)}]
    return [T(r.sub(0, 1, r.w, 5), [label], accent), long_text(r.sub(0, 8, r.w, 7), text, value_color)]


def b_spark(s: Slot) -> list[dict]:
    if s.opt("source") == "feed":
        feed = (s.source("feeds") or {}).get(str(s.opt("feed_id") or "")) or {}
        values = [v for v in feed.get("series") or () if isinstance(v, (int, float))]
    else:
        weather = s.source("weather") or {}
        values = [temp_value(v, s.ctx.units) for v in weather.get("hourly_c") or ()]
        values = [v for v in values if v is not None]
    if not values:
        return s.placeholder(["--"])
    return [spark(s.rect, values[-s.rect.w:], s.color, s.accent(None))]


def b_health(s: Slot) -> list[dict]:
    r, health = s.rect, s.source("health")
    if not health:
        return s.placeholder(["--"])
    cpu = temp_value(health.get("cpu_temp_c"), s.ctx.units)
    hot = isinstance(health.get("cpu_temp_c"), (int, float)) and health["cpu_temp_c"] >= 70
    net = health.get("net_ok")
    age = age_text(health.get("feed_age_s"))
    lines = {"cpu": ([f"CPU {cpu}°", f"{cpu}°"] if cpu is not None else ["CPU --", "--"],
                     s.accent(AMBER) if hot else s.color),
             "net": (["NET OK", "OK"] if net else ["NET DOWN", "DOWN"] if net is False else ["NET --", "--"],
                     s.color if net else s.accent(AMBER)),
             "feed": ([f"FEED {age}", age], s.accent(AMBER))}
    if r.full:
        return [T(r.sub(0, y, r.w, 5), *lines[key], a="l")
                for y, key in ((0, "cpu"), (6, "net"), (11, "feed"))]
    strings, color = lines[s.opt("field")]
    return [T(r, strings, color)]


# --- play -----------------------------------------------------------------

def _wrap(text: str, font: str, width: int) -> list[str] | None:
    lines: list[str] = []
    for word in text.split():
        if measure(word, font)[0] > width:
            return None
        if lines and measure(f"{lines[-1]} {word}", font)[0] <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def b_text(s: Slot) -> list[dict]:
    r = s.rect
    text = " ".join(str(s.opt("text") or "").upper().split())
    if not text:
        return []
    if not fit_text([text], r.w, r.h)[2]:
        return [T(r, [text], s.color)]
    for font, height, gap in (("5x7", 7, 2), ("3x5", 5, 1)):
        lines = _wrap(text, font, r.w)
        if not lines or len(lines) < 2:
            continue
        total = len(lines) * height + (len(lines) - 1) * gap
        if total <= r.h:
            top = r.y + (r.h - total) // 2
            return [{"t": "text", "f": font, "s": line, "x": r.x, "y": top + i * (height + gap),
                     "w": r.w, **paint(s.color)} for i, line in enumerate(lines)]
    return [long_text(r, text, s.color)]


def b_icon(s: Slot) -> list[dict]:
    r, name = s.rect, s.opt("name")
    if r.icon_fits or (r.w >= 7 and r.h >= len(ICONS.get(name, ())) > 0):
        return [icon(name, r.x, r.y, s.color, r.w, r.h)]
    return [T(r, [ICON_TEXT.get(name, name.upper()), "*"], s.color)]


def b_art(s: Slot) -> list[dict]:
    r = s.rect
    art_id = str(s.opt("art_id") or "")
    art = s.ctx.art.get(art_id) or catalog.BUILTIN_ART.get(art_id)
    if not isinstance(art, dict) or not art.get("frames"):
        return s.placeholder(["NO ART", "ART", "?"])
    w, h = int(art.get("w") or 0), int(art.get("h") or 0)
    palette = art.get("palette") or []
    frames = art["frames"]
    fps = max(1, min(12, int(art.get("fps") or 1)))
    cells = str(frames[int(s.ctx.elapsed * fps) % len(frames)])
    ox, oy = r.x + (r.w - w) // 2, r.y + (r.h - h) // 2
    points = []
    for index, char in enumerate(cells[:w * h]):
        if char == ".":
            continue
        slot = int(char, 16) if char in "0123456789abcdefABCDEF" else -1
        x, y = ox + index % w, oy + index // w
        if 0 <= slot < len(palette) and r.x <= x < r.x + r.w and r.y <= y < r.y + r.h:
            points.append([x, y, palette[slot]])
    return [{"t": "pts", "p": points}]


_LIFE_CACHE: dict[tuple[int, int, int], tuple[int, frozenset]] = {}


def _life_seed(w: int, h: int, cycle: int, salt: int) -> frozenset:
    return frozenset((x, y) for y in range(h) for x in range(w)
                     if rnd(x * 31 + y * 17 + cycle * 1013 + salt * 7919) > 0.74)


def _life_step(cells: frozenset, w: int, h: int) -> frozenset:
    counts: dict[tuple[int, int], int] = {}
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    key = ((x + dx) % w, (y + dy) % h)
                    counts[key] = counts.get(key, 0) + 1
    return frozenset(p for p, n in counts.items() if n == 3 or (n == 2 and p in cells))


def life_cells(w: int, h: int, elapsed: float) -> frozenset:
    """Conway's life on a torus, deterministic for a given elapsed time."""
    cycle, generation = divmod(int(max(0.0, elapsed) * LIFE_RATE), LIFE_CYCLE)
    key = (w, h, cycle)
    cached = _LIFE_CACHE.get(key)
    step, cells = cached if cached and cached[0] <= generation else (0, _life_seed(w, h, cycle, 0))
    while step < generation:
        following = _life_step(cells, w, h)
        step += 1
        cells = _life_seed(w, h, cycle, step) if len(following) < 3 or following == cells else following
    if len(_LIFE_CACHE) > 8:
        _LIFE_CACHE.clear()
    _LIFE_CACHE[key] = (generation, cells)
    return cells


def b_life(s: Slot) -> list[dict]:
    r = s.rect
    color = solid(s.color)
    low = hex_color(mix("#000000", color, 0.3))
    return [{"t": "pts", "p": [[r.x + x, r.y + y, hex_color(mix(low, color, rnd(x + y * 91)))]
                               for x, y in sorted(life_cells(r.w, r.h, s.ctx.elapsed))]}]


def b_fire(s: Slot) -> list[dict]:
    r = s.rect
    color = solid(s.color)
    ramp = FIRE_RAMP if color.upper() in ("#FF7A1F", WHITE) else (
        dim(color, 0.75), color, hex_color(mix(color, WHITE, 0.4)), hex_color(mix(color, WHITE, 0.75)))
    t = max(0.0, s.ctx.elapsed) * 8
    t0, frac = int(t), t - int(t)
    points = []
    for i in range(r.w):
        def base(k: int) -> float:
            return 4 + math.floor(rnd(i * 3.7 + k * 13.1) * 7) + (3 if i % 6 == 2 else 0)
        height = jround((base(t0) * (1 - frac) + base(t0 + 1) * frac) * r.h / 16)
        for k in range(height):
            level = k / height
            tone = ramp[0] if level < 0.3 else ramp[1] if level < 0.6 else ramp[2] if level < 0.85 else ramp[3]
            points.append([r.x + i, r.y + r.h - 1 - k, tone])
        spark_y = r.h - 1 - height - 2
        if rnd(i * 9.1 + t0 * 5.3) > 0.8 and spark_y >= 0:
            points.append([r.x + i, r.y + spark_y, ramp[1]])
    return [{"t": "pts", "p": points}]


def b_none(s: Slot) -> list[dict]:
    return []


RENDERERS: dict[str, Callable[[Slot], list[dict]]] = {
    "time": b_time, "date": b_date, "weekday": b_weekday, "temp": b_temp,
    "weather_icon": b_weather_icon, "rain": b_rain, "sun_time": b_sun_time, "flight": b_flight,
    "plane_count": b_plane_count, "countdown": b_countdown, "timer": b_timer, "text": b_text,
    "progress": b_progress, "spark": b_spark, "icon": b_icon, "art": b_art, "feed": b_feed,
    "calendar_next": b_calendar, "metar": b_metar, "iss": b_iss, "health": b_health,
    "analog_clock": b_analog, "fuzzy_time": b_fuzzy, "radar": b_radar, "sun_arc": b_sun_arc,
    "hourly_graph": b_hourly, "habit_week": b_habit, "life": b_life, "fire": b_fire, "none": b_none,
}


def _slot_color(value, index: int, palette: dict | None, forced: bool):
    if palette and (forced or not _valid_color(value)):
        return palette["primary"] if index == 0 else palette["secondary"]
    return value if _valid_color(value) else WHITE


def render_screen(screen: dict, ctx: RenderContext, palette: str | None = None,
                  strict: bool = False) -> list[dict]:
    """Build the layer list for a screen. `palette` forces a palette over every slot color."""
    layout = catalog.LAYOUTS.get(screen.get("layout")) or catalog.LAYOUTS["full"]
    style = screen.get("style") if isinstance(screen.get("style"), dict) else {}
    pal = catalog.PALETTES.get(palette or style.get("palette"))
    forced = palette is not None and pal is not None
    slots = screen.get("slots") if isinstance(screen.get("slots"), list) else []
    layers: list[dict] = []
    for index, rect in enumerate(layout["slots"]):
        slot = slots[index] if index < len(slots) and isinstance(slots[index], dict) else {}
        block = slot.get("block") if slot.get("block") in RENDERERS else "none"
        options = slot.get("options") if isinstance(slot.get("options"), dict) else {}
        s = Slot(Rect(rect["x"], rect["y"], rect["w"], rect["h"]), block,
                 _slot_color(slot.get("color"), index, pal, forced), options, pal, forced,
                 str(screen.get("id") or ""), ctx)
        try:
            layers += RENDERERS[block](s)
        except Exception:
            if strict:
                raise
            layers += s.placeholder(["?"])
    return layers


def frame(screen: dict, ctx: RenderContext, palette: str | None = None) -> list[tuple[int, int, int]]:
    """Render a screen to 512 RGB pixels."""
    return rasterize(render_screen(screen, ctx, palette), ctx.elapsed)


def data_needs(screen: dict) -> set[str]:
    """The provider needs (see Contract 2) for a screen's blocks."""
    needs: set[str] = set()
    for slot in screen.get("slots") or ():
        if not isinstance(slot, dict):
            continue
        block = slot.get("block")
        options = slot.get("options") if isinstance(slot.get("options"), dict) else {}
        if block in ("temp", "weather_icon", "rain", "hourly_graph"):
            needs.add("weather")
        elif block in ("sun_time", "sun_arc"):
            needs.add("sun")
        elif block in ("iss", "calendar_next", "health"):
            needs.add({"iss": "iss", "calendar_next": "calendar", "health": "health"}[block])
        elif block in ("plane_count", "radar"):
            needs.add("aircraft:nearby")
        elif block == "timer":
            needs.add("timers")
        elif block == "flight":
            callsign = _callsign(options.get("callsign"))
            if options.get("source") == "follow":
                if callsign:
                    needs.add(f"aircraft:follow:{callsign}")
            else:
                needs.add("aircraft:nearby")
        elif block == "progress":
            source = options.get("source", "day")
            callsign = _callsign(options.get("callsign"))
            if source == "timer":
                needs.add("timers")
            elif source == "flight" and callsign:
                needs.add(f"aircraft:follow:{callsign}")
        elif block == "metar":
            station = str(options.get("station") or "").strip().upper()
            if station:
                needs.add(f"metar:{station}")
        elif block in ("feed", "spark"):
            if block == "spark" and options.get("source", "temp_hourly") != "feed":
                needs.add("weather")
            elif options.get("feed_id"):
                needs.add(f"feed:{options['feed_id']}")
    return needs


def sample_context(now: datetime | None = None, elapsed: float = 0.0) -> RenderContext:
    """A context that reproduces the design previews (Fri Oct 9, 10:24)."""
    return RenderContext(now=now or datetime.fromisoformat(catalog.SAMPLE_NOW), elapsed=elapsed,
                         data=catalog.sample_data(), art=dict(catalog.BUILTIN_ART),
                         habits=dict(catalog.SAMPLE_HABITS), timers=dict(catalog.SAMPLE_TIMERS))


def ascii_preview(screen: dict, ctx: RenderContext | None = None) -> str:
    """16 lines of 32 characters ('#' lit, '.' dark) for reviewing a screen in a terminal."""
    pixels = frame(screen, ctx or sample_context())
    return "\n".join("".join("#" if any(pixels[y * 32 + x]) else "." for x in range(32))
                     for y in range(16))


if __name__ == "__main__":
    # python3 blocks.py [screen id ...]: print built-in screens with the sample data.
    import sys
    wanted = sys.argv[1:] or [s["id"] for s in catalog.BUILTIN_SCREENS]
    by_id = {s["id"]: s for s in catalog.BUILTIN_SCREENS}
    for screen_id in wanted:
        if screen_id not in by_id:
            raise SystemExit(f"Unknown screen id: {screen_id}")
        print(f"{screen_id} ({by_id[screen_id]['name']})\n{ascii_preview(by_id[screen_id])}\n")
