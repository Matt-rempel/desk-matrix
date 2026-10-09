# Settings redesign: implementation plan

This plan turns the "screen gallery" design (Gallery, Customize, Build your
own, Pixel studio, Lineup, Device) into working software. The design files
are the `.dc.html` artboards in the Design canvas; their pixel layouts
(`Matrix.dc.html` renderer, the `S = {...}` screen specs in `Main.dc.html`,
`Lineup.dc.html`) are the visual reference for every built-in screen.

## Principles

1. **One renderer.** `render.py` + `blocks.py` (pure Python, no third-party
   imports) turn a screen definition into 512 RGB pixels. The display service
   uses them for the panel; the web server uses them for every preview. The
   browser never re-implements fonts or layout; it paints pixel arrays on a
   `<canvas>`. Previews therefore match the panel exactly.
2. **Everything is a screen.** Clocks, flights, weather, timers and art are
   all screens: a *layout* (slot rectangles) filled with *blocks*. Built-in
   gallery screens and user-built screens share one schema.
3. **The lineup replaces "mode".** The panel plays the active time-of-day
   *moment* (or the always-on list), unless a screen is pinned ("Show now")
   or an *interruption* fires.
4. **Stay dependency-free and private.** Standard library only. The web
   server keeps its pairing key, origin checks and strict CSP
   (`script-src 'self'; style-src 'self'`): no inline scripts or `style=""`
   attributes in HTML, no external fonts or CDNs. System font stacks
   replace Geist (`-apple-system, system-ui, sans-serif` and
   `ui-monospace, "SF Mono", Menlo, monospace`).
5. **Existing installs upgrade in place.** Old `settings.json` keeps loading;
   `library.json` is created from it on first run (see Migration).

## Module map and ownership

| File | Purpose | Wave / owner |
| --- | --- | --- |
| `render.py` | Fonts (5×7, 3×5, big = 3×5 ×2), layer rasterizer, auto-fit text, scrolling | 1 · Engine |
| `catalog.py` | Layouts, palettes, icons, block catalog metadata, built-in screens, shelves, `SAMPLE_DATA` | 1 · Engine |
| `blocks.py` | `render_screen`, `frame`, `data_needs` | 1 · Engine |
| `providers.py` | Weather, METAR, ISS, sun (offline), calendar (ICS), JSON feeds, Pi health | 1 · Providers |
| `web/` | `index.html`, `app.css`, JS files: the whole new UI | 1 · Frontend |
| `settings.py` | New device settings fields | 2 · Data/API |
| `library.py` | `library.json` schema, validation, persistence, migration, actions | 2 · Data/API |
| `web_server.py` | Static files from `web/`, new API | 2 · Data/API |
| `player.py` | Lineup scheduler, pin, timers, interruptions, transitions, motion, aircraft provider | 2 · Player |
| `flightboard.py` | Main loop drives `player.py`; status + data snapshot | 2 · Player |
| `install.sh`, units, docs | Ship new files, document sources | 3 · Integration |
| `screens.py` | Kept only for migration of legacy clock screens | 2 · Data/API |

Agents edit only the files they own. Each adds `test_<module>.py` files.
The full suite must pass: `python3 -m unittest discover -s . -p 'test_*.py'`
and `sh -n install.sh`.

## Contract 1 — layers (render.py)

