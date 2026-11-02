# Display palettes

The palette pickers in Customize and Build offer eleven gradients:

| Palette | Main colors |
|---|---|
| Ember | Gold → coral |
| Phosphor | Lime → mint |
| Ice | Frost → sky blue |
| Neon | Pink → violet |
| Aurora | Mint → periwinkle |
| Ocean | Cyan → blue |
| Lagoon | Pale mint → teal |
| Sunset | Peach → pink |
| Orchid | Lavender → magenta |
| Citrus | Yellow → lime |
| Rose | Pale peach → rose |

Each has a matching secondary text color and UI glow. Text gradients render in
the shared pixel renderer, so preview and panel use the same colors. Selecting a
palette follows the existing behavior: it replaces slot color overrides with
the palette colors. Original restores a built-in screen's original styling.

Paper and Night red are retired from both pickers. Existing saved screens using
their IDs still validate, load and render with their original colors. Their
metadata is exposed separately as `legacy_palettes` and is added only to the
frontend lookup map, not its selectable palette list. The scheduled Night look
setting continues to work independently; this change does not alter that setting,
brightness, saved screens or lineup.
