**Fixed**
- `cad-agent check`, `report` and `all`: a part the slicer did not report as ok (`ok: false` in a current
  `exports/slice-report.json`: a slicer error or a print-stability issue PrusaSlicer names) is now a failing row in a
  new "Slicer" feature (`cad-slicer`), with the slicer's own words. Before, it was footer text only and the report
  still passed. Each sliced part that is ok gets a passing row with its grams and minutes (#520).

**Projects must change**
- A project that runs `cad-agent slice` and has a flagged part now gets exit 1 from `check`, `report` and `all` until
  the part is fixed and sliced again. Projects that do not slice, or whose slice report is stale, see no change (#520).
