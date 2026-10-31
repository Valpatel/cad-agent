# Rendered motion must be compared with independent joint intent

The CAD motion/interference gate and a renderer-transform check cover different systems. A viewer can preserve
rest placement and all within-mesh distances while rotating about the wrong axis. Browser/exported pivots must
therefore be checked against CAD source datums or independently inspected geometry, not against themselves.

The maintained procedure and schema are [docs/rendered-motion.md](../../docs/rendered-motion.md); use the
[cad-motion-validation skill](../../skills/cad-motion-validation/SKILL.md). `cadagent.sim.motion_trace` compares captured
landmarks, enforces coverage, reports pivot/radius drift and binds both input documents with hashes. Its seeded
negative tests run in the normal pytest CI. Product-specific captures and geometric reference evidence stay in
the product repository.

A pass covers the declared components and sampled poses under the stated tolerance. It does not certify reference
truth, actual hardware, complete mesh geometry, continuous motion or collision clearance.
