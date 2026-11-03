# Fonts and sizes

In Customize or Build, choose a **Font**, then a **Size**. Each font button
shows a native 64×32 sample produced by the same renderer as the panel.

| Font | Appearance |
| --- | --- |
| Standard | Fine stroke lettering and familiar clock digits |
| Block | Solid, chunky pixel cells |
| Outline | Hollow block lettering with a one-pixel border, including Max |
| Digital | Full-height seven-segment digits, with a centered 1 and stroke letters for words and units |

| Size | Maximum height |
| --- | --- |
| Auto | Fits the slot using the normal sizes, up to 20 rows |
| Max | Fits both axes, up to 30 rows on a full panel |
| Extra large | 20 rows |
| Large | 14 rows |
| Medium | 10 rows |
| Small | 7 rows |
| Tiny | 5 rows |

Sizes fit down when necessary to keep the entire value visible. Max adapts
the digit width as well as height, so both `4:37` and `12:59` fit. On a
full-panel clock it leaves one pixel above and below. Select **Second line →
Nothing** to give a clock the whole panel. Changing Font or Size alone keeps
the layout and the other selection. Other blocks keep their smaller labels,
icons and neighbouring slots.

At Small and Tiny, Outline uses solid pixel cells and Digital uses compact
digits to stay legible. Long values that cannot fit at Tiny scroll within
their slot. Gradients and blinking colons work with every family; replacing
the colon with a blank keeps the digits stationary.
Outline / Max also uses hollow, one-pixel borders on the colon dots.
Its 7 has a continuous top bar and straight right stem, forming a square
corner instead of a stepped diagonal.

Digital's vertical segments reach the same cap height and baseline as its
horizontal segments. The 1 is a centered continuous stem, and the 4 has a
continuous right stem, avoiding the shortened appearance of inset bars.

## Storage and compatibility

New choices live in the slot's `options.font_family` and `options.font_size`:

```json
{"font_family": "block", "font_size": "max"}
```

Families are `standard`, `block`, `outline`, and `digital`. Sizes are `auto`,
`max`, `xl`, `large`, `medium`, `small`, and `tiny`.

The original `options.font` values remain accepted and retain their exact
rendering when neither new key is present. Viewing an old screen does not
rewrite it. The editor derives its current selections from `legacy_fonts`
in the catalog; editing one axis saves both new keys and preserves other
options. A partial API update inherits the missing axis from the legacy font.
An old `block` maps to Block / Auto; old `max` maps to Standard / Max.

`render.py` owns family rasterization and cached fitting. `catalog.py` declares
the options and generates public font samples. `blocks.py` applies typography
to the main text layers. `web/fonts.js` supplies the shared editor controls.
No downloaded fonts, runtime image libraries, or external services are needed.
