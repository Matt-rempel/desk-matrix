# Desk Matrix

Desk Matrix turns a Raspberry Pi and a 32×16 HUB75 RGB matrix into a
configurable desk display. Everything it shows is a *screen*: clocks, nearby
and followed flights, weather, METAR, the sun and the ISS, timers, habits,
messages, pixel art and numbers from your own JSON feeds. A private HTTPS
settings page on your phone or computer lets you pick screens from a gallery,
customize them, build your own, draw pixel art, and plan which screens play
at each time of day.

The application files and Linux services still use the `flightboard` name so
existing installations can update without moving settings or changing units.

The first installation uses WinSport in Calgary as a sample location. **Change
the location and time zone in settings for your own desk.**

## Hardware

- Raspberry Pi 3 Model B, tested with Raspberry Pi OS Lite 64-bit
- One 32×16 HUB75 RGB matrix, wired with the driver's
  [`regular` GPIO mapping](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md)
- A separate **5 V, at least 2.5 A** micro-USB supply for the Pi
- A separate, correctly polarized 5 V supply sized for the LED panel
- A common ground through the HUB75 signal connector
- MicroSD card and a network connection for the Pi

Check the panel's input connector, GPIO wiring, and power polarity with the
power disconnected. The install script assumes one 32×16 panel and the
`regular` mapping; it does not detect or correct wiring. Use a HUB75 adapter
board if you want a simpler and sturdier connection than individual jumpers.
The Pi and panel must each have adequate power; do not power the matrix from
the Pi's GPIO header.

## Install on a new Pi

1. Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash
   Raspberry Pi OS Lite 64-bit. In Imager's customization screen, set a unique
   username and password, Wi-Fi or Ethernet, and enable SSH. Choose a login
   name other than `flightboard` so the web service cannot read your GitHub
   credentials or edit your checkout. Boot the Pi and connect the separately
   powered matrix.
2. Sign in to the Pi over SSH. Get the public repository's clone URL from
   GitHub's **Code** button, and run:

   ```sh
   sudo apt-get update
   sudo apt-get install -y git
   git clone 'https://github.com/Matt-rempel/desk-matrix.git'
   cd desk-matrix
   sh install.sh
   ```

   Cloning a public repo does not require a GitHub login. The Pi user needs
   `sudo`; the installer asks for that password in the Pi terminal.
   It installs build packages, compiles a pinned version of
   [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix), creates
   a dedicated `flightboard` service account if needed, and installs the
   display and settings services at boot. The driver build can take several
   minutes on a Pi 3.
