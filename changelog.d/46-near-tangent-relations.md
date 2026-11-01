**Fixed**
- `cadagent.review.gates.relations.relate`: a shallow near-tangent crossing that OCCT's boolean misses is no longer
  read as `touching` or `contains`. Where the two boundaries meet, the curves found by `BRepAlgoAPI_Section` guide
  samples that are classified against the other solid. A crossing outside the kernel's own common or cut makes the
  pair `unknown`, with the point and depth in `witness["crossing_probe"]`. A 4 mm ball 0.011–0.23 mm through a cone
  wall had read `contains` or `touching` at 24 of 500 positions (#46).
- Containment gate: an instance whose relation finds such a crossing fails as an escape, with the depth found.

**Projects must change**
- `RELATIONS_VERSION` is now 5, so cached relations (`.cadagent-cache/gates/`) and the containment gate's cached
  checks recompute on the next run. A pair that crossed where the kernel saw no crossing now reads `unknown`, and
  every gate fails on it; nudge the parts apart or into a clear overlap. No answer changed on the README hero's
  811-pair sweep or the gate bench.
