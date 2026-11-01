# Changelog

Every release of cad-agent: what projects using it gain and what they must change. New work goes under
`## Unreleased`. Releasing is part of the development loop ([CONTRIBUTING.md](CONTRIBUTING.md#releases)):
`tools/cut_release.py` dates that entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check
requires, and merging the release PR (`dev` → `main`) tags the release and deploys the site (when the owner has set
the `production` environment's deploy secret; until then the site job warns and skips, and the site is deployed by
hand from `main`). Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## Unreleased

## v0.5.0 (2026-11-01)

**New**
- `cad-agent snapfit`: cantilever, torsion and annular snap-fit sizing by the Covestro method, with allowable strain
  for moulded resins and, by print direction, for 11 filaments (13 entries: two have dry and wet values) (#105, [docs/compliant.md](docs/compliant.md)).
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
  areas it serves (#173).
- The topic tree: [docs/vision.md](docs/vision.md) and [docs/areas.yaml](docs/areas.yaml) map six domains and 35
  areas, each at its maturity; a test keeps every page, command, skill and agent on the map (#148).
- [Manufacturing-process profiles](research/process-profiles.md): design limits for FDM, SLA, SLS, MJF, injection
  moulding, sheet metal and CNC in one table, every rule credited to its source, with charts (#162).
- `tools/cut_release.py`: cuts a release (dates the Unreleased entry, bumps the version) and checks the result against
  CI's release gate.

- Site home page: Gyropup in 3D, its 58 parts exported from STEP by `cad-agent view`, packed small with
  `cadagent.view.pack_view` and shown by the kit's new `<cad-model>` (`kit/model.js`); a reel of real outputs with
  the numbers they computed; and "where cad-agent fits", the tools we build on beside what cad-agent adds, each with
  its maturity from `docs/areas.yaml` (#179). The browser suite fails a page with more than one and a half screens of
  text and nothing to look at; the pages still over are listed with their issues and the list only shrinks.

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

**Projects must change:** `cad-agent check` and `cad-agent report` have a **Holes clear** row per part, and it fails
("hole check not run") until `cad-agent holes` has run on the current STEP or the part is listed in `cad.holes.skip`
(#88). A project whose CI runs `build` then `check` exits 1 after the upgrade: run `cad-agent holes` (or `cad-agent
all`, which now runs it) before `check` and `report`, then fix each hole with material inside or list it as an
exception. Write STEP files with `cadagent.geometry.export_step` instead of
`cadquery.exporters.export` (or a project's own header rewrite); each STEP file changes once, then stays the same
across rebuilds. Hole-check counts now separate holes from cones. A countersunk seat that used to count as
a hole reads as a countersink, so recorded counts and findings can change on the next run. Links to the numbered lessons
(`lessons/NN-….md`) still work through one-line stubs on GitHub until v0.6.0, which removes them: point such links at
the new paths before then (the stubs name them). FEA deflections and stiffnesses with the printed materials change with
the new moduli (#125): re-run deflection, stiffness, flexure-travel and clearance-under-load checks against their
limits. Under the same forces, stresses and safety factors do not change (the PA6-CF rows' strengths are now computed
exactly, 48.96 and 23.04 MPa instead of 49 and 23). A force or a stress worked out at a given travel (a clip's
retention, a flexure at full travel) falls with E, so re-check strength at travel too, with the in-plane modulus or a
coupon. Densities change too, so mass estimates move by 1.6–9.4 %, and `MATERIALS['pa_cf'].name` is now
`'PAHT-CF (dry)'` (was `'PA6-CF'`), so report titles that print it change (#147). The CFD `read_results` `residuals`
and `T_max_history` cover the whole run, not only the newest solve (#155). Slicer include trees that are invalid or
ambiguous now fail instead of degrading (#93). The catalogue's `schema` value is now `cad-agent-catalog/2`: a reader
that checks for `/1` must accept `/2` (#174).
