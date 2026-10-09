# Desk Matrix

Desk Matrix turns a Raspberry Pi and a 32×16 HUB75 RGB matrix into a
configurable desk display. It currently shows a clock and date, cycles through
nearby aircraft, or follows one flight. Clock screens can use one centered
5×7 text row or two rows; long details scroll across the panel. A private
HTTPS settings page lets you change modes, location, colors, brightness, and
screen timing from a phone or computer.

The application files and Linux services still use the `flightboard` name so
existing installations can update without moving settings or changing units.
The control page also shows weather and timer concepts as planned screens;
they are not active modes yet.

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
5. Set your **short location label, latitude, longitude, and IANA time zone**
   on the settings page. For example, Calgary uses `America/Edmonton`.
   Adjust brightness for your panel and power supply.

The web backend listens only on `127.0.0.1:8765` on the Pi. Tailscale Serve
provides the HTTPS address to devices allowed by your tailnet. No router port
forwarding or Tailscale Funnel is needed. Tailscale's HTTPS certificate makes
the Pi's Tailscale DNS name visible in public certificate records; the page
itself remains private to the tailnet. Publishing the source repository does
not publish your Pi's saved settings or pairing key.

### Update

On the Pi, from the repository checkout:

```sh
git pull --ff-only
sh install.sh
```

The installer preserves `/var/lib/flightboard/settings.json` and the pairing
key. It reuses an existing matrix driver environment and restarts the two
services after checking imports. If an update fails while switching services,
it restores the previous application files and units. The full private pairing
link is shown again after a successful update. To suppress it in a captured
terminal log, run `sh install.sh --no-pairing-link`.

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

Nearby mode shows the nearest aircraft and up to two more with airline-style
callsigns, filling unused slots with the next closest planes. Each selected
plane gets a callsign/route view and a detail view with airline, aircraft
type, distance, approximate altitude, and ground speed. Missing details fall
back to live callsign and position data. Small dots show which plane is being
displayed. Tiny 7×7 aircraft or airline-inspired marks can be enabled; they
are deliberately simple because this panel cannot render full logos clearly.

Follow mode looks for a specific flight and shows route progress when both
airport coordinates and a recent aircraft position are available. This is an
approximation along a great-circle route, **not an arrival estimate**. Some
flight numbers may need the exact ADS-B callsign, such as `ACA150`. If the
flight is not broadcasting a recent position or the feed lacks coverage, the
display shows `WAITING`.

Clock mode starts with three built-in screens: clock and date, time only, and
time with weekday. Select a preset under **Clock screen library**, or choose
**Clone & edit** to save a custom screen. Each custom screen has a name, one
or two rows, and an independent color and content choice (time, date, or
weekday) for each row. Built-ins stay available as starting points. Time uses
24-hour format; date includes abbreviated weekday, month, and day. The clock
uses the configured time zone and does not request flight data while selected.
Up to 20 custom screens are saved on the Pi with the rest of the settings.

The settings page controls nearby/follow/clock mode, location and radius,
number of planes, screen time, colors, icons, day brightness, and optional night dimming
in the configured time zone. Its **Turn display off/on** button blanks or
restores the LEDs immediately while the Pi and web page stay available. The
choice survives a restart; off does not disconnect electrical power from the
Pi or panel. Other settings changes are applied without restarting.

## Data and limits

Live aircraft positions come from [adsb.fi](https://adsb.fi/) through its
[open data API](https://github.com/adsbfi/opendata). Its public API is for
personal, non-commercial use and allows one request per second. Desk Matrix
spaces nearby and global callsign requests at least 1.1 seconds apart and
refreshes positions about every 20 seconds by default. Coverage and
callsigns depend on available receivers. This is an aircraft position display,
not an authoritative airport arrival or departure board.

Route, airline, and aircraft details come from the
[ADSBdb public API](https://github.com/mrjackwills/adsbdb). Lookups run one at
a time and are cached. Routes may be absent or inaccurate. The display uses
position data when metadata is missing and clears stale aircraft rather than
showing them indefinitely.

## Development

Run tests on a computer with Python 3.11+ (the matrix driver is imported only
when starting the hardware display):

```sh
python3 -m unittest discover -s . -p 'test_*.py'
```

Run `python3 flightboard.py --once` on the Pi to test the aircraft feed without
using GPIO. See [IDEAS.md](IDEAS.md) for proposed display modes and
[CONTRIBUTING.md](CONTRIBUTING.md) for the shared Git workflow.
