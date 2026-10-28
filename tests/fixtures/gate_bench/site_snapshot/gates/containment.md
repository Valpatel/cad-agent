# Gate: containment

**PASS** · 21 checks: 21 pass, 0 warn, 0 fail · a check of the CAD model against its declarations; physical fit not verified

Geometry: `exports/dossier-geometry.json` digest `0d19dd24ff02475c`, 27 shapes

## Findings

None.

## Exclusions (declared)

- screw_0, insert_0: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_1, insert_1: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_2, insert_2: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_3, insert_3: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design

## Assumptions

- each content instance is tested against the registered cavity solid with non-destructive OCCT booleans (common and cut volumes, cross-checked) against the registered cavity solid
- inside means no more than contain_mm3 of the instance is outside the cavity; touching the cavity boundary is inside
- the wall check tests each instance against the container's solid: touching is allowed, shared volume above overlap_mm3 fails
- the point furthest outside is the furthest of the vertices of a tessellation of the escaped piece, climbed to the piece's extreme point along the outward direction; its depth is a lower bound
- an instance touching the cavity boundary is re-checked by classifying points on its surface (tessellation nodes at probe_deflection_mm and a UV grid of about probe_spacing_mm per face) against the cavity, because the boolean can miss a shallow near-tangent crossing; a crossing whose footprint falls between samples, or no deeper than touch_mm, can still be missed
- the cavity-fit check requires the cavity to share no volume with the container and to lie within the box of the container and its closed_by parts; a cavity that stays inside that box but outside the material (beside an L-shaped container) is not caught
- support is a static contact test (the instance moved support_mm along `down` pushes further out of the cavity or into a supported instance than before the move, by boolean volume or, for a pair with no shared volume within support_mm, by the surface probe), not a settling or stability simulation; only the cavity and other instances count as support
- mesh-only items are sample-only: Monte Carlo volume estimates against the exact solids, with no interpenetration or support check
- the model is checked, not the print: no tolerance stack, shrink or deflection

## Limits

- `touch_mm`: 0.01
- `contain_mm3`: 0.001
- `overlap_mm3`: 0.001
- `volume_check_mm3`: 0.01
- `support`: "fail"
- `down`: [0.0, 0.0, -1.0]
- `support_mm`: 0.05
- `witness_deflection_mm`: 0.05
- `witness_max_points`: 600
- `contact_probe`: true
- `probe_deflection_mm`: 0.01
- `probe_points`: 20000
- `probe_spacing_mm`: 0.5
- `mesh_samples`: 4000
- `seed`: 0
- `poses`: {}
