# NHL scoreboard

The **NHL scoreboard** screen uses the full native **64×32** panel for two team
logos, abbreviations, scores, shots and game status. All information stays
visible together; it does not scroll or rotate between statistics.

## Choose the screen

1. Open **New screen → Sports → NHL scoreboard**.
2. Open **Teams to follow**, search or browse the team list, select one or more
   teams, then tap **Done**. Save the screen and add it to your lineup or use
   **Show now**.
3. Existing NHL screens use the same logo scoreboard automatically. Open
   **Customize** to change their teams, colours or shots setting.

The selected team always appears on the left, whether it plays at home or away.
The opponent appears on the right. **SH12-9**, for example, means 12 shots for
the selected team and 9 for the opponent. Turn **Show shots** off to hide this
row. Missing scores or shots use a dash, not an invented zero. Very large shot
counts use the shorter prefix `S` so both numbers still fit.

With multiple teams, live games take priority. If none are live, recently
finished games take priority over upcoming games. Games at the same priority
rotate every 10 seconds of screen time. Rotation resumes across short lineup
visits rather than repeatedly starting with the first team. When two selected
teams play each other, that matchup appears once, with the earlier selected
team on the left. Close the picker to cancel; **Done** requires at least one
team. Teams can be found by full name or abbreviation.

Logos retain their team colours with the Original palette. Applying a screen
palette tints them to match the selected palette. The old text-only Classic
layout has been removed. Existing screens render with logos, including screens
saved with no layout option or `display: classic`. Their team selections,
colours, shots setting and lineup/pin references are retained. The old
`data-score` ID is a hidden compatibility entry that renders the new scoreboard;
it is not offered as another gallery template.

## Live alerts

Open **Lineup → Live alerts → NHL games live**. Enable the alert and open
**Teams to follow** to select multiple teams using the same picker as Customize.
Tap **Done**, then **Save lineup** to apply the alert settings.

- **Brief alerts** shows the appropriate game at puck drop and whenever its
  score changes. If several games change while another alert is showing, the
  pending game observations are checked in selection order after it finishes.
  A shared matchup is not alerted twice. Changes to the same game during its
  alert remain visible and can trigger another brief alert afterward.
- **Follow live games** keeps scoreboards on the display while any selected
  game is live, rotating between unique games, including intermissions. Games
  leave the rotation when finished, stale or unavailable. The normal lineup
  resumes when no selected game is live. Existing timer/device alert priorities
  and Show now pins are respected.
- Alerts always use the full **Team logos** layout, including alert settings
  saved before it was introduced. The saved screen itself is not rewritten.
  **Scoreboard appearance** optionally selects an NHL screen whose colours and
  shots setting the alert should use. It lists **Default scoreboard** and unique
  saved appearances; identical looks are combined even when the screens follow
  different teams. Saved choices are labelled with their name and team codes,
  with a variant number only if distinct looks would otherwise share a label.
  Choosing another appearance preserves the currently followed teams.

Screen and alert team lists can be configured independently. Until an alert
has an explicit team list, it inherits the teams from its selected appearance
screen; old single-team screens retain their original team. An empty stored
list is the backwards-compatible inheritance value, not an empty selection
offered by the picker. Explicit lists accept up to all 32 teams, without
duplicates or unknown team codes.

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
- `nhl.py`, `player.py`: followed-team selection, unique-game rotation and
  multi-game alert bookkeeping.
- `providers.py`: background requests, game-detail enrichment and last-good data.
- `flightboard.py`: promptly persists new NHL observations for web previews.
- `blocks.py`: the single logo scoreboard renderer shared by panel and previews.
- `catalog.py`: NHL options, the new built-in and the Sports shelf.
- `nhl_logos.py`: generated runtime pixels, included in `deploy-manifest.json`.
- `web/options.js`, `web/api.js`, `web/matrix.js`: conditional shots control and
  fresh live previews.
- `web/nhl-teams.js`: shared searchable picker with bundled team marks; used by
  Customize and Lineup live alerts.
- `web/nhl-appearance.js`: groups equivalent saved appearances for live alerts.

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
