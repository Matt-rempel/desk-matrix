# Lineup editing

Lineup has three levels:

1. **Default screens** play whenever no schedule is active.
2. **Schedules** choose another list for particular hours and days. Edit schedule
   reveals name, start/end and weekdays. More schedule options contains brightness,
   priority and deletion. The first matching schedule still wins when hours overlap.
3. **Live alerts**, **Device alerts** and **Transitions** are collapsed until opened.

Each list shows one compact row per screen, with its position, preview, name and
duration. Tap the row for Screen settings: duration, Move earlier, Move later and
Remove from lineup. Add screen opens the existing picker. Removing a lineup entry
does not delete its saved screen. Repeated entries keep independent durations.

All changes remain drafts until **Save lineup**. **Discard** restores the last
saved lineup. Closing a schedule editor or settings panel is not a save action.
Opening controls does not change the lineup. Schedule deletion requires confirmation
and can still be discarded before saving.

The existing library schema and API are unchanged. Existing names, order, times,
days, durations and brightness remain valid; non-preset durations are retained in
the duration picker. No migration or reset is required. Paired time controls share
the same constrained widths and native-appearance reset in Lineup and Device.

## UI verification

Use isolated fixture state, not the user's live lineup:

- Open a screen, change its duration, close, then Discard. Verify nothing persisted.
- Move/remove entries and save; reload and verify order. Saved gallery screens stay.
- Add the same screen twice and give each a different duration. Move one and confirm
  the other is unaffected. Open an existing non-preset duration without changing it.
- Add a schedule, edit hours/days, enable custom brightness, add screens and save.
- Cancel a schedule deletion; confirm another deletion and then Discard it.
- Expand alerts/transitions, edit and save them; confirm the other settings survive.
- Check light/dark themes, keyboard focus, settings-panel dismissal, narrow phone
  widths and desktop. Confirm rows and native time inputs stay inside their cards.
