# Clock and calendar collection

In **Screens → New screen → Time**, choose a design, customize it, save it to Your screens, then use Show now or add it to a lineup. Existing clock templates remain available. Installing this collection does not change a saved screen or add anything to a lineup automatically.

These designs use the entire native **64 × 32** display. Their geometry is composed for each design. Tracker has independent Font and Size controls for the time; the other faces retain their composed typography.

| Concept | Screen | What it shows |
| --- | --- | --- |
| A | Platform | Two split-flap plates for hours and minutes, colon and optional date footer. Changed plates briefly collapse and open at the new minute. |
| C | Station | Railway-style analog dial, digital time, weekday and date. Optional seconds hand. |
| D | Time Stack | Large block hours at the top left and minutes at the bottom right, with date in the open corner. |
| E | Orbit | Concentric hour, minute and second rings beside readable digital time and date. The hour ring always follows the familiar 12-hour dial, even with a 24-hour numeric readout. |
| G / New | Tracker | Large digital time and a sliding ruler. Choose Track → Minutes or Seconds. The pointer marks the selected minute/second and nearby values wrap from 59 to 00. |
| H | Clockwork | Twenty-four miniature dials arrange their hands into four numerals; the changed numeral briefly rotates its hands at each minute. |
| I | Perpetual Card | Weekday calendar tab, large day number, digital time and month. |
| J | Week Strip | Digital time above the current Monday–Sunday week, with today's date highlighted. Adjacent dates can cross a month or year boundary. |
| K | Month Map | Large day number, month/year and a Monday-first month grid. Each tile is a day; the accent marks today, dimmer tiles distinguish past and future days. Handles up to six weeks. |
| L | Date Poster | Full-height day number beside weekday, month and year. Date only. |
| M | Word Glow | Exact 12-hour time in a field of glowing words: IT IS / TEN / TWENTY / FOUR. The filler letters reflow each minute. Uses OH ONE through OH NINE and O'CLOCK at minute zero. |
| P | Minute Runner | Block time, optional date and an original pixel runner making one lap each minute. Coins disappear as it passes them. |

## Controls

- **Design:** Switch between all twelve layouts without leaving Customize.
- **Track:** Tracker has one Minutes/Seconds selector. Minutes is the default for new screens. The choice changes only the ruler; font, size, colors, date and time format stay with the screen.
- **24-hour time:** Available for numeric clocks, including Perpetual Card and Week Strip. Hidden on date-only designs and Word Glow. Tracker clocks omit the leading hour zero in 12-hour mode (9:37) and retain it in 24-hour mode (09:37). The other composed numeric fields retain two digits for spacing.
- **Font / Size:** Tracker offers Standard, Block, Outline and Digital, with Auto, Max, Extra large, Large, Medium, Small and Tiny sizes. Auto keeps the original 14-pixel time area. Extra large uses 20 pixels; Max fills up to 20 pixels with a footer, or 25 when both date and optional seconds readout are hidden. The ruler moves down to stay fully visible; its labels and the date keep their own small font. Font settings are retained but ignored when switching to another design.
- **Show date:** Available when the date is an optional footer or side label. Calendar-first designs keep their date content.
- **Seconds:** Platform, Time Stack, Tracker in Minutes mode, Clockwork, Perpetual Card and Week Strip offer Off, Number or Progress bar. Off is the default, preserving saved appearances. The number is placed beside the date or AM/PM marker, except Week Strip, which shows HH:MM:SS. The bar occupies a spare row and fills over the minute. Narrow bars necessarily advance in coarser pixel steps.
- **Seconds indicator:** Available on Station, Orbit and Minute Runner. Turning it off removes the seconds hand/arc or parks the runner; the main time still updates.
- **Animate:** Available on the six moving designs. Off removes flip/ruler/hand choreography and runner bouncing, and changes smooth second motion to whole-second steps. It does not freeze time.
- **Palette / colors:** Palette gradients tint the time and supporting geometry. Accent color changes the secondary marks; in Word Glow it controls the illuminated words. Original retains each design's characteristic colors. Forced night colors override custom colors throughout.
- The existing screen-wide Still/Breathe/Slide/Sparkle motion controls remain separate from the design's own Animate setting.

