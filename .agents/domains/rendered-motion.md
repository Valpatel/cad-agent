# Rendered motion must be compared with independent joint intent

The CAD motion/interference gate and a renderer-transform check cover different systems. A viewer can preserve
rest placement and all within-mesh distances while rotating about the wrong axis. Browser/exported pivots must
therefore be checked against CAD source datums or independently inspected geometry, not against themselves.

The maintained procedure and schema are [docs/mechanical/rendered-motion.md](../../docs/mechanical/rendered-motion.md); use the
[cad-motion-validation skill](../skills/cad-motion-validation/SKILL.md). `cadagent.mechanical.motion_trace` compares
captured landmarks, enforces coverage, reports pivot/radius drift and binds both input documents with hashes. Its seeded
negative tests run in the normal pytest CI. Product-specific captures and geometric reference evidence stay in
the product repository.

A pass covers the declared components and sampled poses under the stated tolerance. It does not certify reference
truth, actual hardware, complete mesh geometry, continuous motion or collision clearance.


A source-bound renderer must validate the original instance/mesh partition list **before** creating any name-keyed
hash, pose or mesh map. Require unique exact IDs even when duplicate entries reference the same geometry;
map key equality cannot prove original-list uniqueness. The producer and actual consumer must reject the same
invalid population before output replacement or geometry allocation. See the
[duplicate-partition incident and regression](../inbox/review/2026-11-12-source-partitions-need-pre-map-uniqueness.md).


Native motion/assembly tests must reach their optional dependency guard before importing that dependency.
Check missing-extra behavior in an isolated process as well as the real installed CAD path; a CAD-enabled
pass cannot verify core absence. Preserve failed hosted instances separately from fresh source checks
([observed core failure](../inbox/review/2026-11-12-native-tests-need-optional-import-boundaries.md)).
