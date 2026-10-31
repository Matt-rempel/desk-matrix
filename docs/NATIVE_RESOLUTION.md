# Native 64×32 display

The current renderer supersedes the 32×16 geometry in the original
`REDESIGN_PLAN.md`. Python defines `WIDTH=64`, `HEIGHT=32` in `render.py`;
the web frame contract is in `web/display.js`.

- Frames contain 2,048 RGB pixels, row-major (`y * 64 + x`), encoded as
  12,288 hexadecimal characters in preview and status responses.
- `/api/catalog` and `/api/status` expose `display.width` and `display.height`.
- All six layout IDs remain stable. Their slot bounds come from `catalog.py`.
  The builder uses those bounds relative to the native dimensions.
- The renderer clips blocks to their slots. Typography offers display (20 px),
  large (14 px), big (10 px), 5×7 and 3×5 fonts; auto text prefers complete
  content before abbreviations. Charts, clock faces, radar and animations
  draw directly at native resolution.
- Full flight cards show callsign, route and distance/altitude together.
  Hockey cards show both scores and status together. Other built-ins have
  revised spacing, larger values and native graphics.
- Library schema version 1 remains compatible: saved screens contain layout
  IDs rather than coordinates. No saved screen, lineup or original art data
  needs rewriting. Existing explicit font choices remain respected.
- Art supports 14×14, 32×32 and 64×32, plus legacy 7×7, 16×16 and 32×16.
  Old art scales by whole pixels to fit its slot; native art retains individual
  pixels. Oversized art is centered and cropped to the slot.
- The existing Bonnet command with `--panel-scale 2` now outputs native pixels.
  It is also the default geometry. `--panel-scale 1` averages 2×2 pixels for
  older hardware. Mapping, GPIO timing and power settings are independent.

Validation: run the Python suite, `node --test test_web_api.mjs`, and
`sh -n install.sh`. `python3 blocks.py <screen-id>` prints a native ASCII
preview. Physical flicker and readability still require observation at the panel.
