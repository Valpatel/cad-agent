# A preassembled module has an internal sequence and a parent insertion

Do not fit its components separately in the parent merely to satisfy a one-part coverage checker. Internal assembly happens with different surrounding obstacles. Lowering a parent around a trapped component or declaring an overlap waiver is not proof that the real module can be inserted.

Use the [rigid-subassembly API](../../docs/mechanical/subassembly-insertion.md): exact, disjoint member keys; a fully checked internal plan against those live members; one parent fit of the named module. All attached fastener solids must travel with it. Parent order may refer to a module, but external fastener/tool geometry must retain real part and receiver names. A query must consider every compound member, not just its carrier or a bounding envelope that loses protruding screws.

Module service is conditional on explicit removed parent keys. Retaining fasteners cannot be silently left in place, and internal screws remain attached. The resulting clear withdrawal does not prove removal of the prerequisite bumper/retainers or their tool access. Wiring, joint strength, rigidity, physical fit and ergonomics need separate evidence.

Resolve every explicit service target before collapsing members into parent modules. A member key or owner alias cannot be forwarded to a parent view that no longer contains it; reject unsupported member teardown, unknown names and fastener-only requests before geometry. Supported parent aliases need a service check for each resolved instance. A service-enabled green verdict with no evidence for the requested operation is not qualification.

Keep a positive fixture where internal tool access clears off the parent but fails in the final surrounding base, an attached-screw-only insertion blocker, an external retainer tool blocker, and a later bumper that blocks conditional withdrawal. Structural mistakes must fail before geometry is offered as a pass. Existing single-part behavior remains a regression. See the [incident and validation](../inbox/2026-10-29-preassembly-needs-its-own-obstacle-scope.md).

Stage support is a separate scope from insertion and contact. A fixed or zero-gravity model can look stable
without any supporting fixture. Require explicit free rigid groups and declared fixed primitive fixtures,
retain maximum drift/rotation and terminal speeds, and require a force-bearing contact path to support.
Reject hidden retention/gravity compensation, callbacks and solver resets as stability proof. Preserve model
bytes, effective settings and timestep controls; a robust pass/fail classification is not a converged transient.
See the [stage physics evidence and limits](../inbox/2026-11-10-stage-stability-needs-free-gravity-and-support.md).

A complete settling window includes the initial `mj_forward` state, before contact relaxation. Collision masks
do not cover explicit MJCF pairs, and captured child XML can itself import ambient files. The first rigid-stage
API rejects explicit pairs and nested model assets/attachments before compilation; do not count mask-only or
top-level hash coverage as a complete physics/input boundary. Keep concrete negative fixtures for all three
independent [false-pass controls](../inbox/2026-11-10-stage-stability-needs-free-gravity-and-support.md#independent-review-found-three-false-passes-inside-the-first-contract).

Native collider coverage must include object classes: deformable/flex contacts are not ordinary rigid geoms.
Reject unsupported flexes and non-geom/negative contact IDs before looking up a part or support path; Python
index `-1` otherwise aliases the last object. Keep the actual [fixed-flex support regression](../inbox/2026-11-10-stage-stability-needs-free-gravity-and-support.md#collider-coverage-includes-object-classes-not-only-rigid-geom-masks).