`render.rasterize(layers, elapsed=0.0) -> list[tuple[int, int, int]]`
returns 512 pixels, row-major (`y * 32 + x`), black = `(0, 0, 0)`. Later
layers paint over earlier ones; anything outside 32×16 is clipped. Colors
are `"#RRGGBB"`. Layer dicts (same as the design's `Matrix.dc.html`):

| `t` | Keys |
| --- | --- |
| `text` | `s` (str, or list of candidate strings for `auto`), `f` (`big`/`5x7`/`3x5`/`auto`), `x`, `y`, `w` (default `32 - x`), `h` (optional; centers vertically), `a` (`l`/`c`/`r`, default `c`), `c` or `grad: [from, to]` (horizontal gradient), `scroll` (bool: if wider than `w`, scroll using `elapsed`, holding 2 s at each end), `clip` (bool: clip to the `x..x+w` region) |
| `icon` | `n` (icon name), `x`, `y`, optional `w`/`h` to center, `c` |
| `px` | `x`, `y`, `rows` (strings), `pal` (char → color) |
| `pts` | `p`: list of `[x, y, color]` |
| `rect` | `x`, `y`, `w`, `h`, `c` |
| `line` | `x1`, `y1`, `x2`, `y2`, `c` |
| `circle` / `arc` | `cx`, `cy`, `r`, `c`, `dotted` (arc = upper half) |
| `bar` | `x`, `y`, `w`, `h`, `v` (0–1), `c`, `bg` |
| `dots` | `x`, `y`, `n`, `size`, `gap`, `on` (list of 0/1), `c`, `off` |
| `analog` | `cx`, `cy`, `r`, `hr`, `mn`, `c` (face), `hc`, `mc` |
| `spark` | `x`, `y`, `w`, `h`, `d` (numbers), `c`, `c2` (vertical gradient), `line` (bool), `fill` |

Fonts: 5×7 glyph shapes come from the existing `FONT` table in
`flightboard.py` (moved into `render.py`); 3×5 and the punctuation additions
(`° % + > < ! ' ?`) come from the design. Glyphs are proportional (blank
columns trimmed) except digits, which stay fixed-width so clocks don't
jitter. One blank column between glyphs; a space is 2 px (5×7) or 1 px
(3×5); `big` is 3×5 scaled ×2 (10 px tall) with a 1 px gap. `auto` tries
`big`, then `5x7`, then `3x5` (skipping fonts taller than `h`) and, within
each font, each candidate string in order; the first that fits `w` wins. If
nothing fits, use `3x5` with the last candidate and `scroll`.
`render.measure(text, font) -> (width, height)` is public.

## Contract 2 — screens (catalog.py, blocks.py)

```json
{
  "id": "custom-<32 hex>" | "<builtin id>",
  "name": "Morning glance",
  "layout": "icon2",
  "slots": [{"block": "weather_icon", "color": "#FFB23F", "options": {}}],
  "style": {"palette": "ember" | null, "motion": "still"},
  "based_on": "time-big" | null
}
```

* `layout` ∈ `LAYOUTS` (rects as in the design's Builder):
  `full` [0,0,32,16]; `two` [0,0,32,7] [0,9,32,7];
  `icon2` [0,0,7,16] [8,0,24,7] [8,9,24,7]; `bigsmall` [0,0,32,10] [0,11,32,5];
  `three` [0,0,32,5] [0,6,32,5] [0,11,32,5]; `split` [0,0,15,16] [17,0,15,16].
  `len(slots)` must equal the layout's slot count.
* Slot `color: null` means "use the palette": slot 0 takes the palette's
  `primary` (a color or a 2-color gradient), other slots take `secondary`.
  With no palette and no color, white.
* `PALETTES`: `ember`, `phosphor`, `ice`, `paper`, `neon`, `night`, colors
  from the Customize artboard.
* `style.motion` ∈ `still`, `breathe`, `slide`, `sparkle` (applied by the
  player, not the renderer).

`BLOCKS` in `catalog.py`: `{id: {"name", "glyph", "category",
"options": {name: {"type": "bool|int|str|enum|date|color|art|feed",
"default", "choices"?, "min"?, "max"?, "max_len"?}}, "min_w", "min_h",
"needs": [...]}}`. Block ids:

`time` (`h24`, `colon_blink`), `date` (`style`: short/long), `weekday`,
`temp` (`which`: now/high/low/hilo), `weather_icon`, `sun_time`
(`event`: next/sunrise/sunset), `flight` (`source`: nearby/follow,
`callsign`, `field`: callsign/route/detail), `plane_count`, `countdown`
(`label`, `date`), `timer` (`work_min`, `break_min`), `text` (`text`),
`progress` (`source`: day/year/timer/flight), `spark` (`source`:
temp_hourly/feed, `feed_id`), `icon` (`name`), `art` (`art_id`), `feed`
(`feed_id`, `field`: value/label), `calendar_next` (`field`: time/title),
`metar` (`station`, `field`: station/category/wind), `iss` (`field`:
distance/direction/label), `health` (`field`: cpu/net/feed), `none`.
Panel-sized blocks: `analog_clock` (min 15×15), `fuzzy_time` (32×16),
`radar` (15×15), `sun_arc` (32×16), `hourly_graph` (16×6), `habit_week`
(`habit_id`; 28×10), `life` (any, animated), `fire` (any, animated).

`BUILTIN_SCREENS`: every gallery screen in the design, ids:
`time-big`, `time-classic`, `time-analog`, `time-words`, `time-daybar`,
`sky-nearby`, `sky-follow`, `sky-radar`, `sky-iss`, `sky-sun`,
`weather-now`, `weather-hourly`, `weather-rain`, `weather-metar`,
`focus-pomodoro`, `focus-countdown`, `focus-streak`, `focus-nextup`,
`play-message`, `play-pet`, `play-life`, `play-fire`, `play-music`,
`data-market`, `data-score`, `data-transit`, `data-health`, plus
`night-clock` (dim red classic). Each also carries `"family"`
(`clock` enables Customize's Type / Second line / Clock knobs), `"tag"`
and `"source"` labels. `SHELVES` groups them as Time, Sky, Weather, Focus,
Play, Data with the design's titles and blurbs. `LEGACY_IDS` maps
`clock-classic`→`time-classic`, `clock-simple`→(a one-row time screen),
`clock-weekday`→(time + weekday).

`blocks.render_screen(screen, ctx) -> list[layer]`,
`blocks.frame(screen, ctx) -> list[pixel]`,
`blocks.data_needs(screen) -> set[str]` with need strings `weather`,
`sun`, `iss`, `calendar`, `health`, `metar:<ICAO>`, `feed:<id>`,
`aircraft:nearby`, `aircraft:follow:<CALLSIGN>`, `timers`.

`ctx` is `blocks.RenderContext(now: aware datetime, elapsed: float seconds
since the screen appeared, data: dict, units: {"temp": "C"|"F",
"distance": "nm"|"km"}, art: {id: art}, habits: {id: [dates]},
timers: {id: timer})`. Missing data never raises: blocks show a short
placeholder (`--`, `NO DATA`, `SET UP`) in the slot color dimmed.
`catalog.SAMPLE_DATA` is a full snapshot (shape below) that reproduces the
design's previews (10:24 Fri Oct 9, 14°, WJA YYC>YVR, etc.).

## Contract 3 — data snapshot (providers.py)

```python
providers.Providers(settings, state_dir)
  .update(needs: set[str], feeds: list[dict]) -> None  # non-blocking; schedules fetches
  .snapshot() -> dict
  .close()
```

Snapshot (every key optional / may be `None`; times are ISO strings in
UTC; `age_s` is seconds since the source observation):

```
weather:  {temp_c, high_c, low_c, code: sun|cloud|rain|snow|storm|fog|moon,
           hourly_c: [12 floats], rain_in_min: int|None, observed_at, age_s}
metar:    {"CYYC": {station, category: VFR|MVFR|IFR|LIFR, wind_dir, wind_kt,
           gust_kt, observed_at, age_s}}
sun:      {sunrise, sunset, next_event: sunrise|sunset, next_at, daylight_progress}
iss:      {distance_km, bearing_deg, direction: N|NE|..., overhead: bool, updated_at}
calendar: {next: {start, title}|None, updated_at}
feeds:    {"<feed id>": {value: str, series: [float], updated_at, error}}
health:   {cpu_temp_c, net_ok, feed_age_s}
aircraft: {nearby: [{callsign, route, distance_nm, altitude_ft, icon}],
           tracked: {callsign, route, origin, destination, progress,
           remaining_min, altitude_ft, speed_kt}|None, updated_at}   # filled by player.py
```

Sources (no API keys): Open-Meteo forecast (weather, 15 min);
aviationweather.gov `api/data/metar?format=json` (10 min);
`api.wheretheiss.at/v1/satellites/25544` (30 s, only while needed; the ISS
screen shows its distance and direction now, and the interruption fires
when it is within ~1,500 km — pass prediction would need SGP4 and is out of
scope); NOAA sunrise equation computed locally; ICS calendar URL from
settings (15 min; single and non-recurring events, plus simple
`RRULE:FREQ=DAILY|WEEKLY`); user JSON feeds (`url`, dotted `path`,
optional `series_path`, `prefix`, `suffix`, `interval_s` ≥ 60). Every
fetch has a timeout, backoff after errors, keeps the last good value, and
runs off the render thread.

## Contract 4 — library.json (library.py)

Stored at `STATE_DIR/library.json` (mode 0640, atomic write like
`settings.json`).

```
{
  "version": 1,
  "screens": [screen, ...],                 # custom, max 40
  "art": [{"id": "art-<16 hex>", "name", "w", "h", "palette": ["#RRGGBB" ≤16],
           "frames": ["<w*h chars: '.' off, '0'-'9','a'-'f' palette index>" ≤8],
           "fps": 1-12}],                   # sizes 7x7, 16x16, 32x16; max 50
  "feeds": [{"id": "feed-<8 hex>", "name", "url", "path", "series_path",
             "prefix", "suffix", "interval_s"}],   # max 10
  "habits": {"<habit id>": ["YYYY-MM-DD", ...]},   # last 60 days kept
  "timers": {"<timer id>": {"state": "idle|running|paused", "phase": "work|break",
             "work_min", "break_min", "ends_at": epoch|null, "remaining_s",
             "cycles": int}},
  "lineup": {
    "always": [{"screen_id", "seconds"}],
    "moments": [{"id": "m-<8 hex>", "name", "start": "HH:MM", "end": "HH:MM",
                 "days": [0-6, Monday = 0], "brightness": 1-100|null,
                 "screens": [{"screen_id", "seconds": 5-300}]}],
    "transition": "cut|slide|dissolve|wipe",
    "interrupts": {
      "plane_overhead": {"enabled", "radius_nm", "max_alt_ft", "seconds"},
      "timer_done": {"enabled"},
      "rain_soon": {"enabled", "minutes"},
      "iss_overhead": {"enabled"}}},
  "pinned": {"screen_id", "until": epoch|null} | null
}
```

Moments may cross midnight. When several match, the first in list order
wins; when none match, `always` plays; an empty lineup shows `time-classic`.

**Migration** (no `library.json` yet): custom clock screens become screens
(1 row → `full` with the row's block; 2 rows → `two`); `lineup.always` is
`[selected clock screen]` for `mode: clock`, `[sky-nearby]` for `nearby`,
or a custom copy of `sky-follow` with `callsign = settings.flight` for
`flight`. The legacy fields stay in `settings.json` and are ignored after
migration.

## Contract 5 — settings.py additions

`temp_unit` (`C`/`F`, default `C`), `distance_unit` (`nm`/`km`, default
`nm`), `brightness_follow_lineup` (bool, true), `brightness_max` (1–100,
100), `night_palette` (bool, false: use the `night` palette during the
night hours), `calendar_ics_url` (`""` or an http(s) URL ≤ 512 chars).
Existing fields are unchanged. Effective brightness = active moment's
brightness if `brightness_follow_lineup` and it is set, else the existing
day/night logic; always capped by `brightness_max`.

## Contract 6 — HTTP API (web_server.py)

All `/api/*` routes need `X-Flightboard-Key`; POSTs keep the origin and
JSON content-type checks. Body limit rises to 64 KiB.

| Route | Result |
| --- | --- |
| `GET /`, `GET /<name>.(js\|css\|svg)` | Files from `web/` (name `[a-z0-9-]+`) |
| `GET /api/catalog` | `{layouts, palettes, blocks, icons, motions, transitions, builtins, shelves}` |
| `GET /api/library` | library.json contents (validated) |
| `POST /api/library` | One action, returns the full library: `save_screen` {screen} (no/empty id → new `custom-…` id), `delete_screen` {screen_id}, `save_art` {art}, `delete_art` {art_id}, `save_feed` {feed}, `delete_feed` {feed_id}, `save_lineup` {lineup}, `show_now` {screen_id, seconds?}, `unpin` {}, `timer` {timer_id, op: start/pause/resume/reset/skip, work_min?, break_min?}, `habit` {habit_id, date, done} |
| `POST /api/preview` | `{"screens": [screen…] (≤40), "elapsed"?: s}` → `{"frames": ["<3072 hex chars>", …]}`. Uses `STATE_DIR/data.json` when fresh (< 30 min) and `SAMPLE_DATA` for anything missing |
| `GET /api/settings`, `POST /api/settings`, `POST /api/display` | As today, plus Contract 5 fields |
| `GET /api/status` | As today plus `frame` (3072 hex), `screen_id`, `screen_name`, `moment`, `pinned`, `data_age` |

A frame string is 512 pixels × `RRGGBB`, row-major, lowercase hex.

## Contract 7 — player (player.py, flightboard.py)

`player.Player(library: dict, settings, now_fn=time.time)` with
`tick(now_monotonic, data) -> (pixels, info)`. It resolves the playlist
(pin → interrupts → active moment → always), advances by each item's
`seconds`, applies the lineup transition (cut, slide 0.4 s, dissolve 0.5 s
per-pixel blend, wipe 0.6 s in a fixed pseudo-random pixel order) and the
screen's motion (breathe 70–100 % sine over 4 s, slide-in 0.4 s, sparkle:
a few lit pixels brighten briefly). Timers advance phases and raise
`timer_done`. Interruptions: plane within radius and below altitude (once
per callsign per hour), timer done (flash the panel three times), rain
within N minutes (once per hour), ISS overhead (once per pass). `info` =
`{screen_id, screen_name, moment, pinned, needs}`.

`flightboard.py` keeps the hardware setup and flight/ADS-B fetch helpers
(existing tests keep passing), wraps them in an aircraft provider that
fills `snapshot["aircraft"]` when `aircraft:*` is needed, reloads
`settings.json`/`library.json` on mtime change, renders ~20 fps, writes
`status.json` (with `frame`) every 2 s and `data.json` (the snapshot)
every 30 s, and applies `effective_brightness`. `--once` keeps working.

## Contract 8 — frontend (web/)

Hash routes: `#/` Gallery, `#/customize/<screen id>`, `#/build[/<id>]`,
`#/draw[/<art id>]`, `#/lineup`, `#/device`, with the pairing view when no
key is stored (key in `sessionStorage`, as today). A `<canvas>` matrix
component draws a 3072-hex frame with LED dots, optional glow, and a
`pitch` (design sizes: 10 hero, 4.25 thumbnails, 2.5 lineup). Previews are
batched through `/api/preview` and debounced (150 ms) while editing; the
gallery hero polls `/api/status` every 2 s and shows the live `frame`.
Visual system from the design: background `#0B0B0C`, surfaces `#151517` /
`#1C1C1F`, lines `#2A2A2E`, text `#F4F2EE`, muted `#A3A19B`, accent
`#FFB23F`, 44 px minimum touch targets, real buttons/inputs/labels,
visible focus, works at 320 px wide and scales up to a centered column on
desktop. No inline styles in HTML (CSP); set dynamic styles through the
CSSOM or classes.

## Waves

1. **Parallel:** Engine (render/catalog/blocks), Providers, Frontend
   (against Contracts 2, 6 and 8 with a throwaway mock server).
2. **Parallel:** Data/API (settings, library, web_server, migration) and
   Player (player.py, flightboard.py).
3. **Integration:** run the real web server with a fake `rgbmatrix`, drive
   the UI in Chromium, fix contract mismatches, update `install.sh` (ship
   `web/` and new modules, back up and restore them), README, IDEAS and
   CONTRIBUTING, then commit and push.

## Out of scope

ISS pass prediction (needs SGP4), GTFS-realtime protobuf transit feeds
(use a JSON feed), full RFC 5545 recurrence, streaming-service
integrations for "Now playing" (use a JSON feed, e.g. from a home
automation server).
