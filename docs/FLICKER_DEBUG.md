# Debug flicker

Compare software settings on the physical matrix, particularly random pixels or
rows flashing. Open **Device → Display diagnostics → Open flicker tests**.
The Pi schedules the run; closing your phone or browser does not stop it.

This mode tests hypotheses. It does not claim to detect or fix physical flashes.
The web preview shows intended pixels, so a clean preview cannot prove that the
physical panel is clean. [Research and primary sources](FLICKER_RESEARCH.md)
explain the stock Bonnet's software pulse limitation and later hardware options.

## A useful first comparison

1. Select **Current baseline**, **GPIO slowdown 5**, and **PWM depth 9 bits**.
   Deselect other profiles for this first run. The default selection instead
   uses baseline, GPIO slowdown 3, and PWM depth 9.
2. Choose the screen where flashing is easiest to see, a moving clock such as
   Clockwork or Tracker, and **Sharp white text**. Keep the same sources across
   all profiles. Using individual screens avoids lineup schedules or alerts
   changing the comparison.
3. Set **1 hour**, **15 minutes per profile**, **1 minute per screen**, and
   **20% fixed brightness**. Test brightness is limited to 1–50% and also obeys
   your normal device brightness ceiling. The power switch still turns the
   display off.
4. Start the run. Wait until the page names the applied profile instead of
   “Applying the next profile…”. Driver changes require a display-service
   restart, usually around 10–30 seconds. Outstanding provider requests can
   extend this; the estimate is not a deadline.
5. Watch the physical panel. Use **No flashes seen**, **Better**, **Same**, or
   **Worse**, and record details: screen, row/color, rough frequency, and whether
   it happens during movement. Notes attach to the profile and actual screen
   acknowledged by the display, rather than a queued next profile.
6. Download the JSON report before starting another run. Use **Stop and restore
   normal** to end early, or let the run expire automatically.

Profiles run in the listed order and repeat. Each starts the same ordered screen
sequence. Run time and profile dwell use wall-clock time, including restart
downtime. Choose enough time for all profiles and screens; the API rejects plans
that cannot cover every selected profile once or every selected screen within a
profile. With a single selected profile, it stays applied continuously for the
whole run, without periodic driver restarts. Runs last 5 minutes–24 hours; the
web form offers 30 minutes–24 hours.

Normal settings, lineup, saved screens and pins are not rewritten. An individual
screen is selected only in an in-memory trial player. After a run, the normal
player resumes with its existing schedules and pins. Changes made separately in
other app pages during a run still save normally.

## Available software profiles

Every candidate starts from the actual normal driver settings. Driver presets
change just the named control; selecting several profiles does not combine them.
Controls unavailable in the installed Python binding are disabled.

| Profile | What it isolates | Tradeoff / interpretation |
| --- | --- | --- |
| Current baseline | Normal driver settings, 20 FPS app rendering | Reference for the same screens and fixed trial brightness |
| GPIO slowdown 3, 4, 5, 8 | Data/clock timing margin | Slower edges can help panel settling; may reduce refresh speed |
| PWM depth 9, 7, 5 bits | Color precision and refresh work | Fewer color levels; faint gradient colors may disappear |
| Longer PWM pulse 180, 240, 300 ns | Shortest PWM timing interval | More settling time, potentially lower refresh speed |
| Dither 1 or 2 bits | Temporal handling of low PWM bits | Changes fine-color behavior; compare gradients carefully |
| Refresh cap 120 or 200 Hz | More regular refresh pacing | Experimental upper bound; ineffective if actual refresh is already slower |
| App rendering 10, 5, 1 FPS | Python rendering load | Animations become slower; hardware scanning continues independently |
| Pause live-data polling | New provider/network work | Uses cached data; web access, Tailscale and health reporting remain active |
| Freeze each rendered screen | Drawing and framebuffer changes | Holds the first rendered frame for each screen visit; hardware scanning continues |

Four static diagnostic patterns are also available: sharp white text, RGB bars,
grayscale ramp, and checkerboard. Select up to 12 sources, including saved screens,
built-ins, or **Current lineup**.

