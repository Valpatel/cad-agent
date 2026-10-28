# Gate: assembly

**PASS** · 55 checks: 55 pass, 0 warn, 0 fail · a check of the CAD model against its declarations; physical fit not verified

Geometry: `exports/dossier-geometry.json` digest `0d19dd24ff02475c`, 27 shapes

## Findings

None.

## Assumptions

- Each part goes in along a straight line in its step's declared direction, from beyond every part present to its modelled position: no rotation, tilt or wiggle, and no room for hands or fixtures is checked.
- An insertion is checked against the parts fitted and the fasteners installed at earlier steps (the fastener gate's install_step); parts no step fits are not obstacles (the cover check fails them). A tool sweep is checked against the fastener gate's present_at (parts no step fits count as present). Instances fitted at one step are not checked against each other.
- Conservative advancement: the part steps by its gap to each obstacle (box distance or exact), which cannot skip a contact, and by max_step_mm only within that distance of it; a feature thinner than that step can pass another between two samples there.
- Exact B-rep relations within the relation tolerances (overlap_mm3 of shared volume blocks; touching and sliding along a face are allowed); no tolerance stack, print shrink or flex, so a clear path in the model does not prove the printed parts go together.
- Tool access is the fastener gate's straight sweep of the declared envelope along the screw axis, against the parts present when the screw is driven.

## Limits

- `max_step_mm`: 1.0
- `margin_mm`: 1.0
- `refine_steps`: 12
- `max_samples`: 5000
- `tool_access`: true
- `missing_direction`: "warn"
- `touch_mm`: 0.01
- `overlap_mm3`: 0.001
- `service`: false

## Assembly sequence

| Step | Fit | Onto | Direction | Present | Clearance (mm) | Touching | Fasteners | Tool | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | base | - | -Z | 0 | - | - | - | - | pass |
| 2 | hopper | base | -Z | 1 | - | base | - | - | pass |
| 3 | insert_0 | hopper | -Z | 2 | ≥ 32.00 | hopper | - | - | pass |
| 4 | insert_1 | hopper | -Z | 3 | ≥ 31.20 | hopper | - | - | pass |
| 5 | insert_2 | hopper | -Z | 4 | ≥ 31.20 | hopper | - | - | pass |
| 6 | insert_3 | hopper | -Z | 5 | ≥ 31.20 | hopper | - | - | pass |
| 7 | board | hopper | -Z | 6 | 2.40 | hopper | - | - | pass |
| 8 | ball | hopper | -Z | 7 | 2.17..2.40 | hopper | - | - | pass |
| 9 | lid | hopper | -Z | 15 | ≥ 17.60 | hopper, insert_0, insert_1, insert_2, insert_3 | screw_0, screw_1, screw_2, screw_3 | hex key 2.5 (screw_0: pass, screw_1: pass, screw_2: pass, screw_3: pass) | pass |
| 10 | bracket | base | -Z | 20 | ≥ 22.00 | base | - | - | pass |
| 11 | hinge_block | base | -Z | 21 | ≥ 5.10 | base | - | - | pass |
| 12 | stop | base | -Z | 22 | ≥ 29.00 | base | - | - | pass |
| 13 | arm | hinge_block | -Z | 23 | ≥ 7.00 | hinge_block, stop | - | - | pass |
| 14 | pin | hinge_block | -Y | 24 | ≥ 5.41 | arm, hinge_block | - | - | pass |
| 15 | frame | base | -Z | 25 | 1.00..2.00 | base | - | - | pass |
