**New**
- `cad-agent slice` with PrusaSlicer keeps what PrusaSlicer said about each part: it runs with `--loglevel 3`, saves
  the log next to the G-code (`build/slicer/<part>/out/slicer.log`) and records each part's `warnings`, `errors`,
  `stability_issues` (the categories after "Detected print stability issues", such as `Long bridging extrusions`) and
  `benign_log_lines` (a count of PrusaSlicer's notes that say nothing about the print).
  `cadagent.manufacturing.slicer_prusa.parse_log` reads a log (#246, by Jeff Patrick).
- Per-part slicer settings: `cad.slicer.parts` may be a mapping of part name to `{overrides: {...}}`, applied on top
  of `cad.slicer.overrides` (a brim for a tall part, more perimeters for a pin-loaded link). A report row records its
  `part_overrides` and is stale once they change (#246, by Jeff Patrick).

**Changed**
- A PrusaSlicer slice report gives each part an `ok`: true only with exit code 0, G-code written and no error or print
  stability issue. The report's `pass` needs every part ok, and `cad-agent slice` exits 1 otherwise, so a part that
  slices but PrusaSlicer says will print badly no longer reports as fine. Bambu Studio reports are unchanged (#246, by Jeff Patrick).
- A part PrusaSlicer flagged keeps its grams and time, and says so: its print-release card carries a `slicer: …` pill,
  the release warnings (and `manifest.json`) name it, and the results report's slicer line adds `NOT OK, flagged by
  the slicer` (#270).
- Slicing some parts (`cad-agent slice PART ...`) keeps only the old rows that are still current; `pass` is about the
  rows in the report, so a part left out is reported as not sliced (#270).

**Projects must change**
- PrusaSlicer projects: re-run `cad-agent slice`. A part with a stability issue or slicer error now fails it; fix the
  geometry, or set that part's own overrides under `cad.slicer.parts` (#246, by Jeff Patrick).
