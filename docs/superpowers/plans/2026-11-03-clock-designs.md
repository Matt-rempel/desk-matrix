# Clock Design Collection Implementation Plan

> For agentic workers: use superpowers:executing-plans for inline execution.

**Goal:** Add the twelve approved native 64 × 32 time/date designs to the Time gallery.
**Architecture:** A stdlib framebuffer canvas and shared clock-face renderer feed the existing block pipeline and HTTP previews. One full-panel block selects its design; each template has a stable ID. Existing clocks remain available.
**Tech stack:** Python standard library, native RGB frames, plain JavaScript.
**Spec:** Approved A, C, D, E, G, H, I, J, K, L, M, P studies in the clock-concepts-2026-11-03 design pack; user approved this subset. Runtime details documented in docs/CLOCK_DESIGNS.md.

## Global constraints

- Exactly the selected twelve concepts: Platform, Station, Time Stack, Orbit, Minute Track, Clockwork, Perpetual Card, Week Strip, Month Map, Date Poster, Word Glow, Minute Runner.
- Native 64 × 32; no runtime Pillow or network dependencies. Use the supplied localized time.
- Preserve existing screen IDs, user state, hardware settings and touch/keyboard focus behavior.
- Expose only controls relevant to the chosen design. Palette and night overrides apply throughout.
- Implement, verify, review, push and install using the previously authorized workflow.

## Review focus

Midnight and 12/24-hour transitions; leap years and six-row calendars; all ten Clockwork digits; minute-boundary animations returning to the correct time; palette/night overrides without original-color leaks.

## Tasks

1. [x] Add native canvas and twelve clock faces. First write failing tests for time/date semantics and valid native frames; implement and visually inspect contact sheets and motion.
   - Produces: clock_canvas.py, clock_faces.py, test_clock_faces.py.
   - Verify: python3 -B -m unittest test_clock_faces.
2. [x] Integrate full-panel clock_design block, twelve templates, schema, and deployment manifest. Test library validation, rendering and offline data needs.
   - Consumes: face names and draw_face API; produces catalog metadata and block renderer.
   - Verify: targeted Python tests plus existing renderer/catalog/library tests.
3. [x] Add design-specific options and live editor previews. Verify options change on design selection, preview refreshes without stale cache, and mobile layout fits.
   - Consumes: catalog options; produces JavaScript controls and preview updates.
   - Verify: node --test test_web_api.mjs and local browser walkthrough.
4. [ ] Document usage; run full checks; request fresh review; address material findings; commit, push and install. Confirm services, served files, all twelve previews, and unchanged saved user state.
   - Verify: full unittest discovery, Node tests, sh -n install.sh, git diff --check, deployed smoke checks.
