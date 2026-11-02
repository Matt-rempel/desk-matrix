# Following a flight

In a flight screen, select **Source → Follow one**, then enter the flight number
including its airline code: `WS2231`, `AC150`, or the aircraft's transmitted
callsign such as `WJA2231`. Case, spaces and hyphens are normalized.

Tap **Check flight** before saving. It reports the callsign searched and whether
the live feed has a position. The check does not change the matrix, pin a screen,
or save edits. After saving, tap **Show now** to display the flight.

**Show → Callsign / Route / Details** chooses the top line of a full-panel flight
card. The other fields remain below it, with the airline logo and followed-flight
progress bar retained. Details shows estimated time remaining for a followed
flight, or distance and altitude for nearby flights. In smaller layout slots,
Show selects the single field displayed. Previews and the matrix use this same
selection.

The app asks [adsb.fi](https://github.com/adsbfi/opendata) for live positions,
globally for a followed flight, independently of the nearby-flight radius.
[ADSBdb](https://github.com/mrjackwills/adsbdb) translates passenger flight numbers
to ICAO callsigns when it knows them, and supplies route metadata.
These are separate services: a known route does not establish a live position.

Regional and codeshare flights can transmit a different operating-airline
callsign. For example, Plane Finder lists `DL4113` as `SKW4113`, while ADSBdb
returned `DAL4113` during diagnosis. Use the operating callsign from the tracker's
aircraft details when the normal flight number fails. We do not guess an operator
from a flight number: unrelated airlines can use the same number.

Our receiver network may not see a flight that another tracker sees. Scheduled,
landed, out-of-coverage or no-longer-transmitting flights can have no live
position. The current parser requires a valid position seen within 30 seconds.
No live signal is not a cancellation or arrival status. Commercial trackers may
have different data sources; this app does not query Plane Finder.

## Lookup states

- **Check flight:** this draft has not been checked.
- **Looking:** a lookup is running.
- **No signal:** the latest successful lookup returned no usable live position.
- **Feed error:** the network request failed; this is not proof the flight is absent.

The phone's check queues one temporary flight in `flight-check.json` for up to
two minutes. The matrix process handles it through the existing background
aircraft provider, including the 1.1-second spacing between adsb.fi requests.
Flight checks refresh on the normal 20-second provider cadence. The phone polls
the local status every second while checking, without making external requests.
Checks require the matrix service to be running, even when its display is off.
One draft check is active at a time; checking a different draft replaces it.

Status snapshots include each followed flight's lookup state and resolved
callsign. Editor previews select their own result from the follow map, and read
the two-second status snapshot so they do not wait for the 30-second data export.
Follow-flight thumbnails are not cached in the browser as permanent frames.
