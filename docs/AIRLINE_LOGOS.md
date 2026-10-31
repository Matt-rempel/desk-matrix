# Airline artwork on the 64×32 panel

Nearby and followed-flight cards reserve a 22×22 region for airline marks.
Callsign and route use the 40-pixel column beside it. Nearby flights retain
distance/altitude below; followed flights retain a progress bar and remaining
time below. Compact custom slots still show their selected text field.

These assets are rasterized from published artwork, rather than hand-drawn
7×7 approximations. Original colour, shape and aspect ratio are preserved
within the limits of the pixel grid. Palette quantization includes dim edge
pixels to soften diagonals. Logos are bundled and do not require a network
request, new API account, Pillow or CairoSVG on the Pi.

## Sources

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

Source files were prepared 2026-10-31. SHA-256 hashes are included in the
generated `airline_logos.py` data for reproducibility. The artwork is used to
identify the airline associated with a flight, not as application branding.

## Rebuilding

Build-time dependency: Pillow.

```sh
python tools/build_airline_logos.py tools/logo-sources/aircanada.png tools/logo-sources/westjet.png --extra united tools/logo-sources/united.png --extra delta tools/logo-sources/delta.png > /tmp/logos.json
```

Use the result as `LOGOS` in `airline_logos.py`; the helper resolves ICAO and
IATA callsigns and accepts the existing provider icon hints. Unknown airlines
retain the generic/legacy icon fallback. Rendering and previews share the
same asset data. New art does not alter saved screens or lineup entries.
