**New**
- `cadagent.mechanical.clearance`: a range-of-motion collision check. `collisions(instances)` intersects every pair of
  placed solids whose bounding boxes overlap and reports pairs overlapping by more than `tolerance_mm3` (2 mm³ by
  default), with `skip` for intended overlaps and `only` to limit the check; a boolean that fails is reported as an
  error, never as a pass. `sweep(poses, place_fn)` runs it at every named pose and writes a check JSON with a
  top-level `pass` and `physical_fit_verified: false`. `swept_envelope(pieces)` builds a revolved swept-volume cutter
  with slopes capped at 45°, as one revolve (no flat ceilings, no many-tool fuse). Poses are samples, not a
  continuous sweep (docs/toolkit.md, #251).
