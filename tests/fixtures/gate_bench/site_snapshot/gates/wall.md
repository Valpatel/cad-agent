# Gate: wall

**PASS** · 8 checks: 8 pass, 0 warn, 0 fail · a check of the CAD model against its declarations; physical fit not verified

Geometry: `exports/dossier-geometry.json` digest `0d19dd24ff02475c`, 27 shapes

## Findings

None.

## Assumptions

- thickness is measured by rays along the inward surface normal: mesh rays from triangle centroids (sub-sampled to max_rays) and exact B-rep rays from a UV grid on every face
- a pass means no sample was thinner than wall_mm - tol_mm; regions between samples and walls met at a slant are not measured
- the per-part wall_mm is the declared minimum; whether it suits the printer, nozzle, material and load is not checked
- a mesh reads curved walls thin by its chord error (about 0.09 mm seen on a 2.4 mm spherical shell tessellated at 0.05 mm); with the B-rep given, thin mesh samples are re-measured exactly and only confirmed ones fail; with a mesh alone, tol_mm must cover that error
- the model is checked, not the print: no shrink, elephant foot, or slicer perimeter rounding

## Limits

- `tol_mm`: 0.01
- `max_rays`: 20000
- `brep_grid`: [3, 16]
- `brep_spacing_mm`: 2.0
- `parts`: {"arm": {"wall_mm": 2.4}, "base": {"wall_mm": 2.4}, "bracket": {"wall_mm": 2.4}, "frame": {"wall_mm": 2.4}, "hinge_block": {"wall_mm": 2.4}, "hopper": {"wall_mm": 2.4}, "lid": {"wall_mm": 2.4}, "stop": {"wall_mm": 2.4}}
