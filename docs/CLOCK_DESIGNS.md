# Clock and calendar collection

In **Screens → New screen → Time**, choose a design, customize it, save it to Your screens, then use Show now or add it to a lineup. Existing clock templates remain available. Installing this collection does not change a saved screen or add anything to a lineup automatically.

These designs use the entire native **64 × 32** display. Their typography and geometry are composed for each design rather than controlled by the older clock's font/size and second-line settings.

| Concept | Screen | What it shows |
| --- | --- | --- |
| A | Platform | Two split-flap plates for hours and minutes, colon and optional date footer. Changed plates briefly collapse and open at the new minute. |
| C | Station | Railway-style analog dial, digital time, weekday and date. Optional seconds hand. |
| D | Time Stack | Large block hours at the top left and minutes at the bottom right, with date in the open corner. |
| E | Orbit | Concentric hour, minute and second rings beside readable digital time and date. The hour ring always follows the familiar 12-hour dial, even with a 24-hour numeric readout. |
| G | Minute Track | Large digital time, a fixed pointer, and a minute ruler that slides into position each minute. |
| H | Clockwork | Twenty-four miniature dials arrange their hands into four numerals; the changed numeral briefly rotates its hands at each minute. |
| I | Perpetual Card | Weekday calendar tab, large day number, digital time and month. |
| J | Week Strip | Digital time above the current Monday–Sunday week, with today's date highlighted. Adjacent dates can cross a month or year boundary. |
| K | Month Map | Large day number, month/year and a Monday-first month grid. Each tile is a day; the accent marks today, dimmer tiles distinguish past and future days. Handles up to six weeks. |
| L | Date Poster | Full-height day number beside weekday, month and year. Date only. |
| M | Word Glow | Exact 12-hour time in a field of glowing words: IT IS / TEN / TWENTY / FOUR. The filler letters reflow each minute. Uses OH ONE through OH NINE and O'CLOCK at minute zero. |
| P | Minute Runner | Block time, optional date and an original pixel runner making one lap each minute. Coins disappear as it passes them. |

## Controls

- **Design:** Switch between all twelve layouts without leaving Customize.
- **24-hour time:** Available for numeric clocks, including Perpetual Card and Week Strip. Hidden on date-only designs and Word Glow. Numeric hour fields use two digits for consistent spacing.
- **Show date:** Available when the date is an optional footer or side label. Calendar-first designs keep their date content.
- **Seconds indicator:** Available on Station, Orbit and Minute Runner. Turning it off removes the seconds hand/arc or parks the runner; the main time still updates.
- **Animate:** Available on the six moving designs. Off removes flip/ruler/hand choreography and runner bouncing, and changes smooth second motion to whole-second steps. It does not freeze time.
- **Palette / colors:** Palette gradients tint the time and supporting geometry. Accent color changes the secondary marks; in Word Glow it controls the illuminated words. Original retains each design's characteristic colors. Forced night colors override custom colors throughout.
- The existing screen-wide Still/Breathe/Slide/Sparkle motion controls remain separate from the design's own Animate setting.

Phone Customize previews and the Pi use the same renderer and the device's configured timezone. Gallery thumbnails are settled snapshots; Customize requests fresh frames. The displayed time is based on the supplied wall clock, so entering a screen does not start a fictional clock or replay an old date. Clockwork's choreography lasts 1.5 seconds after a minute boundary; Platform's flip lasts 0.4 seconds and Minute Track's slide 0.5 seconds.

## Implementation

- `clock_canvas.py`: clipped integer drawing primitives, bounded glyph-mask cache, no third-party dependencies.
- `clock_faces.py`: pure localized-datetime-to-RGB renderer, calendar calculations, exact word time and dial patterns for all ten numerals.
- `blocks.py`: `clock_design` full-panel block; `RenderContext.animate_clock` lets static gallery previews settle decorative motion.
- `catalog.py`: schema, twelve stable template IDs, Time shelf entries. Family `clock_design` keeps the old clock editor from splitting these compositions into multiple slots.
- `web/options.js`: design-specific control visibility and a compact design selector.
- `web/matrix.js`, `web/api.js`: fresh clock previews and a faster cadence for moving designs; hidden tabs pause requests.
- `deploy-manifest.json`: includes both new runtime modules.

All designs run offline. No Pillow, image assets, network lookup or hardware configuration is required at runtime. Smaller builder slots display a full-panel hint instead of cropping the design.

## Inspiration and scope

Original pixel compositions translating the approved concept studies: [Solari Cifra 3](https://www.cifra3.com/en) (Platform), [Mondaine](https://eu.mondaine.com/pages/design-technologie) (Station), [ClockClock](https://www.humanssince1982.com/en-eu/collections/collectibles) (Clockwork), [Danese Timor](https://www.danesemilano.com/contents/files/products/timor_files_mari_timor_481.pdf) (Perpetual Card) and [QLOCKTWO](https://qlocktwo.com/en-us/wordclock) (Word Glow). These are native pixel interpretations, not copied product artwork or simulations of their physical mechanisms.

The four unselected concepts (Warm Tubes, Daylight Ridge, Light Blocks and Binary Tiles) remain design studies and are not included in this release.
