**Fixed**
- `cad-agent check`, `report` and `all`: a part in `cad.holes.skip` is a `skip` row under "Holes clear", not a
  `pass`: it was not checked, so it no longer adds to the pass count. The report's overall result and
  `exports/hole-checks.json` are unchanged (#526).