3. The installer guides you through signing the Pi in to
   [Tailscale](https://tailscale.com/docs/install/linux) and enabling private
   HTTPS with Tailscale Serve. Open any approval link it prints in your own
   browser. If sign-in or approval is still pending when the script exits,
   finish it and run `sh install.sh` again.
4. Install Tailscale on the phone or computer that will control the board and
   sign in to the **same tailnet**. Open the private HTTPS pairing link printed
   at the end of installation. The settings page also accepts the pairing key
   pasted into its form. Keep the key and link out of screenshots and chat.
5. Under **Device**, set your **short location label, latitude, longitude,
   and IANA time zone**. For example, Calgary uses `America/Edmonton`.
   Adjust brightness for your panel and power supply.

The web backend listens only on `127.0.0.1:8765` on the Pi. Tailscale Serve
provides the HTTPS address to devices allowed by your tailnet. No router port
forwarding or Tailscale Funnel is needed. Tailscale's HTTPS certificate makes
the Pi's Tailscale DNS name visible in public certificate records; the page
itself remains private to the tailnet. Publishing the source repository does
not publish your Pi's saved settings or pairing key.

### Add the settings page to your Home Screen

On iPhone, connect to Tailscale, open the Pi's HTTPS settings address in
**Safari**, then use **Share → Add to Home Screen**. Name it **Desk Matrix**
and add it. On Android, open the same address in Chrome and choose
**Install app** (or **Add to Home screen**) from the browser menu.

The installed app has its own pairing session, so enter the key in it if
prompted. Keep Tailscale connected to change settings; when the Pi cannot
be reached, the app shows a retry page. The offline page caches no settings,
flight data, or pairing key.

### Update

On the Pi, from the repository checkout:

```sh
git pull --ff-only
sh install.sh
```

The installer preserves `/var/lib/flightboard` (settings, your screens and
lineup in `library.json`, and the pairing key). It reuses an existing matrix
driver environment and restarts the two services after checking imports. If
an update fails while switching services, it restores the previous
application files, `web/` directory and units. The full private pairing
link is shown again after a successful update. To suppress it in a captured
terminal log, run `sh install.sh --no-pairing-link`.

**Upgrading from the mode-based version:** nothing to do by hand. On first
start, your settings are migrated into `library.json`: custom clock screens
become screens in **Your screens**, and the old mode becomes the lineup
(clock → that clock screen, nearby → *Nearby flight*, follow → a *Follow*
copy with your flight number). Location, colors, brightness and night hours
carry over; the old mode fields stay in `settings.json` but are no longer
used. The previous settings page files in `/opt/flightboard` are removed.

### Troubleshooting

```sh
systemctl status flightboard.service flightboard-web.service
journalctl -u flightboard.service -n 50 --no-pager
tailscale serve status
```

To retrieve a lost pairing key **on the Pi**, use
`sudo cat /var/lib/flightboard/web-token`. The key is stored in a file
readable only by the service account and root. The webpage keeps it only in
the current browser tab's session storage.

For smoother matrix timing, disable onboard audio with
`dtparam=audio=off` in `/boot/firmware/config.txt`, then reboot. The display
falls back to software pulse timing when the Pi's sound module is loaded, so
this is optional. The matrix driver's README describes this hardware limit.

## What the display shows

The settings page has three tabs.

**Screens** opens on a live copy of the panel, then a gallery of built-in
screens grouped into shelves:

| Shelf | Screens |
| --- | --- |
| Time | Big digits, Classic, Analog, In words, Day progress, Night clock |
| Sky | Nearby flight, Follow a flight, Radar, ISS, Sun arc |
| Weather | Right now, Next 12 hours, Rain soon, METAR |
| Focus | Pomodoro, Countdown, Habit streak, Next up (calendar) |
| Play | Message, Pixel pet, Life, Ember, Now playing |
| Data | Market, Score, Transit, Pi health |

Previews are rendered on the Pi by the same code that drives the panel, so
what you see is what the LEDs show. **Customize** changes a screen's palette,
clock style, second line, options and motion, then **Show now** pins it to the
panel until you return to the lineup, or **Add to lineup** keeps it in
rotation. Pomodoro timers start, pause and reset from the phone; habit
screens take a tap for **Done today**. **Build your own** combines one of six
layouts with blocks (time, date, temperature, flight, countdown, text, feed
value, sparkline, pixel art and more). The **Pixel studio** draws 7×7 icons,
16×16 sprites or full-panel art with up to eight animation frames, ready to
use in a screen. **Planes nearby** lists aircraft in range with a **Follow**
button whenever a flight screen is playing.

**Lineup** plans the day. Each *time of day* (for example Morning, 07:00–
09:00 on weekdays) has its own screens, durations and optional brightness;
**Any other time** plays when none match. Moments may cross midnight; the
first match in the list wins. Screens change with a cut, slide, dissolve or
pixel wipe. *Interruptions* break in for a plane overhead (radius, altitude
and duration are adjustable), a finished timer, rain starting soon, or the
ISS passing within about 1,500 km. *Pi alerts* break in when the Pi itself
needs attention: CPU at or above a chosen temperature (75 °C by default),
under-voltage or throttling reported by the Pi firmware, no internet for a
chosen number of minutes (checked with a TCP connection to 1.1.1.1 every
minute, only while that alert is on), or the SD card nearly full. Each
repeats while the problem lasts and re-arms once it clears.

**Device** holds location and time zone, flight radius and rotation, units
(°C/°F, nm/km), brightness (follow the lineup, a maximum, night dimming and
an optional Night red look), the calendar link, custom JSON feeds, and the
display power switch. Off blanks the LEDs immediately while the Pi and page
stay available; it survives a restart and does not cut power to the Pi or
panel. Changes apply without restarting.

Nearby flight shows the closest aircraft and cycles through a few more with
callsign, route, airline, type, distance, altitude and speed when known.
Follow a flight shows route progress when both airports and a recent position
are known: an approximation along a great-circle route, **not an arrival
estimate**. Some flight numbers need the exact ADS-B callsign, such as
`ACA150`. Missing data never blanks a screen: it shows a short placeholder
such as `--` or `NO DATA`.

## Data and limits

Sources need no API keys, run off the display thread with timeouts, keep the
last good value and back off after errors. The page shows each source's age.

- **Aircraft:** positions from [adsb.fi](https://adsb.fi/) through its
  [open data API](https://github.com/adsbfi/opendata) (personal,
  non-commercial use, one request per second; Desk Matrix spaces requests at
  least 1.1 s apart and refreshes about every 20 s). Route, airline and type
  from the [ADSBdb public API](https://github.com/mrjackwills/adsbdb), one
  lookup at a time and cached. Coverage depends on receivers; routes may be
  missing or wrong. This is not an authoritative arrivals board.
- **Weather:** [Open-Meteo](https://open-meteo.com/) forecast for your
  location every 15 minutes. Weather data by Open-Meteo.com, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **METAR:** NOAA [aviationweather.gov](https://aviationweather.gov/) data
  API every 10 minutes for the airport you enter, with observation age.
- **ISS:** [wheretheiss.at](https://wheretheiss.at/) every 30 s, only while
  an ISS screen or interruption needs it.
- **Sun:** sunrise and sunset are calculated on the Pi; no network.
- **Calendar (optional):** a private ICS link, fetched every 15 minutes and
  kept on the Pi. Single events, all-day events and simple daily or weekly
  repeats are understood; complex recurrence rules are not.
- **Custom JSON feeds (optional, up to 10):** any http(s) URL, a dotted path
  to the value (and optionally to a number series), prefix, suffix, and a
  refresh interval of at least 60 s.

Known limits: the ISS screen shows the station's current distance and
direction, not predicted passes. Transit arrivals, sports scores, market
prices and *Now playing* come from your own JSON feeds (for example from a
home-automation server); there are no built-in services for them. Weather
alerts are not shown, and the display is not a safety warning channel.

## Development

Run tests on a computer with Python 3.11+ (the matrix driver is imported only
when starting the hardware display). Everything uses the standard library:

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

Run `python3 flightboard.py --once` on the Pi to test the aircraft feed without
using GPIO, and `python3 blocks.py time-classic` to print a screen as ASCII. See [IDEAS.md](IDEAS.md) for proposed display modes and
[CONTRIBUTING.md](CONTRIBUTING.md) for the shared Git workflow.
