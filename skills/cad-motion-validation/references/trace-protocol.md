# Rendered joint motion validation

`cad-agent motion-trace` compares actual renderer landmarks with independent mechanical intent. It complements
`cad-agent gates --only motion`: that gate poses CAD bodies and checks interference; it does not execute a
browser's scene graph or verify how exported meshes were recentered.

## Reference and capture

Keep two independent paths. Derive the reference axes, home landmarks and component ownership from CAD source
or inspected geometry. Capture observations by applying the actual scene's world matrices to actual mesh vertices.
Do not generate observed points with the validator, and do not reuse a suspect animation manifest as the oracle.
Record the source revision and export hashes in `reference` and `capture_source`, with the full capture procedure in
the product repository. Content SHA-256 hashes of both JSON inputs are included in the report.

An axis passing through the origin, a symmetric wheel, or a screenshot at zero degrees can conceal a pivot error.
Use offset datums, landmarks on and off the shaft, all moving components, and stationary housings. A motor housing
belongs to the support's joint, while its rotor may belong to a shaft joint. Names alone cannot establish ownership.

Contract JSON (the example is one shaft and a fixed mount):

```json
{
  "schema_version": 1,
  "length_unit": "mm",
  "frame": "assembly-home",
  "reference": "CAD revision and source datum/mesh hashes recorded here",
  "joints": {
    "shaft": {"parent": null, "pivot": [40, 20, 30], "axis": [1, 0, 0], "range_deg": [0, 360]}
  },
  "components": {
    "rotor": {"joint": "shaft", "points": [[40, 20, 30], [41, 20, 30], [40, 22, 30], [40, 20, 33]]},
    "mount": {"joint": null, "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]}
  }
}
```

Every joint's pivot and axis, and every home landmark, use the **same assembly home frame**. Parent axes carry
child axes as the parent turns; child pivots are not parent-local offsets. Matrices compose as
`parent_motion × rotation_about_home_axis`. Each range is increasing and includes zero, the CAD as-modelled
pose. Rotations are right-handed degrees; axes are normalized. `parent` and component `joint` are explicit,
including `null`. Every joint must carry captured components, directly or through descendants.

Each component needs at least four affinely independent (noncoplanar) ordered landmarks. For a solid, select
actual mesh vertices spanning three dimensions and include extreme/shaft-adjacent points. Four landmarks identify
a rigid transform; additional vertices expose geometry/deformation errors. A zero-thickness surface needs
independent frame markers to constrain the missing dimension; mark that evidence limitation. Bounding-box corners
are valid frame probes only when transformed by the actual object's matrix, and do not validate the mesh shape.

Capture JSON:

```json
{
  "schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
  "capture_source": "renderer revision, export hashes and capture procedure",
  "samples": [
    {"id": "home", "angles_deg": {"shaft": 0}, "components": {
      "rotor": [[40, 20, 30], [41, 20, 30], [40, 22, 30], [40, 20, 33]],
      "mount": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    }}
  ]
}
```

This one-sample example intentionally fails coverage. Generate all required input poses:

```sh
cad-agent motion-trace reference.json --poses-only --output poses.json
# Drive the real renderer with poses.json and write capture.json.
cad-agent motion-trace reference.json capture.json --tolerance-mm 0.01 --output motion-report.json
```

The command needs no project config or CAD extra. Python callers use
`cadagent.mechanical.motion_trace.required_poses(contract)` and
`cadagent.mechanical.motion_trace.validate_motion_trace(contract, trace)`. Exit 0 means all supplied landmarks match and
required poses are present; exit 1 means mismatches or incomplete coverage; exit 2 means malformed/unreadable evidence.
A failed/malformed command must fail the calling build step.

Convert observations explicitly from renderer units and world coordinates to reference mm and assembly-home
coordinates. Remove only the known scene placement/basis conversion, retaining all articulated movement. Use
actual applied joint state, not merely requested controls. Force world matrices current before reading them;
capture after load/animation settling. Disable explosions only for normal assembly checks, then separately verify
explosion reset. Record all joints and all components in every sample, in the same landmark order.

## Coverage and diagnosis

Required poses include home, each joint's limits and at least three interior values with no gap over 90 degrees,
and non-home ancestor/child combinations. Multi-turn ranges cannot alias every required pose to full turns.
Ranges needing more than 4096 intervals are rejected: test bounded cycles. Add simultaneous independent-joint
motion, real firing, stop/start, repeated cycles, stage transitions and emergency recovery captures as applicable.
The minimum protocol cannot decide which application events or simultaneous loads matter.

The report gives the worst point error, sample and point index for every component, plus inferred pivot-anchor
drift and radial drift. A fixed housing must match its parent's transform; a rotor must remain on its declared
axis while its off-axis landmarks turn. The verdict compares full expected positions, so a wrong axis can fail
even when distances within the mesh and its shaft point remain constant. Anchor/radius metrics diagnose errors;
they do not replace the full comparison.

Choose the position tolerance before inspecting results, based on export precision and expected error scale.
The default is 0.01 mm; it is not a universal manufacturing tolerance. Tighten the sample spacing where geometry
or clearance requires it, and retain the CAD motion/containment checks. A sampled kinematic match does not prove
continuous collision clearance, dynamic forces, speed, timing, physical fit, or hardware safety.

## Regression proof

Break the renderer deliberately and demonstrate the check fails: offset a pivot while preserving home placement,
change an axis/sign, lose a parent, spin a stationary housing, and introduce a unit/basis mismatch. Restore the
correct implementation and retain the negative test. `tests/test_motion_trace.py` exercises these classes with an
independent analytic fixture; product tests must also capture their actual exported geometry and renderer.
