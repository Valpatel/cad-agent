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

**Fixed**
- Bambu slicer templates that include other templates are resolved before profiles are flattened (#93).
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

**Projects must change:** hole-check counts now separate holes from cones. A countersunk seat that used to count as
a hole reads as a countersink, so recorded counts and findings can change on the next run. Links to the numbered lessons
(`lessons/NN-….md`) still work through one-line stubs on GitHub until v0.6.0, which removes them: point such links at
the new paths before then (the stubs name them). FEA deflections and stiffnesses with the printed materials change with
the new moduli (#125): re-run deflection, stiffness, flexure-travel and clearance-under-load checks against their
limits. Under the same forces, stresses and safety factors do not change (the PA6-CF rows' strengths are now computed
exactly, 48.96 and 23.04 MPa instead of 49 and 23). A force or a stress worked out at a given travel (a clip's
retention, a flexure at full travel) falls with E, so re-check strength at travel too, with the in-plane modulus or a
coupon.
