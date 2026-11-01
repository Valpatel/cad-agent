**New**
- `cad-agent export-3mf` also writes `exports/<name>-plates.3mf`: every printed part at its quantity, in print
  orientation, packed onto as many build plates as the bed needs, in one Bambu Studio project. Where Bambu Studio is
  installed at export time, the file carries its project settings, opens with the plates laid out and slices plate
  by plate; without it, Bambu Studio opens the parts on one plate. Parts with different filaments never share a
  plate. Next to it, `<name>-plates.svg` shows the plates from above and `<name>-plates.json` records the layout
  (#84).
- `cadagent.manufacturing.plates`: `pack` (MaxRects over footprints, with gap, margin, keep-out areas, quarter turns
  and the diagonal turn a long part needs), `check_plates`, `write_plates_3mf` and `read_plates_3mf` (read back and
  verified; the same bytes for the same parts, settings and Bambu Studio version), `plates_svg` and `export_plates`
  (#84).
- `cadagent.manufacturing.slicer.project_settings`: Bambu Studio's own project settings for a printer, process and
  filaments, and `default_bed_type`: the plate surface a printer ships with (#84).
- `cad.plates` in `cad-agent.yaml`: `parts` (with each part's `quantity` and `filament`), `gap_mm`, `margin_mm`,
  `rotate`, `keep_out` and `bed_type`. Parts and quantities default to `cad.release` (#84).

**Projects must change**
- `export-3mf` (and `all`) now exits 1 when a part fits no build plate or the parts need more than 36 plates. Set
  `cad.plates.parts` to the parts you print, or `cad.plates: false` to write no plates file (#84).
- `exports/` gains three files per project, deleted again by a run that fails or by `cad.plates: false`. A part
  named `<name>-plates` must be renamed, or plates turned off (#84).
- A `cad.slicer` printer, process or filament (or a `cad.plates` filament) that Bambu Studio has no profile for now
  stops `export-3mf` with a config error where Bambu Studio is installed (#84).
