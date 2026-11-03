# NHL scoreboard

The **NHL scoreboard** screen uses the full native **64×32** panel for two team
logos, abbreviations, scores, shots and game status. All information stays
visible together; it does not scroll or rotate between statistics.

## Choose the screen

1. Open **New screen → Sports → NHL scoreboard**.
2. Choose **Team shown**, then save and add it to your lineup or use **Show now**.
3. To change an existing NHL screen, open **Customize → Scoreboard → Team logos**.

The selected team always appears on the left, whether it plays at home or away.
The opponent appears on the right. **SH12-9**, for example, means 12 shots for
the selected team and 9 for the opponent. Turn **Show shots** off to hide this
row. Missing scores or shots use a dash, not an invented zero. Very large shot
counts use the shorter prefix `S` so both numbers still fit.

Logos retain their team colours with the Original palette. Applying a screen
palette tints them to match the selected palette. The older **Classic** layout
remains available. Updating the app does not change saved screens, the lineup,
or the pinned screen automatically.

## Period, clock and game states

- During play, the bottom line shows the period and time remaining, such as
  **P2 17:42**. Overtime uses **OT** and a shootout uses **SHOOTOUT**.
- An explicit intermission flag from the NHL feed shows **1ST INT**, **2ND INT**,
  **3RD INT** or **OT INT**. A clock reaching zero alone does not imply a break.
- A stopped clock stays stopped. A running clock counts down locally between
  observations, then resynchronizes with the next observation. The feed is
  polled every 15 seconds during a live game, so a stoppage or goal can take
  until the next successful poll to appear.
- If a running observation is more than 30 seconds old, the clock changes to
  **P2 SYNC** (or the corresponding period) instead of continuing to guess.
  A provider error or live-data age over 90 seconds shows **STALE**, retaining
  the last successful scores and shots.
- Completed games show **FINAL**, **FINAL/OT** or **FINAL/SO**. If the game-detail
  request fails, a final score from the schedule can still be shown without
  optional shots.
- Upcoming games show **VS** and the local start day/time. The existing
  **24-hour time** setting controls this time. A team without a selected game
  uses the existing no-game display.

The adapter prefers a live game, then a final whose start was within the last
12 hours, then the next scheduled game. Upcoming games within two hours are
polled every minute; other schedules and finals every five minutes. Newly
fetched NHL observations are written to the web-preview data file promptly,
without writing it every second as the clock changes. The editor requests
fresh NHL frames once a second for a still screen and does not retain NHL
frames in the static preview cache.

## Sources and bundled artwork

Game selection uses the NHL's public [club schedule feed](https://api-web.nhle.com/v1/club-schedule/CGY/week/now),
with a season-schedule fallback. Live scores, shots and clock flags come from
the selected game's `gamecenter/{game_id}/landing` endpoint; this
[game-detail example](https://api-web.nhle.com/v1/gamecenter/2025020181/landing)
illustrates the payload structure. The adapter verifies the game ID and both
team abbreviations before accepting details.

All 32 team marks are bundled in `nhl_logos.py`, derived from the NHL's official
dark-background SVGs at
`https://assets.nhle.com/logos/nhl/svg/{TEAM}_dark.svg`, for example the
[Calgary Flames mark](https://assets.nhle.com/logos/nhl/svg/CGY_dark.svg).
Each generated entry includes its source URL and SHA-256. The marks identify
the teams; they remain the property of their respective owners.

Marks fit inside a 14×14 box while preserving their proportions. They are
stored as transparent pixel rows and a compact colour palette, so displaying
them on the Pi needs no image library or logo download. Small details are
necessarily reduced at this resolution. Unknown marks fall back to a team
abbreviation.

### Rebuild the logo module

This is a build-time operation only:

1. Fetch each official SVG using the team codes in `nhl.TEAMS`, saving it as
   `{TEAM}.svg` in a source directory.
2. Use an SVG renderer to create transparent PNGs at up to 512×512, preserving
   aspect ratio, named `{TEAM}.png` in a PNG directory.
3. With Pillow installed in the build environment, run from the repository:

   ```sh
   python3 tools/build_nhl_logos.py PNG_DIRECTORY --svg-dir SVG_DIRECTORY > nhl_logos.py
   ```

The generator crops transparent margins, fits each mark to 14×14, reduces
colours and omits near-black background pixels. Inspect the resulting marks
on black before committing. Include `--svg-dir` to record original SVG hashes;
without it the recorded hashes describe the input PNGs instead.

## Implementation and checks

- `nhl.py`: defensive schedule/detail parsing, polling intervals and status text.
- `providers.py`: background requests, game-detail enrichment and last-good data.
- `flightboard.py`: promptly persists new NHL observations for web previews.
- `blocks.py`: Classic and Team logos renderers shared by panel and previews.
- `catalog.py`: NHL options, the new built-in and the Sports shelf.
- `nhl_logos.py`: generated runtime pixels, included in `deploy-manifest.json`.
- `web/options.js`, `web/api.js`, `web/matrix.js`: conditional shots control and
  fresh live previews.

Regression coverage includes intermissions, stopped/running clocks, stale
observations, overtime/shootouts/finals, missing shots, away-team orientation,
double-digit scores, logo bounds, provider failures, prompt data persistence,
preview freshness and saved options. Run the normal project checks:

```sh
python3 -B -m unittest discover -s . -p 'test_*.py'
node --test test_web_api.mjs
sh -n install.sh
git diff --check
```
