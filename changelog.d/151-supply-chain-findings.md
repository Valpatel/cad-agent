**Changed**
- `pyproject.toml` floors: `pillow>=13.0` (every older release has critical advisories), `vtk>=9.5.2` (past three
  advisories fixed in 9.5.1; the lowest VTK that cadquery-ocp 7.9.3 pins), `markdown>=3.8.1`, `numpy>=1.22`,
  `pyyaml>=6.0` and `pytest>=9.0.3` (they had none). CI now also runs the core suite at the numpy, PyYAML and pytest
  floors, and the site and release tests at markdown 3.8.1 (#151).
- The web kit's `three/` and `fonts/` folders have SHA-256 receipts (`SOURCE.json`), so a silent change to any of them
  fails `tests/webkit-vendor.test.mjs` and the supply-chain report; every vendored kit file now has one. The receipt
  for three.js names its npm tarball and records the one local patch to OrbitControls; the fonts' receipt names the
  Google Fonts and licence URLs the files came from (#151).
- `tools/resource_audit.py`: a web kit receipt can list a `patched` file (expected to differ from its package, made
  against a recorded upstream file) while every other file must still match byte for byte; a receipt with no npm
  package records hashes and sources only; `npx --no-install` counts as pinned, since it runs only what the lockfile
  installed (#151).
- Catalogue and pages: moved repositories point at their new owners (BackplaneWorks/kistack, BackplaneWorks/Backplane,
  the-dual-space/pymoo, meta/Ax), the dead OpenFOAM starter-script link and the plain-HTTP CalculiX links are fixed,
  install advice no longer tells readers to install from a plugin marketplace or run `uvx` unpinned, and a
  `curl | sh` installer is described as the risk it is. The supply-chain report's open findings fall from 1 critical,
  15 medium, 37 low and 12 info to the counts in `research/security-report.md` (#151).

**Projects must change**
- A project environment holding pillow below 13.0, vtk below 9.5.2 or markdown below 3.8.1 must upgrade them
  (`pip install -U pillow vtk markdown`) before installing this cad-agent with the `cad`, `sim` or `site` extra. A
  project that pins cadquery 2.6 or 2.7 (cadquery-ocp 7.8, which pins vtk 9.3.1) must move to cadquery 2.8 (#151).