Phone Customize previews and the Pi use the same renderer and the device's configured timezone. Gallery thumbnails are settled snapshots; Customize requests fresh frames. The displayed time is based on the supplied wall clock, so entering a screen does not start a fictional clock or replay an old date. Previous-minute animations follow the actual timeline through daylight-saving changes. Clockwork's choreography lasts 1.5 seconds after a minute boundary; Platform's flip lasts 0.4 seconds and Minute Track's slide 0.5 seconds.

## Implementation

- `clock_canvas.py`: clipped integer drawing primitives, bounded glyph-mask cache, no third-party dependencies.
- `clock_faces.py`: pure localized-datetime-to-RGB renderer, calendar calculations, exact word time and dial patterns for all ten numerals.
- `blocks.py`: `clock_design` full-panel block; `RenderContext.animate_clock` lets static gallery previews settle decorative motion.
- `catalog.py`: schema, twelve visible template IDs and two hidden tracker compatibility IDs, Time shelf entries. Family `clock_design` keeps the old clock editor from splitting these compositions into multiple slots.
- `web/options.js`: design-specific control visibility and a compact design selector.
- `web/matrix.js`, `web/api.js`: fresh clock previews and a faster cadence for moving designs; hidden tabs pause requests.
- `deploy-manifest.json`: includes both new runtime modules.

All designs run offline. No Pillow, image assets, network lookup or hardware configuration is required at runtime. Smaller builder slots display a full-panel hint instead of cropping the design.

## Inspiration and scope

Original pixel compositions translating the approved concept studies: [Solari Cifra 3](https://www.cifra3.com/en) (Platform), [Mondaine](https://eu.mondaine.com/pages/design-technologie) (Station), [ClockClock](https://www.humanssince1982.com/en-eu/collections/collectibles) (Clockwork), [Danese Timor](https://www.danesemilano.com/contents/files/products/timor_files_mari_timor_481.pdf) (Perpetual Card) and [QLOCKTWO](https://qlocktwo.com/en-us/wordclock) (Word Glow). These are native pixel interpretations, not copied product artwork or simulations of their physical mechanisms.

The four unselected concepts (Warm Tubes, Daylight Ridge, Light Blocks and Binary Tiles) remain design studies and are not included in this release.

## Seconds on the existing clocks

The standard clock templates (Big digits, Classic, Time only, Night clock, Time & weekday and Day progress) now have **Show seconds** in the Clock section. World clocks and the original Analog clock have the same toggle in their block options. These all default to off. Numeric clocks show HH:MM:SS; analog clocks add a long seconds hand. The full numeric value auto-fits when an older fixed font would overflow, and the phone preview refreshes while seconds are visible.

Tracker in Seconds mode always shows its seconds ruler, so the extra Seconds readout selector is hidden in that mode. Animate off changes the ruler from a short slide to a direct tick. Optional readout settings are retained when switching back to Minutes, and ignored on incompatible designs.

## Gallery order and saved trackers

The Time shelf starts with Classic, Big digits, Analog, world clocks and Night clock. Calendar and graphic clock designs follow. The most experimental screens finish the shelf: Orbit, Word Glow, Clockwork and Minute Runner. The lineup screen picker uses the same order.

There is one visible **Tracker** template (`time-tracker`) and one Tracker choice in the Design selector. Existing `time-minute-track` and `time-seconds-track` IDs remain hidden compatibility templates, so saved pins and lineup references continue working. Old `minute_track` / `seconds_track` slot options are normalized in memory to `design: tracker` with `track_unit: minutes` or `seconds`. An explicit unit choice wins when editing. Reading the library does not rewrite the saved file; saving through the app stores the current format. Custom screen names are preserved.
