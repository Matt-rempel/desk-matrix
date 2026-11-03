# Flicker investigation: software options and controlled trials

Research and read-only driver capability check: **3 November 2026**.

This investigation concerns random pixels or rows flashing **when viewed directly**, not just dark bands in a phone photo. The current setup is one native 64 × 32 HUB75 panel on a Raspberry Pi with an Adafruit single-output RGB Matrix Bonnet.

## What we know about this installation

The parent agent read the service configuration: `--panel-scale 2 --mapping adafruit-hat --software-pulse --gpio-slowdown 2`. The CPU governor was already `performance`; `vcgencmd get_throttled` reported `0x0`; onboard `snd_bcm2835` was loaded. These are observations at the time of the investigation, not guarantees about future operation.

Read-only inspection instantiated **RGBMatrixOptions only**, not RGBMatrix, so it did not initialize GPIO or interrupt the display. Installed Python properties were:

| Property | Available? | Library default; service overrides may differ |
| --- | --- | --- |
| `pwm_bits` | Yes | 11 |
| `pwm_lsb_nanoseconds` | Yes | 130 |
| `pwm_dither_bits` | Yes | 0 |
| `limit_refresh_rate_hz` | Yes | 0, unlimited |
| `show_refresh_rate` | Yes | false |
| `scan_mode` | Yes | 0, progressive |
| `gpio_slowdown` | Yes | 1; current service explicitly uses 2 |
| `disable_hardware_pulsing` | Yes | false; current service explicitly uses true |
| `limit_refresh_rate` | **No** | Wrong Python property name for this installation |
| `disable_busy_waiting` | **No** | Exists upstream in C++, but absent from the installed Python binding |

The application already paints an offscreen canvas and uses `SwapOnVSync`; adding double buffering is therefore not a new remedy. The current `--refresh` argument controls provider polling in **seconds**. It is neither the application frame rate nor the panel's hardware refresh frequency. These facts were checked in local `flightboard.py`.

## The known Bonnet timing limitation

The stock single-output Bonnet cannot use the driver's hardware pulse path with its default wiring. Adafruit distinguishes its software-timed convenience mode from the hardware-timed quality configuration. The latter requires a GPIO4–GPIO18 connection and disabling conflicting onboard audio. Therefore **changing a mapping flag alone is not a software-only repair**. Keep the current mapping and software-pulse mode during software trials. Hardware pulse mode remains a later option after confirming the required physical modification. [Adafruit Bonnet guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi?view=all)

A separate issue is data-edge timing: random colored pixels can result from marginal GPIO signals. The current Adafruit installer recommends trying slowdown 5 on Pi 3/4 when solid white flickers, then reducing it for speed. That supports testing 3, 4 and 5 despite earlier short trials being inconclusive. It does not promise a cure. [Adafruit installer source](https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/blob/main/rgb-matrix.py)

## Restart-only driver experiments

These are test candidates, not claims that every setting improves this panel. Retain native geometry, mapping, pulse mode and brightness while changing one timing dimension at a time. Constructing a matrix applies its initialization options; restarting only the display service is the predictable way to compare complete profiles.

| Experiment | Proposed values | What it tests / tradeoff | Priority |
| --- | --- | --- | --- |
| Slower GPIO | 2 baseline, then 3, 4, 5 | More time for data edges to settle; may reduce refresh speed. | High for random pixels/rows |
| Lower PWM depth | 11 baseline, then 9, 7, 5 | Shortens the refresh workload; reduces gradient and dim-color fidelity. | High |
| Longer base pulse | 130 ns baseline, then 180, 240, 300 | High-contrast ghosting and short-pulse tolerance; can lower refresh rate. | High/medium |
| Temporal dithering | 0 baseline, then 1, 2 | Redistributes low-bit contributions across refreshes; evaluate dim gradients and shimmer. | Medium |
| Refresh-rate cap | 0 baseline; experimental 200 and 120 Hz | Consistency under load, rather than peak speed. Calibrate against actual minimum refresh if measured. | Medium |
| Shorter base pulse | 100 ns; later 75 or 50 | Refresh-speed probe; can worsen ghosting or color accuracy. | Later |
| Interlaced scan | `scan_mode=1` versus 0 | A low-refresh alternative; can introduce combing. | Later, advanced |
| Reduced brightness | Several moderate levels below the current ceiling | Sensitivity to output intensity; also changes visibility and pulse distribution, so compare carefully. | Diagnostic |

