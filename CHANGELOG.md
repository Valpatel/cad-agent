# Changelog

Every release of cad-agent: what projects using it gain and what they must change. A release PR (`dev` → `main`)
dates its entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check requires
([CONTRIBUTING.md](CONTRIBUTING.md#gates)); merging it tags the release and deploys the site. Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## v0.5.0 (unreleased)

**New**
- `cad-agent snapfit`: cantilever, torsion and annular snap-fit sizing by the Covestro method, with allowable strain
  for moulded resins and, by print direction, for 11 filaments (13 entries: two have dry and wet values) (#105, [docs/compliant.md](docs/compliant.md)).
- `cadagent.formulas`: closed-form engineering equations (beams and snap arms, torsion bars, coil springs, screw preload
  and thread strip, four-bar linkages, conduction and fan operating points), each with its SI units, validity limits
  and source; `catalogue()` lists them. A browser port drives the site's snap-arm explorer, tested against golden
  vectors from the Python (#146, [docs/formulas.md](docs/formulas.md)).
- `cad-agent holes`: the standard hole-clearance check, and [docs/common-issues.md](docs/common-issues.md), the index
  of recurring CAD mistakes and the checks that catch them (#88). Countersinks, chamfers and drill points are probed as
  cones and counted apart from cylindrical holes (#101).
- Release page: a browsable print page with thumbnails, print settings, CAD files and source (#87), pick-one groups
  and a one-build total (#89).
- Merge gates: `cad-gates/<base>/branch-flow`, `…/review` and `cad-gates/main/release` statuses, run from the default
  branch's (dev's) copy of the gates, on every push and every 15 minutes; tagged releases and the site deploy from `main` (#112).

- Site home page: Gyropup in 3D, its 58 parts exported from STEP by `cad-agent view`, packed small with
  `cadagent.publish.view.pack_view` and shown by the kit's new `<cad-model>` (`kit/model.js`); a reel of real outputs with
  the numbers they computed; and "where cad-agent fits", the tools we build on beside what cad-agent adds, each with
  its maturity from `docs/areas.yaml` (#179). The browser suite fails a page with more than one and a half screens of
  text and nothing to look at; the pages still over are listed with their issues and the list only shrinks.

**Changed**
- `src/cadagent/` is laid out by domain, as the topic tree ([docs/areas.yaml](docs/areas.yaml)) groups the work:
  `cadagent.mechanical` (`holes`, `fasteners`, `mcmaster`, `connectors`, `markings`, `compliant`, `motion_trace`),
  `cadagent.manufacturing` (`slicer`, `mesh3mf`), `cadagent.thermal` (`heatsink`), `cadagent.simulation` (`fea`, `cfd`,
  `topopt`, `explore`, `robot`, `simviz`, `simreport`), `cadagent.electrical` (`pcb`, `pcb_routing`), and for the
  practice domain `cadagent.review` (`gates`, `dossier`, `packet`, `evidence`) and `cadagent.publish` (`report`,
  `htmlreport`, `site`, `site_review`, `view`, `serve`, `release`, `render`, `dotsvg`). `project`, `cli`, `geometry`,
  `links`, `package` and `agentkit` stay at the top (#114; the table is in
  [docs/toolkit.md](docs/toolkit.md#package-layout-v050)). `cadagent.geometry` and `cadagent.review` were modules and
  are now packages at the same paths, unchanged for code that imports them. The old paths (`import cadagent.fea`,
  `from cadagent import mcmaster`, `cadagent.gates.motion`, ...) still work: each gives the same module object, so
  patching a name through it reaches the code, and so does `python -m` (`python -m cadagent.gates.run`, the v0.4 gate
  worker, runs `cadagent.review.gates.run`). The first import through an old path raises a `DeprecationWarning`
  naming the new path, reported at the line that imported it. **The old paths are removed in v0.7.0.**
  `tests/test_package_areas.py` keeps the packages and the tree in step: a module has one home, an `api:` line in its
  own domain, and a node that relies on another domain's module names it in the new optional `uses:` list.

**Fixed**
- Bambu slicer templates that include other templates are resolved before profiles are flattened (#93).
- Reproducible STEP files: `cadagent.geometry.export_step(shape, path)` writes the same bytes for the same model, with
  a fixed header date (`SOURCE_DATE_EPOCH` when set), the product named after the file and assembly links numbered
  within the file. `mcmaster normalise` writes `<PN>.norm.step` with it (#91).
- FEA printed materials take their modulus from the filament data sheet they cite: the lowest the sheet gives, across
  the layers (PLA 2060, PETG 1120, PETG-CF 1340, PAHT-CF 1820, TPU 7.4 MPa; the humid PA6-CF rows 2126 and 1042).
  Before, they were 31-147 % higher (TPU about 4x), so deflections read 24-60 % low (TPU 75 %). Each printed
  material now names its sheet (`source`), what E and the strength are taken from (`note`) and the print direction of
  E (`direction`); results repeat them in their assumptions line, and the viewer shows the direction. Densities follow
  the sheets, and `pa_cf` is named PAHT-CF, as its values always were (#125).

**Docs and research**
- Work-claim comments for sharing issues between agents (#102); the 2026-10-31 survey of agent toolkits, compliant
  mechanisms and FEA/process tools, and its catalogue entries (#109, #110).
- Lessons grouped by area (`lessons/process/`, `mechanical/`, `wiring/`, `electronics/`, `simulation/`, `review/`),
  with a diagram on every page (#133). The site redirects every old page for good (`tools/site-redirects.txt`).

**Projects must change:**
- Write STEP files with `cadagent.geometry.export_step` instead of `cadquery.exporters.export` (or a project's own
  header rewrite); each STEP file changes once, then stays the same across rebuilds (#91).
- Hole-check counts now separate holes from cones. A countersunk seat that used to count as a hole reads as a
  countersink, so recorded counts and findings can change on the next run.
- Links to the numbered lessons (`lessons/NN-….md`) still work through one-line stubs on GitHub until v0.6.0,
  which removes them: point such links at the new paths before then (the stubs name them).
- FEA deflections and stiffnesses with the printed materials change with the new moduli (#125): re-run deflection,
  stiffness, flexure-travel and clearance-under-load checks against their limits. Under the same forces, stresses and
  safety factors do not change (the PA6-CF rows' strengths are now computed exactly, 48.96 and 23.04 MPa instead of 49
  and 23). A force or a stress worked out at a given travel (a clip's retention, a flexure at full travel) falls with
  E, so re-check strength at travel too, with the in-plane modulus or a coupon.
- Move imports to the new package paths before v0.7.0 (#114). The old → new list:
  `python -c "from cadagent._moved import MOVED; print(*(f'cadagent.{o} -> {n}' for o, n in MOVED.items()), sep='\n')"`
  (an old package's submodules move with it: `cadagent.gates.motion` → `cadagent.review.gates.motion`).
- Run the gate worker, and any module run with `python -m`, at its new path: `python -m cadagent.review.gates.run`
  instead of `python -m cadagent.gates.run`. The old one still runs, with a warning, until v0.7.0.
- Type checkers and IDEs do not run import finders, so they report the old paths as missing modules at once (mypy:
  `Cannot find implementation or library stub for module named "cadagent.fea"`), though they still run. A
  type-checked project moves its imports when it upgrades.
- After pulling, a git checkout keeps `src/cadagent/compliant/`, `dossier/`, `explore/` and `gates/` holding only
  their `__pycache__`; `tests/test_package_layout.py` names each one. Delete them (this removes only caches and the
  folders they leave empty):
  `find src/cadagent -name __pycache__ -type d -prune -exec rm -rf {} + && find src/cadagent -type d -empty -delete`
- A test that replaces a *whole module* through its old path (`sys.modules["cadagent.report"] = fake`, or
  `cadagent.report = fake`) no longer reaches cad-agent's own code, which imports the new paths. Replace it at the new
  path: `monkeypatch.setitem(sys.modules, "cadagent.publish.report", fake)`.
- 44 of the 61 moved library files changed bytes: their imports, two paths to `webkit/`, and text that names module
  paths, including what they write into outputs (the slicer's work-folder marker, the CFD case headers, the
  simulation report's and the design comparison's footers, the gate worker's command line, the dossier lint's rule
  titles, a line on the site's review pages, and the geometry record's `hash` line, which gate inputs leave out, so
  verdicts stay current). A project that binds evidence to a library file's sha256 (`Path(cadagent.slicer.__file__)`)
  gets new hashes for those 44 from the move alone, and must measure again. The move leaves the other 17 byte for
  byte (`geometry`, `fasteners`, `connectors`, `markings`, `mcmaster`, `motion_trace`, `compliant/__init__`,
  `compliant/allowables`, `compliant/figures`, `mesh3mf`, `robot`, `pcb_routing`, `evidence`, `dossier/load`,
  `gates/verdict`, `view`, `serve`); `geometry` and `mcmaster` change in this release anyway, for `export_step` (#91).
