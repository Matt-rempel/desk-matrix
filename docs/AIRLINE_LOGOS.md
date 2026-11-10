# Airline artwork on the 64×32 panel

Nearby and followed-flight cards reserve a 22×22 region for airline marks.
Callsign and route use the 40-pixel column beside it. Nearby flights retain
distance/altitude below; followed flights retain a progress bar and remaining
time below. Compact custom slots still show their selected text field.
AirSprint uses a wider header (up to 64×18) for its horizontal wordmark, with
callsign and route on the next row and distance/altitude or remaining time below.
Followed AirSprint flights keep their progress bar.

The web app also shows smooth versions of the same marks in the gallery's
**Planes nearby** list, the **Follow one** nearby picker, and the flight identity
beside the callsign input/lookup result. All seven known operators are supported.
Unknown registrations keep a neutral plane symbol; a logo is not inferred solely
from a regional/codeshare flight's marketing relationship. Badges have accessible
airline labels and a neutral fallback if an image cannot load.

These assets are rasterized from published artwork, rather than hand-drawn
7×7 approximations. Original colour, shape and aspect ratio are preserved
within the limits of the pixel grid. Palette quantization includes dim edge
pixels to soften diagonals. Logos are bundled and do not require a network
request, new API account, Pillow or CairoSVG on the Pi.

## Sources

- Flair Airlines: `tools/logo-sources/flair.png`, the user's supplied green
  circular Flair mark, prepared with the image tool to remove the charcoal app
  tile outside the circle. The green circle and dark lettering remain opaque;
  the exterior is transparent on the panel and in browser badges. Numeric `FLE`
  and `F8` callsigns select this mark.
- AirSprint: `tools/logo-sources/airsprint.png`, the user's supplied horizontal
  AirSprint Private Aviation logo, prepared with the image tool to remove its
  white background and interior white negative spaces. The navy wordmark, blue
  swoosh and tagline remain. Numeric `ASP` callsigns select this artwork. Its
  wide layout avoids squeezing the complete lockup into a 22-pixel square.

- American Airlines: `tools/logo-sources/american.png`, the user's supplied
  red/blue/silver flight symbol with the white background removed using the
  image tool. The silver eagle head is retained as artwork, not removed with
  the background. Numeric `AAL` and `AA` callsigns select this mark.

- Delta: `tools/logo-sources/delta.png`, the user's original vertical lockup.
  The red widget is isolated above the tiny dark wordmark for legibility;
  its existing transparency is retained. Numeric `DAL` and `DL` callsigns and the legacy provider's
  `delta` hint select this artwork.

- United white globe on blue: `tools/logo-sources/united.png`, supplied by the
  user. The blue square is retained as part of the artwork. `UAL` and `UA`
  numeric callsigns select this mark; unrelated regional operators are not
  assumed to be United solely from their own operator code.

- Air Canada red rondelle: `tools/logo-sources/aircanada.png`, the user's
  supplied Air Canada roundel with its white background removed using the
  image tool. Both the exterior and interior negative spaces are transparent.
  Trademark rights remain with Air Canada.
- WestJet two-colour leaf: `tools/logo-sources/westjet.png`, from the
  [WestJet media resources](https://www.westjet.com/en-ca/media/resources)
  [colour lockup](https://www.westjet.com/content/dam/westjet/images/newsroom/media-resources/logos/WestJet-logo-colour.png).
  The leaf is isolated from the right side of that lockup for this small
  identifying display. WestJet retains rights in its artwork; this is not an
  official or endorsed airline application.

The original five sources were prepared 2026-10-31; Flair and AirSprint were
added 2026-11-10. SHA-256 hashes are included in the
generated `airline_logos.py` data for reproducibility. The artwork is used to
identify the airline associated with a flight, not as application branding.

## Rebuilding

Build-time dependency: Pillow.

```sh
python tools/build_airline_logos.py tools/logo-sources/aircanada.png tools/logo-sources/westjet.png --extra united tools/logo-sources/united.png --extra delta tools/logo-sources/delta.png --extra american tools/logo-sources/american.png --extra flair tools/logo-sources/flair.png --extra airsprint tools/logo-sources/airsprint.png --web-dir web > /tmp/logos.json
```

Use the result as `LOGOS` in `airline_logos.py`; the helper resolves ICAO and
IATA callsigns and accepts the existing provider icon hints. Unknown airlines
retain the generic/legacy icon fallback. Rendering and previews share the
same asset data. New art does not alter saved screens or lineup entries.
`--web-dir` writes bounded 128px marks and a 256px-wide AirSprint image as flat
`web/airline-*.png` assets. `catalog_json()` publishes the shared `AIRLINES`
identity/prefix table and image paths, so the browser and panel use the same
operator matching rules. The Pi needs no imaging dependency at runtime.
