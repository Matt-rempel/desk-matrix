"""Lineup player: pin, moments, interruptions, timers, transitions and motion.

`Player.tick(now_monotonic, data)` returns the 512 pixels to show and a small
`info` dict. The player reads `library.json` contents (Contract 4) and
settings but never writes either; timer phases are computed from `ends_at`
at render time. Standard library only.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import blocks
import catalog
import library
from settings import is_night
from render import BLACK, HEIGHT, WIDTH, jround, mix, parse_color

PIXELS = WIDTH * HEIGHT
FALLBACK_SCREEN = "time-classic"
DEFAULT_SECONDS = 10
MIN_SECONDS, MAX_SECONDS = 3, 3600
TRANSITION_S = {"cut": 0.0, "slide": 0.4, "dissolve": 0.5, "wipe": 0.6}
SLIDE_IN_S = 0.4
BREATHE_PERIOD_S = 4.0
SPARKLE_STEP_S = 0.15
SPARKLE_COUNT = 3
SOON_S = 120  # needs() also covers a moment that starts within this many seconds
PLANE_REPEAT_S = 3600
RAIN_REPEAT_S = 3600
RAIN_SHOW_S = 10
ISS_SHOW_S = 15
FLASH_HALF_S = 0.25  # timer_done: three on/off flashes
FLASH_COUNT = 3
TIMER_SHOW_S = 5
TIMER_LATE_S = 120  # a phase that ended longer ago (e.g. while powered off) does not flash
INTERRUPT_NEEDS = {"plane_overhead": {"aircraft:nearby"}, "rain_soon": {"weather"},
                   "iss_overhead": {"iss"}, "timer_done": set(), "pi_hot": {"health"},
                   "pi_power": {"health"}, "disk_low": {"health"}, "offline": {"net"}}
# Pi alerts: (screen, repeat while the problem lasts, seconds on the panel)
ALERT_SHOW_S = 10
ALERT_REPEAT_S = {"pi_hot": 600, "pi_power": 1800, "offline": 3600, "disk_low": 6 * 3600}
ALERT_SCREENS = {"pi_hot": "sys-hot", "pi_power": "sys-power", "offline": "sys-offline",
                 "disk_low": "sys-disk"}
HOT_CLEAR_C = 5  # a hot alert re-arms once the Pi is this far below the threshold
DISK_CLEAR_PCT = 2
INTERRUPT_DEFAULTS = library.INTERRUPT_DEFAULTS
WIPE_ORDER = tuple(random.Random(0x5EED).sample(range(PIXELS), PIXELS))
WHITE = (255, 255, 255)


# --- library helpers ---------------------------------------------------------------

def resolve_screen(library: dict, screen_id) -> dict | None:
    """Custom screen, then built-in, then legacy alias; None when unknown."""
    if not isinstance(screen_id, str):
        return None
    for screen in (library or {}).get("screens") or ():
        if isinstance(screen, dict) and screen.get("id") == screen_id:
            return screen
    if screen_id in catalog.BUILTINS:
        return catalog.BUILTINS[screen_id]
    legacy = catalog.LEGACY_IDS.get(screen_id)
    return catalog.BUILTINS.get(legacy) if legacy else None


def _minutes(value) -> int | None:
    try:
        hours, minutes = str(value).split(":")
        hours, minutes = int(hours), int(minutes)
    except (TypeError, ValueError):
        return None
    return hours * 60 + minutes if 0 <= hours < 24 and 0 <= minutes < 60 else None


def in_window(start, end, local: datetime, days=None) -> bool:
    """True when local time is within start..end (HH:MM, may cross midnight).

    `days` (Monday = 0) names the day a window starts on, so a 22:00-06:00
    window on Friday also covers early Saturday. None means every day;
    start == end means the whole day.
    """
    first, last = _minutes(start), _minutes(end)
    if first is None or last is None:
        return False
    allowed = set(range(7)) if days is None else {d for d in days if isinstance(d, int)}
    current, weekday = local.hour * 60 + local.minute, local.weekday()
    if first == last:
        return weekday in allowed
    if first < last:
        return first <= current < last and weekday in allowed
    return ((current >= first and weekday in allowed)
            or (current < last and (weekday - 1) % 7 in allowed))


def active_moment(lineup: dict, local: datetime) -> dict | None:
    for moment in lineup.get("moments") or ():
        if isinstance(moment, dict) and in_window(moment.get("start"), moment.get("end"),
                                                  local, moment.get("days")):
            return moment
    return None


def _seconds(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return DEFAULT_SECONDS
    return max(MIN_SECONDS, min(MAX_SECONDS, float(value)))


def timer_at(timer: dict, now: float) -> tuple[dict, float | None]:
    """The timer as it stands at `now` and, if a phase has ended, when the latest one ended.

    Phases roll work -> break -> work via `library.advance_timer`.
    """
    current = dict(timer) if isinstance(timer, dict) else {}
    ends = current.get("ends_at")
    if (current.get("state") != "running" or isinstance(ends, bool)
            or not isinstance(ends, (int, float))):
        return current, None
    try:
        current = library.advance_timer(current, now)
        if ends > now:
            return current, None
        minutes = current["work_min"] if current["phase"] == "work" else current["break_min"]
        return current, float(current["ends_at"] - minutes * 60)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return dict(timer), None


# --- pixel effects -------------------------------------------------------------------

def _scale(pixel, factor: float):
    return tuple(jround(c * factor) for c in pixel)


def apply_motion(pixels: list, motion: str, elapsed: float) -> list:
    """Screen motion: breathe (70-100 % over 4 s), slide in (0.4 s), sparkle."""
    if motion == "breathe":
        factor = 0.85 + 0.15 * math.sin(2 * math.pi * elapsed / BREATHE_PERIOD_S)
        return [_scale(p, factor) if p != BLACK else BLACK for p in pixels]
    if motion == "slide" and elapsed < SLIDE_IN_S:
        progress = max(0.0, elapsed) / SLIDE_IN_S
        offset = jround((1 - (1 - (1 - progress) ** 2)) * WIDTH)  # ease-out from the right
        if offset <= 0:
            return pixels
        out = [BLACK] * PIXELS
        for y in range(HEIGHT):
            row = y * WIDTH
            for x in range(offset, WIDTH):
                out[row + x] = pixels[row + x - offset]
        return out
    if motion == "sparkle":
        lit = [i for i, p in enumerate(pixels) if p != BLACK]
        if not lit:
            return pixels
        step = int(elapsed // SPARKLE_STEP_S)
        phase = (elapsed % SPARKLE_STEP_S) / SPARKLE_STEP_S
        strength = 0.75 * (1 - abs(2 * phase - 1))
        if strength <= 0:
            return pixels
        out = list(pixels)
        rng = random.Random(step * 7919 + 17)
        for index in rng.sample(lit, min(SPARKLE_COUNT, len(lit))):
            out[index] = mix(out[index], WHITE, strength)
        return out
    return pixels


def blend(old: list, new: list, kind: str, progress: float) -> list:
    """One frame of a lineup transition from `old` to `new` (progress 0..1)."""
    if progress >= 1 or kind not in TRANSITION_S or kind == "cut":
        return new
    progress = max(0.0, progress)
    if kind == "slide":  # old slides out to the left while new follows it in
        offset = jround(progress * WIDTH)
        out = [BLACK] * PIXELS
        for y in range(HEIGHT):
            row = y * WIDTH
            for x in range(WIDTH):
                source = x + offset
                out[row + x] = old[row + source] if source < WIDTH else new[row + source - WIDTH]
        return out
    if kind == "dissolve":
        return [a if a == b else mix(a, b, progress) for a, b in zip(old, new)]
    out = list(old)  # wipe: a fixed pseudo-random pixel order
    for index in WIPE_ORDER[:jround(progress * PIXELS)]:
        out[index] = new[index]
    return out


# --- player ---------------------------------------------------------------------------

class Player:
    """Plays the lineup: pinned screen, interruptions, the active moment, or always."""

    def __init__(self, library: dict, settings, now_fn=time.time):
        self._now = now_fn
        self.library: dict = {}
        self.settings = settings
        self._zone_name = None
        self._zone = timezone.utc
        # lineup position
        self._play_key = None
        self._play_items: list[tuple[str, float]] = []
        self._play_index = 0
        self._play_started = 0.0
        self._play_paused = False
        # what is on the panel
        self._shown_key = None
        self._screen_started = 0.0
        self._last_pixels: list | None = None
        self._from_pixels: list | None = None
        self._transition_started = 0.0
        self._transition_kind = "cut"
        # interruptions
        self._interrupt: dict | None = None
        self._plane_fired: dict[str, float] = {}
        self._rain_fired: float | None = None
        self._iss_overhead = False
        self._timer_seen: set[tuple[str, float]] = set()
        self._alert_fired: dict[str, float] = {}
        self.set_library(library)

    # -- inputs ----------------------------------------------------------------
    def set_library(self, library: dict) -> None:
        self.library = library if isinstance(library, dict) else {}

    def set_settings(self, settings) -> None:
        self.settings = settings

    # -- time ----------------------------------------------------------------------
    def _local(self, now: float) -> datetime:
        name = self.settings.timezone
        if name != self._zone_name:
            try:
                self._zone = ZoneInfo(name)
            except (ValueError, ZoneInfoNotFoundError):
                self._zone = timezone.utc
            self._zone_name = name
        return datetime.fromtimestamp(now, self._zone)

    def night_palette(self, local: datetime) -> bool:
        return self.settings.night_palette and is_night(self.settings, local)

    # -- playlist --------------------------------------------------------------------
    @property
    def _lineup(self) -> dict:
        lineup = self.library.get("lineup")
        return lineup if isinstance(lineup, dict) else {}

    def _items(self, entries) -> list[tuple[str, float]]:
        items = []
        for entry in entries or ():
            if isinstance(entry, dict) and resolve_screen(self.library, entry.get("screen_id")):
                items.append((entry["screen_id"], _seconds(entry.get("seconds"))))
        return items

    def _playlist(self, local: datetime) -> tuple[dict | None, tuple, list[tuple[str, float]]]:
        """(active moment, playlist key, items) for a local time."""
        moment = active_moment(self._lineup, local)
        if moment is not None:
            items = self._items(moment.get("screens"))
            if items:
                return moment, ("moment", moment.get("id"), moment.get("name")), items
        items = self._items(self._lineup.get("always"))
        if items:
            return moment, ("always",), items
        return moment, ("fallback",), [(FALLBACK_SCREEN, DEFAULT_SECONDS)]

    def _pin(self, now: float) -> str | None:
        pinned = self.library.get("pinned")
        if not isinstance(pinned, dict):
            return None
        until = pinned.get("until")
        if isinstance(until, (int, float)) and not isinstance(until, bool) and until <= now:
            return None
        screen_id = pinned.get("screen_id")
        return screen_id if resolve_screen(self.library, screen_id) else None

    def _interrupt_config(self, name: str) -> dict | None:
        interrupts = self._lineup.get("interrupts")
        config = interrupts.get(name) if isinstance(interrupts, dict) else None
        if not isinstance(config, dict) or not config.get("enabled"):
            return None
        return {**INTERRUPT_DEFAULTS.get(name, {}), **config}

    def needs(self) -> set[str]:
        """Data needs for what is on now or may play soon, plus enabled interruptions."""
        now = self._now()
        local = self._local(now)
        screen_ids = {sid for sid, _ in self._playlist(local)[2]}
        screen_ids |= {sid for sid, _ in self._playlist(self._local(now + SOON_S))[2]}
        pinned = self._pin(now)
        if pinned:
            screen_ids.add(pinned)
        result: set[str] = set()
        for screen_id in screen_ids:
            screen = resolve_screen(self.library, screen_id)
            if screen:
                result |= blocks.data_needs(screen)
        if self._interrupt:
            result |= blocks.data_needs(self._interrupt["screen"])
        for name, needs in INTERRUPT_NEEDS.items():
            if self._interrupt_config(name):
                result |= needs
        return result

    # -- interruptions ---------------------------------------------------------------
    def _start_interrupt(self, mono: float, name: str, screen_id: str, seconds: float,
                         flash: float = 0.0, focus: dict | None = None) -> None:
        screen = resolve_screen(self.library, screen_id) or catalog.BUILTINS[FALLBACK_SCREEN]
        self._interrupt = {"name": name, "screen_id": screen.get("id", screen_id),
                           "screen": screen, "started": mono, "flash_until": mono + flash,
                           "until": mono + flash + seconds, "focus": focus}

    def _check_interrupts(self, mono: float, now: float, data: dict, pinned: bool) -> None:
        if self._interrupt and mono >= self._interrupt["until"]:
            self._interrupt = None
        # timer_done preempts any other interruption; its bookkeeping runs even when off
        done = None
        for timer_id, timer in self._timers_raw().items():
            ended = timer_at(timer, now)[1]
            if ended is not None and (timer_id, ended) not in self._timer_seen:
                self._timer_seen.add((timer_id, ended))
                if now - ended <= TIMER_LATE_S:
                    done = timer_id
        self._timer_seen = {key for key in self._timer_seen if now - key[1] < 86400}
        iss = data.get("iss") if isinstance(data.get("iss"), dict) else None
        iss_new_pass = False
        if iss is not None:
            overhead = bool(iss.get("overhead"))
            iss_new_pass = overhead and not self._iss_overhead
            self._iss_overhead = overhead
        if pinned:
            return
        if done and self._interrupt_config("timer_done"):
            self._start_interrupt(mono, "timer_done", done, TIMER_SHOW_S,
                                  flash=FLASH_COUNT * 2 * FLASH_HALF_S)
            return
        if self._interrupt:
            return
        if self._check_alerts(mono, data):
            return
        config = self._interrupt_config("plane_overhead")
        aircraft = data.get("aircraft") if isinstance(data.get("aircraft"), dict) else {}
        if config:
            self._plane_fired = {cs: t for cs, t in self._plane_fired.items()
                                 if mono - t < PLANE_REPEAT_S}
            for plane in aircraft.get("nearby") or ():
                if not isinstance(plane, dict):
                    continue
                callsign = str(plane.get("callsign") or "").strip().upper()
                distance, altitude = plane.get("distance_nm"), plane.get("altitude_ft")
                if (callsign and callsign not in self._plane_fired
                        and isinstance(distance, (int, float)) and distance <= config["radius_nm"]
                        and isinstance(altitude, (int, float)) and altitude <= config["max_alt_ft"]):
                    self._plane_fired[callsign] = mono
                    self._start_interrupt(mono, "plane_overhead", "sky-nearby",
                                          _seconds(config.get("seconds")), focus=dict(plane))
                    return
        config = self._interrupt_config("rain_soon")
        weather = data.get("weather") if isinstance(data.get("weather"), dict) else {}
        rain = weather.get("rain_in_min")
        if (config and isinstance(rain, (int, float)) and not isinstance(rain, bool)
                and 0 <= rain <= config["minutes"]
                and (self._rain_fired is None or mono - self._rain_fired >= RAIN_REPEAT_S)):
            self._rain_fired = mono
            self._start_interrupt(mono, "rain_soon", "weather-rain", RAIN_SHOW_S)
            return
        if iss_new_pass and self._interrupt_config("iss_overhead"):
            self._start_interrupt(mono, "iss_overhead", "sky-iss", ISS_SHOW_S)

    def _alert_states(self, data: dict) -> dict[str, bool | None]:
        """Each Pi alert: True (problem), False (clear, re-arm) or None (keep waiting)."""
        health = data.get("health") if isinstance(data.get("health"), dict) else {}
        states: dict[str, bool | None] = {}
        config = self._interrupt_config("pi_hot")
        temp = health.get("cpu_temp_c")
        if config and isinstance(temp, (int, float)):
            states["pi_hot"] = (True if temp >= config["threshold_c"]
                                else False if temp <= config["threshold_c"] - HOT_CLEAR_C else None)
        if self._interrupt_config("pi_power") and health.get("under_voltage") is not None:
            states["pi_power"] = bool(health.get("under_voltage") or health.get("throttled"))
        config = self._interrupt_config("offline")
        offline = health.get("offline_s")
        if config and isinstance(offline, (int, float)):
            states["offline"] = (True if offline >= config["minutes"] * 60
                                 else False if offline == 0 else None)
        config = self._interrupt_config("disk_low")
        free = health.get("disk_free_pct")
        if config and isinstance(free, (int, float)):
            states["disk_low"] = (True if free < config["percent"]
                                  else False if free >= config["percent"] + DISK_CLEAR_PCT else None)
        return states

    def _check_alerts(self, mono: float, data: dict) -> bool:
        for name, problem in self._alert_states(data).items():
            if problem is False:
                self._alert_fired.pop(name, None)
            elif problem:
                fired = self._alert_fired.get(name)
                if fired is None or mono - fired >= ALERT_REPEAT_S[name]:
                    self._alert_fired[name] = mono
                    self._start_interrupt(mono, name, ALERT_SCREENS[name], ALERT_SHOW_S)
                    return True
        return False

    # -- rendering inputs ------------------------------------------------------------
    def _timers_raw(self) -> dict:
        timers = self.library.get("timers")
        return {k: v for k, v in timers.items() if isinstance(v, dict)} if isinstance(timers, dict) else {}

    def _context(self, local: datetime, now: float, elapsed: float, data: dict) -> blocks.RenderContext:
        art = dict(catalog.BUILTIN_ART)
        for item in self.library.get("art") or ():
            if isinstance(item, dict) and item.get("id"):
                art[item["id"]] = item
        habits = self.library.get("habits")
        return blocks.RenderContext(
            now=local, elapsed=elapsed, data=data,
            units={"temp": self.settings.temp_unit, "distance": self.settings.distance_unit},
            art=art, habits=habits if isinstance(habits, dict) else {},
            timers={k: timer_at(v, now)[0] for k, v in self._timers_raw().items()})

    def _screen_data(self, screen: dict, data: dict) -> dict:
        """Point aircraft data at the plane an interruption or follow screen is about."""
        aircraft = data.get("aircraft")
        if not isinstance(aircraft, dict):
            return data
        interrupt = self._interrupt
        if interrupt and interrupt["name"] == "plane_overhead" and screen is interrupt["screen"]:
            focus = interrupt["focus"]
            current = next((p for p in aircraft.get("nearby") or () if isinstance(p, dict)
                            and p.get("callsign") == focus.get("callsign")), focus)
            return {**data, "aircraft": {**aircraft, "nearby": [current]}}
        follow = aircraft.get("follow")
        if isinstance(follow, dict) and follow:
            for need in sorted(blocks.data_needs(screen)):
                if need.startswith("aircraft:follow:") and need[16:] in follow:
                    return {**data, "aircraft": {**aircraft, "tracked": follow[need[16:]]}}
        return data

    # -- main entry point -------------------------------------------------------------
    def tick(self, now_monotonic: float, data: dict | None) -> tuple[list, dict]:
        mono = float(now_monotonic)
        data = data if isinstance(data, dict) else {}
        now = self._now()
        local = self._local(now)
        pinned_id = self._pin(now)
        self._check_interrupts(mono, now, data, pinned_id is not None)
        moment, key, items = self._playlist(local)

        # Lineup position: restart on a new playlist, hold while overridden.
        if key != self._play_key:
            self._play_key, self._play_index, self._play_started = key, 0, mono
        elif items != self._play_items:
            old = self._play_items[self._play_index] if self._play_index < len(self._play_items) else None
            self._play_index %= len(items)
            if items[self._play_index][0] != (old or ("",))[0]:
                self._play_started = mono
        self._play_items = items
        overridden = pinned_id is not None or self._interrupt is not None
        if overridden:
            self._play_paused = True
        else:
            if self._play_paused:
                self._play_paused, self._play_started = False, mono
            if len(items) > 1:
                while mono - self._play_started >= items[self._play_index][1]:
                    self._play_started += items[self._play_index][1]
                    self._play_index = (self._play_index + 1) % len(items)
                    if mono - self._play_started > MAX_SECONDS:
                        self._play_started = mono
                        break

        # What is on the panel.
        interrupt = None if pinned_id else self._interrupt
        flashing = False
        if pinned_id:
            screen_id = pinned_id
            screen = resolve_screen(self.library, pinned_id)
            shown_key = ("pin", pinned_id)
        elif interrupt:
            screen, screen_id = interrupt["screen"], interrupt["screen_id"]
            flashing = mono < interrupt["flash_until"]
            shown_key = ("interrupt", interrupt["started"], flashing)
        else:
            screen_id = items[self._play_index][0]
            screen = resolve_screen(self.library, screen_id)
            shown_key = ("lineup", key, self._play_index, screen_id)
        if shown_key != self._shown_key:
            previous = self._shown_key
            first = previous is None
            after_flash = bool(previous) and previous[0] == "interrupt" and previous[2]
            self._shown_key = shown_key
            self._screen_started = mono
            # Flashes cut in and out; everything else uses the lineup transition.
            kind = self._lineup.get("transition", "cut")
            if first or flashing or after_flash:
                kind = "cut"
            self._transition_kind = kind if kind in TRANSITION_S else "cut"
            self._from_pixels = self._last_pixels
            self._transition_started = mono

        elapsed = max(0.0, mono - self._screen_started)
        night = self.night_palette(local)
        if flashing:
            pixels = self._flash(screen, mono - interrupt["started"], night)
        else:
            ctx = self._context(local, now, elapsed, self._screen_data(screen, data))
            pixels = blocks.frame(screen, ctx, "night" if night else None)
            style = screen.get("style") if isinstance(screen.get("style"), dict) else {}
            pixels = apply_motion(pixels, style.get("motion") or "still", elapsed)
            duration = TRANSITION_S.get(self._transition_kind, 0.0)
            if self._from_pixels is not None and duration and mono - self._transition_started < duration:
                pixels = blend(self._from_pixels, pixels, self._transition_kind,
                               (mono - self._transition_started) / duration)
        self._last_pixels = pixels
        brightness = moment.get("brightness") if moment else None
        info = {"screen_id": screen_id, "screen_name": str(screen.get("name") or screen_id),
                "moment": (moment.get("name") or None) if moment else None,
                "pinned": pinned_id is not None,
                "pin": ({"screen_id": pinned_id, "until": self.library["pinned"].get("until")}
                        if pinned_id else None),
                "interrupt": interrupt["name"] if interrupt else None,
                "moment_brightness": (brightness if isinstance(brightness, int)
                                      and not isinstance(brightness, bool) else None)}
        return pixels, info

    def _flash(self, screen: dict, since: float, night: bool) -> list:
        """Whole panel on/off three times in the timer's color."""
        if int(since // FLASH_HALF_S) % 2:
            return [BLACK] * PIXELS
        color = "#FFB23F"
        slots = screen.get("slots") or ()
        first = slots[0].get("color") if slots and isinstance(slots[0], dict) else None
        if isinstance(first, (list, tuple)) and first:
            first = first[0]
        if isinstance(first, str) and blocks.COLOR_RE.fullmatch(first):
            color = first
        if night:
            color = catalog.PALETTES["night"]["primary"]
        return [parse_color(color)] * PIXELS
