**New**
- `cadagent.mechanical.clearance`: a range-of-motion collision check. `collisions(instances)` relates every pair of
  placed solids whose bounding boxes meet with the relation gate's exact narrow phase (`relate`) and reports pairs
  overlapping by more than `tolerance_mm3` (2 mm³ by default), with `skip` for intended overlaps and `only` to limit
  the check; a pair the gate cannot decide is an error, never a pass. `sweep(poses, place_fn)` runs it at every named
  pose and writes a check JSON with a top-level `pass` and `physical_fit_verified: false`; with `travel_mm` it also
  proves each pair clear between consecutive poses by the gap bound `(g1 + g2 - travel) / 2`, or fails the step.
  `swept_envelope(pieces)` builds a revolved swept-volume cutter with slopes capped at 45°, as one revolve (no flat
  ceilings, no many-tool fuse). Contributed by Jeff Patrick (docs/toolkit.md, #251).