The parameter names, ranges and command-line equivalents are documented in the [driver options parser](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/lib/options-initialize.cc): `--led-pwm-bits`, `--led-pwm-lsb-nanoseconds`, `--led-pwm-dither-bits`, `--led-limit-refresh`, `--led-scan-mode`, and `--led-slowdown-gpio`. Current upstream accepts PWM depths 1–11, base pulses 50–3000 ns and dither values 0–2. Those are driver ranges, **not** a recommendation to expose the entire range as ordinary web controls.

Refresh capping addresses variable refresh periods; a cap that is too low can itself become visibly flickery. A 120 Hz preset is an experiment, not a universal preferred rate. The upstream README recommends choosing a cap using observed minimum refresh under representative load. Low PWM depth can make dim colors disappear, so test a bright monochrome pattern alongside real screens. [Upstream refresh and PWM guidance](https://github.com/hzeller/rpi-rgb-led-matrix#changing-parameters-via-command-line-flags)

### Busy-waiting caveat

Upstream C++ has `disable_busy_waiting`, but it only changes behavior when a nonzero refresh cap is active. A sleep-wait trial must be compared with the **same cap** using busy waiting; uncapped sleep-wait is a no-op. This installed Python binding does not expose that property, so omit or clearly disable that trial rather than pretending it took effect. [Refresh loop implementation](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/lib/led-matrix.cc)

## Application experiments that isolate load

These are engineering inferences from this app's rendering pipeline. They can separate a busy renderer from continuous panel-driving problems; they do not guarantee a hardware refresh improvement.

1. **Application FPS:** compare 20, 10, 5 and 1 FPS with the same screen. Name this metric app FPS, not panel Hz.
2. **Freeze one rendered frame:** render once, then bypass subsequent screen rendering. Merely skipping identical swaps while still recalculating each frame does not isolate renderer CPU cost.
3. **Pause provider requests:** suppress flight/weather/NHL fetch work while displaying held data. Keep Tailscale, SSH and the web connection available.
4. **Animation off versus on:** compare settled and moving versions of the same screen.
5. **Simple versus expensive screens:** a plain clock, Tracker, Clockwork, NHL logos and gradient-heavy art provide different CPU and color workloads.
6. **Monochrome versus gradients:** this tests low-bit shimmer separately from scene complexity.
7. **No transition versus slide/breathe/sparkle:** isolates whole-screen animation and pixel updates.
8. **Longer status/data write intervals or reduced diagnostic logging:** useful if flicker follows storage bursts; avoid uncontrolled filesystem logging during the measurement itself.
9. **Caching/precomputed frame playback:** a later optimization if a frozen frame is markedly cleaner than generating the same visual live. First measure render and paint durations.
10. **More efficient canvas upload:** a later implementation comparison against the current per-pixel upload, retaining offscreen drawing and synchronized swaps.

The driver explicitly supports offscreen frame canvases and recommends synchronized buffer swaps to avoid tearing. Do not replace the existing buffering with direct writes to the active matrix. [Canvas API contract](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/include/led-matrix.h)

## System-level software options for later investigation

| Option | How to evaluate | Activation / limitation |
| --- | --- | --- |
| Real-time refresh scheduling | Inspect startup warnings and `/proc/<pid>/task/*/sched`; verify the refresh thread actually obtains FIFO scheduling. | Diagnostic first. Do not simply make the entire Python app FIFO99. |
| Refresh-thread CPU affinity | Inspect per-thread CPU masks. Steer competing web/provider work away from the refresh core if needed. | Preserve the driver's core choice; whole-process CPU masks can inadvertently exclude it. |
| Reserve a refresh core | Inspect existing boot arguments first; consider CPU isolation and interrupt/RCU placement. | Boot-file change and reboot; prepare an explicit rollback. |
| CPU governor | Check available governors and compare `performance` with the current policy only if useful. | Runtime sysfs setting; this Pi already uses performance. Restore the old policy after a trial. |
| Thermal/power throttling | Log temperature, actual ARM clock and `get_throttled`; correlate changes with trials. | Observation first; software cannot establish the voltage at the panel. |
| Background GUI/services | Test a headless/minimal workload; identify conflicting GPIO daemons and 1-Wire overlays. | Stop only identified optional services; preserve remote access. |
| Onboard audio conflict | Record module state. Disable onboard audio before any future hardware-pulse configuration. | Usually boot configuration / blacklist plus reboot. Audio-off alone does not add the Bonnet's missing PWM connection. |
| Overclock removal | Inspect boot settings; return an overclocked machine to its stock operating point before chasing timing. | Reboot; do not substitute overclocking for diagnosis. |
| Driver version comparison | Record the installed version/source commit; compare pinned builds with a rollback and binding capability check. | Restart/rebuild. Avoid a blind latest-version upgrade during an A/B trial. |
| Optimized kernel | Upstream provides an optimized-kernel guide covering CPU/interrupt isolation and kernel configuration. | Later manual project, not a one-click web preset. Back up and verify OS/kernel compatibility. |

The refresh-thread implementation requests **SCHED_FIFO priority 99** and affinity to core 3, so broad scheduling changes can interfere with an existing optimization. [Driver thread setup](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/lib/thread.cc), [refresh-thread launch](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/lib/led-matrix.cc)

Linux's performance governor requests the highest permitted frequency; it does not bypass thermal or power constraints. It can increase power use and heat. [Linux CPU frequency documentation](https://docs.kernel.org/admin-guide/pm/cpufreq.html) The Pi documentation distinguishes requested frequency from actual ARM clock and documents throttling. [Raspberry Pi frequency and thermal controls](https://www.raspberrypi.com/documentation/computers/config_txt.html)

Upstream documents boot-time core isolation and a newer optimized-kernel route. The kernel guide explicitly says a real-time kernel was not necessary for its improvements. Its `idle=poll`, forced turbo and broad system changes have costs and should be tested separately, with rollback, rather than bundled into the initial dashboard. [Optimized-kernel guide](https://github.com/hzeller/rpi-rgb-led-matrix/tree/master/optimized-kernel)

## Trial protocol and measurement limits

Suggested sequence: normal baseline → individual driver timing trials → lower app FPS / provider pause / frozen frame → repeat the most promising timing profile → later system changes if necessary. Run a baseline again between candidates; do not infer causation from different screens at different brightness levels.

Use a fixed screen dwell, fixed brightness and a selected sequence of real screens. Include black, bright RGB patches, sharp white text, checkerboards and gray gradients. Full-white content is a useful worst-case diagnostic, but keep it at a chosen moderate brightness rather than automatically raising output to 100%.

A useful session record includes profile values actually applied, selected screen IDs, start/end times, dwell, brightness, app render/paint timing, CPU/temperature/throttle observations, error/restart events and human notes. Record “not yet assessed” separately from “no flicker observed.” A Better/Same/Worse judgment and symptom description are more honest than an invented automatic flicker score.

Hardware refresh counters, app FPS and successful API previews do **not** prove the physical display is clean. Phone-camera banding can also be a shutter/scan interaction rather than the random artifacts reported here. Observe the panel directly and repeat comparisons for minutes or hours.

Long sessions should continue without an open browser tab, retain bounded history and have an expiry that restores the baseline configuration. Store temporary trial state separately from the user's saved screens and lineup. Make Stop/Restore baseline available even if a candidate cannot initialize; never launch two GPIO-driving processes together. These are requirements for controlled experiments, not additional claimed cures.

## What not to vary indiscriminately

Keep panel geometry, chain count, row addressing, panel chipset initialization, RGB order and pixel mapping fixed while the image is otherwise correctly arranged. These settings solve configuration mismatches, not ordinary timing jitter. Consider them only if there is stable row scrambling, wrong geometry/colors, or evidence for a different panel driver. Likewise, 5 V supply health, cable integrity and the Bonnet's PWM modification remain physical questions that software trials cannot conclusively resolve.
