**New**
- `cadagent.mechanical.inserts.printed_hole`: the insert's hole for the filament and the nozzle (#323). It takes
  SPIROL's larger hole for filled plastics, a coupon's undersize (which governs; CNC Kitchen's published 0.1 to
  0.25 mm otherwise), the RepRap arc balance as a floor for the line width, and the mesh's facets. `hole_design` and
  `check_joint` take `line_mm`, `filler_pct`, `undersize_mm` and `facets`. A fibre-filled filament adds a `printed hole`
  row, and `line_mm` adds a `boss perimeters` row.
- `cadagent.formulas`: `facet_diameter`, `polyhole` (Nophead), `arc_path_radius` and `arc_printed_diameter` (RepRap
  wiki), with golden vectors from the sources' own numbers.
- The first reference promotion sweep (#323 phase 7), on threaded inserts. It read 41 insert guides at the source:
  22 snippet-only records were promoted to read or above, and 4 read records went up to verified-at-source or encoded.
  Two new sources were added (Nophead's *Polyholes*, the RepRap wiki's *Arc Compensation*). The sweep's checklist is
  in `research/references/README.md`.
- `research/process-profiles.yaml`: four rules, the filled-plastic hole (SPIROL), the 2019 undersize (CNC Kitchen) and
  the perimeters round an insert (LulzBot, PADT), each with the source that governs where they differ.

**Changed**
- `tools/import_refmap.py` reconciles instead of overwriting. A re-import keeps every record someone has read,
  verified or lowered, and every record the map does not make, byte for byte. It still applies the map's changes
  to the rest, so `--check` passes after a promotion sweep.
- `research/process-profiles.yaml` rules may name what applies them (`applied_by`, checked by the tests), and
  expressions may use `sqrt()` and `cos()`. The insert hole's arc floor, facets and SPIROL perimeter rules are
  profile lines that `printed_hole` and `perimeter_counts` evaluate.
- `check_joint` on a fibre-filled filament (PETG-CF, PA6-CF20) now warns until you give `filler_pct` or print the
  hole coupon, because neither data sheet states the fibre content. Its hole band widens by SPIROL's 0 to 0.15 mm.
