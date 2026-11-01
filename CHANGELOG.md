# Changelog

Every release of cad-agent: what projects using it gain and what they must change. A release PR (`dev` → `main`)
dates its entry as `## vX.Y.Z (YYYY-MM-DD)`, which the `cad-gates/main/release` check requires
([CONTRIBUTING.md](CONTRIBUTING.md#gates)); merging it tags the release and deploys the site. Releases up to v0.4.2
are described on the [tags page](https://github.com/Valpatel/cad-agent/tags).

## v0.5.0 (unreleased)

**New**
- `cad-agent snapfit`: cantilever, torsion and annular snap-fit sizing by the Covestro method, with allowable strain
  for moulded resins and, by print direction, for 13 filaments (#105, [docs/compliant.md](docs/compliant.md)).
- `cad-agent holes`: the standard hole-clearance check, and [docs/common-issues.md](docs/common-issues.md), the index
  of recurring CAD mistakes and the checks that catch them (#88). Countersinks, chamfers and drill points are probed as
  cones and counted apart from cylindrical holes (#101).
- Release page: a browsable print page with thumbnails, print settings, CAD files and source (#87), pick-one groups
  and a one-build total (#89).
- Merge gates: `cad-gates/<base>/branch-flow`, `…/review` and `cad-gates/main/release` statuses, run from the default
  branch's (dev's) copy of the gates, on every push and every 15 minutes; tagged releases and the site deploy from `main` (#112).

**Changed**
- `src/cadagent/` is grouped into packages by job: `cadagent.geometry` (`holes`, `fasteners`, `connectors`,
  `markings`), `cadagent.sim` (`fea`, `cfd`, `heatsink`, `topopt`, `simviz`, `simreport`, `robot`, `motion_trace`),
  `cadagent.make` (`slicer`, `mesh3mf`, `release`, `mcmaster`, `pcb`, `pcb_routing`) and `cadagent.publish` (`report`,
  `htmlreport`, `review`, `packet`, `render`, `view`, `dotsvg`, `site`, `site_review`, `serve`) (#114; the table is in
  [docs/toolkit.md](docs/toolkit.md#package-layout-v050)). The old paths (`import cadagent.fea`,
  `from cadagent import mcmaster`, ...) still work: each gives the same module object, so patching a name through it
  reaches the code. The first import through an old path raises a `DeprecationWarning` naming the new path, reported
  at the line that imported it. **The old paths are removed in v0.7.0.**

**Fixed**
- Bambu slicer templates that include other templates are resolved before profiles are flattened (#93).

**Docs and research**
- Work-claim comments for sharing issues between agents (#102); the 2026-10-31 survey of agent toolkits, compliant
  mechanisms and FEA/process tools, and its catalogue entries (#109, #110).

**Projects must change:**
- Hole-check counts now separate holes from cones. A countersunk seat that used to count as a hole reads as a
  countersink, so recorded counts and findings can change on the next run.
- Move imports to the new package paths before v0.7.0 (#114).
- A test that replaces a *whole module* through its old path (`sys.modules["cadagent.report"] = fake`, or
  `cadagent.report = fake`) no longer reaches cad-agent's own code, which imports the new paths. Replace it at the new
  path: `monkeypatch.setitem(sys.modules, "cadagent.publish.report", fake)`.
- 16 of the 29 moved library files changed bytes: their imports, two paths to `webkit/`, and text that names module
  paths, including what they write into outputs (the slicer's work-folder marker, the CFD case headers, the
  simulation report's footer and a line on the site's review pages). A project that binds evidence to a library
  file's sha256 (`Path(cadagent.slicer.__file__)`) gets new hashes for those 16 from the move alone, and must measure
  again. The move leaves the other 13 byte for byte (`geometry`, `fasteners`, `connectors`, `markings`, `robot`,
  `motion_trace`, `mesh3mf`, `mcmaster`, `pcb`, `pcb_routing`, `view`, `dotsvg`, `serve`).
