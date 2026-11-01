# Changelog

Every release of cad-agent: what projects using it gain and what they must change. Each PR adds its lines as a
fragment in [`changelog.d/`](changelog.d/README.md). Releasing is part of the development loop
([CONTRIBUTING.md](CONTRIBUTING.md#releases)): `tools/cut_release.py` folds the fragments into `## Unreleased` and
dates that entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check requires. Merging the release PR
(`dev` → `main`) tags the release and deploys the site, when the owner has set the `production` environment's deploy
secret; until then the site job warns and skips, and the site is deployed by hand from `main`. Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## Unreleased

## v0.5.0 (2026-11-01)

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
- The website, [cad-agent.valpatel.com](https://cad-agent.valpatel.com), built from this repo: every page also as
  Markdown, plus `llms.txt` and `catalog.json` for agents (#108). Long pages get a page tree and outline (#123); every
  page has a diagram, chart, render or animation, and a test keeps it so (#124); animated figures are drawn by the code
  they explain (`tools/motion_figures.py`, #158); copy buttons never cover the code (#130).
- The catalogue as a gallery: demos first, then every entry by kind and by topic-tree area, with our own covers for
  the 50 outside projects and a JSON file per area for agents (`catalog/index.json`, `catalog/<area>.json`).
  `catalog.json` moves to schema 2, which only adds fields (#174). Every outside entry says what it does and which
  areas it serves (#173). If the gallery's script fails, the page falls back to its no-script form. Outside covers
  pick their family from the entry's kernel and tools first. Tool covers show a committed still of their result, and
  the design comparison's chart is drawn from `cad-agent compare --json`, which a `--check` keeps current (#189).
- The topic tree: [docs/vision.md](docs/vision.md) and [docs/areas.yaml](docs/areas.yaml) map six domains and 35
  areas, each at its maturity; a test keeps every page, command, skill and agent on the map (#148).
- [Manufacturing-process profiles](research/process-profiles.md): design limits for FDM, SLA, SLS, MJF, injection
  moulding, sheet metal and CNC in one table, every rule credited to its source, with charts (#162).
- `tools/cut_release.py`: cuts a release (dates the Unreleased entry, bumps the version) and checks the result against
  CI's release gate.
- `Study.render(..., vmax=)` draws at a fixed colour scale (MPa), so the renders of two variants compare by eye
  (before, each render ran from 0 to its own design stress). The colour bar says the scale is fixed and names the
  study's own design stress; stress above `vmax` takes the top colour, with an arrow when the study goes past it.
  `scale` remains the deformation exaggeration (#191).

- Site home page: Gyropup in 3D, its 58 parts exported from STEP by `cad-agent view`, packed small with
  `cadagent.publish.view.pack_view` and shown by the kit's new `<cad-model>` (`kit/model.js`); a reel of real outputs with
  the numbers they computed; and "where cad-agent fits", the tools we build on beside what cad-agent adds, each with
  its maturity from `docs/areas.yaml` (#179). The browser suite fails a page with more than one and a half screens of
  text and nothing to look at; the pages still over are listed with their issues and the list only shrinks.
- The README's animated hero, drawn from Gyropup's real CAD by `tools/readme_anim.py` (`cadagent.publish.anim`): the
  five-bar leg as hidden-line edges from its STEP, assembled, its stride solved from link lengths measured in the CAD,
  its gaps from the assembly gates' relation engine and its hip frame's FEA stress. One CSS-only SVG under 250 KB that
  GitHub shows in an `<img>`, with rules a test enforces ([docs/animated-figures.md](docs/animated-figures.md), #183).

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

- The convergence chart shows the whole run and the monitored values, and no longer draws an empty solids panel
  (#155).
- The gates sweep no longer re-posts an unchanged status (#129).

**Docs and research**
- The README says what cad-agent is: agents that find, test, condense and credit the best published CAD techniques
  (#115). The toolkit page is now [Tools](docs/toolkit.md), the reference for the `cad-agent` command and the
  `cadagent` package; cad-agent itself is the whole toolkit (#178).
- Work-claim comments for sharing issues between agents (#102); the 2026-10-31 survey of agent toolkits, compliant
  mechanisms and FEA/process tools, and its catalogue entries (#109, #110). Corrected since: OrcaSlicer's own MCP server,
  slicing included, is in development on its `feature/mcp` branch, not yet in a release (#177).
- Lessons grouped by area (`lessons/process/`, `mechanical/`, `wiring/`, `electronics/`, `simulation/`, `review/`),
  with a diagram on every page (#133). The site redirects every old page for good (`tools/site-redirects.txt`).

**Projects must change:**
- `cad-agent check` and `cad-agent report` have a **Holes clear** row per part, and it fails ("hole check not run")
  until `cad-agent holes` has run on the current STEP or the part is listed in `cad.holes.skip` (#88). A project
  whose CI runs `build` then `check` exits 1 after the upgrade: run `cad-agent holes` (or `cad-agent all`, which now
  runs it) before `check` and `report`, then fix each hole with material inside or list it as an exception.
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
- Densities change, so mass estimates move by 1.6–9.4 %, and `MATERIALS['pa_cf'].name` is now `'PAHT-CF (dry)'`
  (was `'PA6-CF'`), so report titles that print it change (#147).
- The CFD `read_results` `residuals` and `T_max_history` cover the whole run, not only the newest solve (#155).
- Slicer include trees that are invalid or ambiguous now fail instead of degrading (#93).
- The catalogue's `schema` value is now `cad-agent-catalog/2`: a reader that checks for `/1` must accept `/2` (#174).
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
