# Gate: connectivity

**PASS** · 31 checks: 31 pass, 0 warn, 0 fail · a check of the CAD model against its declarations; physical fit not verified

Geometry: `exports/dossier-geometry.json` digest `0d19dd24ff02475c`, 27 shapes

## Findings

None.

## Exclusions (declared)

- ball#0: loose balls in the hopper
- ball#1: loose balls in the hopper
- ball#2: loose balls in the hopper
- ball#3: loose balls in the hopper
- ball#4: loose balls in the hopper
- ball#5: loose balls in the hopper
- ball#6: loose balls in the hopper
- ball#7: loose balls in the hopper

## Assumptions

- contact is the relation table's: no shared volume and a gap within touch_mm, or shared volume; a contact in the model does not prove that printed parts meet, stay put or carry load
- a joint's moving part seeds a moving body, which grows across fixed joints and fastener clamps/into declarations; every other part belongs to the static frame and must reach a grounded part through contacts, fasteners and fixed joints inside its own group; contact across groups, or with an allowed-free part, holds nothing up
- a joint holds only when its parts are measured within the declared interface clearance, else within max_joint_gap_mm for a moving joint and in contact for a fixed joint
- an item inside its container's declared cavity (contains) is held by the container whether or not it touches
- a fastener with a modelled solid connects only what that solid touches; one without a solid connects what it clamps to what it threads into only when its axis, over its length, is measured to reach both
- an interface between sections, or between parts with several instances, is realised by any one contact between their instances

## Limits

- `touch_mm`: 0.01
- `near_mm`: 1.0
- `overlap_mm3`: 0.001
- `max_joint_gap_mm`: 1.0
- `strict_interfaces`: false
- `nearest_candidates`: 3
