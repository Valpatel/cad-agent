**New**
- `kit/gallery.js`: a tab's `data-item-noun` and `data-items-noun` name its cards in the status line, so a tab with one
  card can say "1 tool". Without them the tab's text names them, as before. `countLine` is exported for tests (#104).

**Changed**
- `catalog.json`: `fields.removed` records that v0.10.0 took `gyropup` off entries while the schema stayed
  `cad-agent-catalog/2`, so a reader that checks for `/2` still runs. Do not rely on `gyropup`; read `projects` on the
  area (#104).

**Fixed**
- Catalogue: the status line reads "1 of 181 entries", not "1 of 181 entry". Its noun now agrees with the total it
  follows, and a tab names its cards by their own noun: "1 of 8 research pages" (#104).
- Catalogue under forced colours (Windows High Contrast and the like): the maturity bars show filled steps in
  `CanvasText` and empty ones as outlined `Canvas`, and the chosen area row takes the system's selection colours
  (`Highlight`, `HighlightText`). Before, every step and the chosen row painted the same `Canvas`, so the bars vanished
  and only bold text marked the choice (#104).
