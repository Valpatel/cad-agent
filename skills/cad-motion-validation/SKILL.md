---
name: cad-motion-validation
description: Use when implementing or reviewing articulated CAD viewers and robot simulations, especially parts orbiting away from shafts, mismatched units or frames, nested joints, and stationary housings that rotate with rotors.
---

# Validate the rendered mechanism

A CAD interference sweep does not validate a browser's scene graph. Establish independent mechanical intent,
capture the actual rendered transforms, and compare them before claiming the simulation is correct.

1. Inventory all moving joints and components, including shafts/rotors, stationary housings, feed mechanisms,
   helper geometry and scene attachments. Record ownership, units, axis handedness, home datums and parent chains
   from CAD source or inspected geometry. Do not take the expected pivots from the suspect animation manifest.
2. Read [the trace protocol](references/trace-protocol.md). Build a reference with at least four noncoplanar
   landmarks per component. Drive the real renderer using `cad-agent motion-trace reference.json --poses-only`,
   then capture actual mesh vertices through its current world matrices in the common assembly frame, in mm.
3. Run `cad-agent motion-trace reference.json capture.json --output motion-report.json`. Inspect the worst-point,
   pivot-anchor and radial errors. Compare axes to physical shaft/bearing geometry; rest-pose agreement and rigid
   within-mesh distances alone cannot catch a wrong orbit. Keep fixed housings attached to their support.
4. Add captures for firing/operation, combined independent joints, stop/start, repeated cycles and scene transitions.
   Reproduce a wrong pivot with correct home placement and require failure. Also exercise units, axis/sign,
   lost-parent and ownership errors. Keep regression checks in the existing product build/test harness.
5. Pair kinematic checks with CAD motion/containment gates and visual inspection of the actual published renderer.
   Record input/export hashes, tolerance, sample density, untested events and independent reference provenance.
   A passing trace says nothing by itself about continuous clearance, loads, physical fit or hardware safety.

Use the repository's normal independent review and deployment process. This skill adds no publication permission.
