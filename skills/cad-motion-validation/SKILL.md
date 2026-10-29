---
name: cad-motion-validation
description: Use when implementing or reviewing articulated CAD viewers and robot simulations, especially parts orbiting away from shafts, mismatched units or frames, nested joints, and stationary housings that rotate with rotors.
---

# Validate the rendered mechanism

A CAD interference sweep does not validate a browser's scene graph. Establish independent mechanical intent,
capture the actual rendered transforms, and compare them before claiming the simulation is correct.

The reference must come from CAD source datums or independently measured geometry. Reusing a suspect viewer
manifest's pivots for both the animation and its expected output can make the same defect pass twice.

Implementation and trace protocol are being added in this branch; do not treat this initial checkpoint as a
completed validation tool. The completed workflow must include deliberate wrong-pivot, axis, units, parent and
component-ownership failures and state the difference between sampled kinematic evidence and physical validation.
