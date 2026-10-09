# Display ideas to evaluate

These are proposals, not committed features. The 32×16 panel is most legible
when each screen has one main fact and at most two short text rows. Longer
details can scroll, but a glance should still make sense.

| Idea | 32×16 fit | Data and setup | First question to settle |
| --- | --- | --- | --- |
| Clock and date | Excellent | Pi system clock and chosen time zone; no API | Show continuously or between flight screens? |
| Current weather | Good | Location, units, one weather provider, cached result | Temperature only, or conditions and high/low too? |
| Nearby plane count and closest distance | Excellent | Existing aircraft feed and location | A separate screen or a flight screen footer? |
| Pomodoro or countdown timer | Excellent | Offline; start/pause/reset in settings | Does a timer interrupt the flight rotation? |
| Custom message and small pixel art | Good | Local text and optional 7×7 art | Should it be a pinned screen or scheduled? |
| Airport METAR summary | Good | Nearby airport ICAO code, weather feed, observation age | Which two METAR facts matter most? |
| Airport wind and flight category | Good | Same METAR feed; show observed conditions | Use a simple wind arrow or text? |
| Sunrise, sunset, and daylight left | Good | Location, date, and time zone; calculable offline | One daily screen or evening countdown? |
| Aircraft spotting log | Good | Local sightings and small capped history | Which stats are worth keeping? |
| Followed-flight milestones | Good | Existing follow mode; extra schedule data may be incomplete | Which milestones are reliable enough to show? |
| Moon phase | Good | Calculable offline | Does it earn a rotation slot? |
| Pi health and data age | Excellent | Local temperature, network, and feed age | Always show on trouble, or only on request? |
| Next calendar event | Fair | Calendar account, private tokens, title truncation | Is the setup worth the privacy cost? |
| Transit arrival | Fair | Local transit feed and stop choice | Is the stop data accurate enough? |
| Sports score | Fair | Team choice and licensed/live feed | Which league and update frequency? |
| ISS overhead pass | Good | Location and orbital data, refreshed periodically | Would a countdown be useful? |
| Market price | Fair | Ticker and market feed; numbers can change quickly | Is this useful on a desk display? |

## Suggested first round

1. **Clock/date**: useful every day, fully offline, and an easy test of a
   general screen rotation.
2. **Weather now**: a strong desk companion once we select a source and decide
   how to show stale data.
3. **Aircraft count/closest**: uses the feed already in Flightboard.
4. **Timer**: local and private, with controls in the settings page.
5. **Compact METAR**: especially fitting for an aviation display; show the
   observation time and avoid squeezing a full report onto the panel.

For any external feed, investigate current API terms, coverage, rate limits,
and update intervals before implementation. Cache the last good result and
make its age visible; old weather, scores, or aircraft positions must not look
live. Keep personal calendars and custom messages on the Pi. Weather alerts,
if added, should not be treated as the only warning channel.

A future 64×32 panel could support four rows of text, larger aircraft art and
logos, forecast tiles, fuller METAR detail, and route graphics. The present
32×16 layout should remain a supported target.
