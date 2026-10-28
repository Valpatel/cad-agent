# Gate: motion

**PASS** · 1 checks: 1 pass, 0 warn, 0 fail · a check of the CAD model against its declarations; physical fit not verified

Geometry: `exports/dossier-geometry.json` digest `0d19dd24ff02475c`, 27 shapes

## Findings

None.

## Exclusions (declared)

- screw_0, insert_0: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_1, insert_1: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_2, insert_2: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design
- screw_3, insert_3: thread envelope: the screw's nominal diameter overlaps the insert's minor diameter by design

## Not checked

- contains ball in hopper_cavity: not moved by I-pin-arm

## Assumptions

- joints are sampled at discrete values across their declared ranges, both ends included; the density is reported per joint axis. A collision that starts and ends between two samples, or a feature thinner than the travel per sample, can be missed: this is not a swept-volume check
- a joint's range is measured from the pose the model was built in (0 = as modelled); a joint's axis is in assembly coordinates at that pose, and a child joint's axis is carried by its parent
- what moves with a joint is its moving part's body: the transitive closure over fixed joints and fastener clamps/into (relations.moving_bodies), or the assembly's own body labels
- joints in one chain are sampled on a grid; independent joints one at a time with the others at home (0 clamped into the range) unless combined
- pairs that do not move relative to each other (static against static, parts of one body) are not queried; the relation table and connectivity gate cover them
- exact B-rep relations within the relation tolerances; no tolerance stack, print shrink, deflection or backlash: a clear pose in the model does not prove the printed parts clear

## Limits

- `touch_mm`: 0.01
- `overlap_mm3`: 0.001
- `near_mm`: 1.0
- `volume_check_mm3`: 0.01
- `default_samples`: 12
- `max_step_deg`: null
- `max_step_mm`: null
- `max_poses`: 2000
- `refine_steps`: 8
- `strict_contacts`: false
- `combine`: []
