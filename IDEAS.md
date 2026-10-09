# Display ideas to evaluate

These began as proposals. Most shipped with the screen gallery redesign; the
**Status** column says which, and the rest are still open. The 32×16 panel is
most legible when each screen has one main fact and at most two short text
rows. Longer details can scroll, but a glance should still make sense.

| Idea | 32×16 fit | Data and setup | Status |
| --- | --- | --- | --- |
| Clock and date | Excellent | Pi system clock and chosen time zone; no API | Done: Time shelf (big, classic, analog, words, day progress, night) |
| Current weather | Good | Location, units, one weather provider, cached result | Done: Right now, Next 12 hours, Rain soon (Open-Meteo) |
| Nearby plane count and closest distance | Excellent | Existing aircraft feed and location | Done: Plane count block, Radar screen |
| Pomodoro or countdown timer | Excellent | Offline; start/pause/reset in settings | Done: Pomodoro, Countdown; timer-done interruption |
| Custom message and small pixel art | Good | Local text and optional 7×7 art | Done: Message, Pixel studio, art block |
| Airport METAR summary | Good | Nearby airport ICAO code, weather feed, observation age | Done: METAR screen and block |
| Airport wind and flight category | Good | Same METAR feed; show observed conditions | Done: METAR block fields (category, wind) |
| Sunrise, sunset, and daylight left | Good | Location, date, and time zone; calculable offline | Done: Sun arc, sunrise/sunset block |
| Aircraft spotting log | Good | Local sightings and small capped history | Open: which stats are worth keeping? |
| Followed-flight milestones | Good | Existing follow mode; extra schedule data may be incomplete | Open: which milestones are reliable enough to show? |
| Moon phase | Good | Calculable offline | Open: does it earn a lineup slot? |
| Pi health and data age | Excellent | Local temperature, network, and feed age | Done: Pi health screen; source ages in Device |
| Next calendar event | Fair | Calendar account, private tokens, title truncation | Done: Next up, from an optional private ICS link |
| Transit arrival | Fair | Local transit feed and stop choice | Done via a custom JSON feed (no GTFS-realtime) |
| Sports score | Fair | Team choice and licensed/live feed | Done via a custom JSON feed |
| ISS overhead pass | Good | Location and orbital data, refreshed periodically | Partly: current distance and direction; pass prediction needs SGP4 |
| Market price | Fair | Ticker and market feed; numbers can change quickly | Done via a custom JSON feed with sparkline |

## Still open

1. **Spotting log**: a small, capped history of aircraft seen nearby, with a
   daily count or "rarest type" screen.
2. **Followed-flight milestones**: takeoff, cruise and descent cues for a
   followed flight, if the position data is reliable enough.
3. **Moon phase**: calculable offline, like the sun.
4. **ISS pass prediction**: a countdown to the next visible pass would need
   orbital elements and an SGP4 implementation.
5. **Weather alerts**: only with a clear statement that the panel is not a
   warning channel.

For any external feed, investigate current API terms, coverage, rate limits,
and update intervals before implementation. Cache the last good result and
make its age visible; old weather, scores, or aircraft positions must not look
live. Keep personal calendars and custom messages on the Pi. Weather alerts,
if added, should not be treated as the only warning channel.

A future 64×32 panel could support four rows of text, larger aircraft art and
logos, forecast tiles, fuller METAR detail, and route graphics. The present
32×16 layout should remain a supported target.