**Current lineup** retains its normal scheduling and alerts; it is less controlled
than individual screens. Freeze + Current lineup holds whichever screen it first
renders until the selected source changes or the profile restarts. Freeze holds
each individual screen's first frame on each visit, rather than freezing time
globally. Pausing live-data polling prevents new requests; it does not cancel an
already running request. Cached data can be old. Preview requests and other web
activity can still create work, so leave the browser closed for a separate
comparison if browser load is suspected.

Mapping, pulse wiring, audio modules, CPU governor, kernel configuration and
network connections remain unchanged. In particular, the mode does not enable
hardware PWM on an unmodified Bonnet. The installed binding has no
`disable_busy_waiting` option. Continuous raw driver refresh-rate logging is
omitted because it can flood the service journal during long runs.

## What the report means

- **Applied settings:** actual driver options at process launch, alongside the
  normal baseline and requested plan. During a restart the last acknowledgement
  can lag the requested profile; the page shows that transition.
- **Render time:** Python time spent producing/checking the intended frame.
  A frozen frame usually has negligible render work after its first sample.
- **Paint time:** writing changed pixels to the back buffer. Its mean divides by
  the number of swaps, not all loop iterations.
- **Swap wait:** time inside `SwapOnVSync`; not a hardware refresh measurement.
  Frames are swapped only when pixels or brightness change.
- **Software errors:** exceptions caught in screen rendering. This does not count
  visible hardware glitches. CPU temperature, current undervoltage and current
  throttling flags provide supporting context when the Pi reports them.
- **App FPS limit:** the selected Python rendering limit, not achieved FPS and
  not panel refresh Hz. A refresh cap is only a configured maximum.
- **Observations:** manual ratings and notes linked to run/profile/screen/step.

Reports keep whole-run aggregates for every profile × selected source, plus the
latest 160 detailed timing records. Detailed records distinguish actual screens;
the Current lineup aggregate groups its screens under that selected source.
Current-run notes retain the latest 200 entries. Eight previous run summaries
are kept, each with its plan, last metrics and last 20 notes. Full timing
aggregates are for the current run; download before starting the next run if you
want a lasting comparison. Timing rows are flushed to disk at profile exit;
the active process supplies its current rows between exits. A sudden power loss
can lose those in-memory rows, though the saved run schedule survives.

## Implementation and recovery

The paired same-origin endpoints are `GET /api/flicker` and `POST /api/flicker`.
POST accepts a validated `start`, `stop`, or `note` action. There is no arbitrary
command, path, GPIO mapping, or privileged-service-control endpoint.

Trial files live under `/var/lib/flightboard`:

| File | Purpose |
| --- | --- |
| `flicker.json` | Current plan, observations and bounded history |
| `flicker-live.json` | Driver acknowledgement, heartbeat, current timings and health |
| `flicker-measurements.json` | Recent detailed rows and full current-run aggregates |
| `flicker-attempt.json` | Startup retry marker for failed candidate recovery |
| `flicker.lock` | Serializes plan and observation changes |

Start, profile boundaries, Stop and expiry cause the display loop to clear the
panel and exit with code 75 when a driver target changes. The existing
`flightboard.service` uses `Restart=on-failure` and `RestartSec=10`, relaunching the
fixed root command. It applies only whitelisted trial controls, then the matrix
library drops privileges as before. Normal command-line options and the Bonnet
systemd override remain the baseline. No extra privileged helper is installed.

If the same candidate target starts twice within 120 seconds, the trial is
blocked and the next attempt uses the normal baseline. This covers an RGBMatrix
initialization failure or early process failure; it also treats a quick manual
service restart as an interrupted trial. Stop remains available if a profile is
merely visually worse. A hung driver that never returns cannot be recovered by
this loop; use normal SSH/systemd recovery if necessary.

Automatic runs require a fresh heartbeat from the updated display service under
systemd. Running the renderer directly from a terminal does not advertise restart
support. To inspect recovery over SSH:

```sh
systemctl status flightboard.service flightboard-web.service
journalctl -u flightboard.service -n 50 --no-pager
```

Tests cover scheduling, expiry, screen loops, continuous single-profile runs,
failed-candidate fallback, option isolation, report retention, frozen rendering,
paused polling, authentication/origin checks, and preserving saved settings and
library. Physical signal quality still needs a person watching the panel.
