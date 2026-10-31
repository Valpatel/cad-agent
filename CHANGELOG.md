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
- Merge gates: `cad-gates/<base>/branch-flow`, `…/review` and `cad-gates/main/release` statuses, run from the base
  branch's copy of the gates; tagged releases and the site deploy from `main` (#112).

**Fixed**
- Bambu slicer templates that include other templates are resolved before profiles are flattened (#93).

**Docs and research**
- Work-claim comments for sharing issues between agents (#102); the 2026-10-31 survey of agent toolkits, compliant
  mechanisms and FEA/process tools, and its catalogue entries (#109, #110).

**Projects must change:** hole-check counts now separate holes from cones. A countersunk seat that used to count as
a hole reads as a countersink, so recorded counts and findings can change on the next run.
