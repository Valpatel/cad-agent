**New**
- `cad-agent slice` with PrusaSlicer: set `cad.slicer.engine: prusa` (the default stays `bambu`).
  `cadagent.manufacturing.slicer_prusa` runs `prusa-slicer` (on PATH or the flatpak) as a separate process. PrusaSlicer
  itself resolves the named printer, print and filament presets, user presets included, so a multi-tool printer such
  as the XL gets every filament setting once per tool, and it refuses a preset that does not fit the printer. Overrides
  use PrusaSlicer's names; an unknown key such as Bambu's `wall_loops` is an error. Grams and time come from the
  G-code footer, and the slice records the SHA-256 of its config and of every profile file read (#242, by Jeff Patrick).
- A PrusaSlicer slice report records `engine: prusa` and is not current for a Bambu Studio project, or the other way
  round. The release page says which slicer's presets it lists (#242, by Jeff Patrick).

**Changed**
- `export-3mf` for a PrusaSlicer project writes plates without Bambu Studio project settings, and says so (#242, by Jeff Patrick).
