# A preassembled module has an internal sequence and a parent insertion

Do not fit its components separately in the parent merely to satisfy a one-part coverage checker. Internal assembly happens with different surrounding obstacles. Lowering a parent around a trapped component or declaring an overlap waiver is not proof that the real module can be inserted.

Use the [rigid-subassembly API](../../docs/mechanical/subassembly-insertion.md): exact, disjoint member keys; a fully checked internal plan against those live members; one parent fit of the named module. All attached fastener solids must travel with it. Parent order may refer to a module, but external fastener/tool geometry must retain real part and receiver names. A query must consider every compound member, not just its carrier or a bounding envelope that loses protruding screws.

Module service is conditional on explicit removed parent keys. Retaining fasteners cannot be silently left in place, and internal screws remain attached. The resulting clear withdrawal does not prove removal of the prerequisite bumper/retainers or their tool access. Wiring, joint strength, rigidity, physical fit and ergonomics need separate evidence.

Resolve every explicit service target before collapsing members into parent modules. A member key or owner alias cannot be forwarded to a parent view that no longer contains it; reject unsupported member teardown, unknown names and fastener-only requests before geometry. Supported parent aliases need a service check for each resolved instance. A service-enabled green verdict with no evidence for the requested operation is not qualification.

Keep a positive fixture where internal tool access clears off the parent but fails in the final surrounding base, an attached-screw-only insertion blocker, an external retainer tool blocker, and a later bumper that blocks conditional withdrawal. Structural mistakes must fail before geometry is offered as a pass. Existing single-part behavior remains a regression. See the [incident and validation](../inbox/2026-10-29-preassembly-needs-its-own-obstacle-scope.md).

Playback adds another distinct scope: its finite authored translation and exact within-step instance order.
Use the existing insertion sweep with explicit finite travel; the ordinary from-beyond-obstacles sweep can
flag a blocker which the displayed part never reaches. Matching mesh and CAD names is not geometry provenance.
Record BREP bytes, placements, guide/model/mesh hashes and source closure from the same native export, and
reject stale or absent bindings before CAD queries. Preserve blocked, unknown and budget-exhausted pairs;
an unchecked kernel relation is never a clear path. Support, retention and gravity remain explicit unknowns
until a separately justified physics scenario exists. See the [playback incident and controls](../inbox/2026-11-10-playback-needs-finite-bound-source-geometry.md)
and [public API](../../docs/practice/assembly-guide.md#validate-the-trajectories-shown-by-playback).

Recoverable native validation needs completed synchronous checkpoints, not merely callback invocation. Reject
awaitable, generator and async-generator results before queries proceed; preserve prior collisions and explicit
unchecked work when storage fails. The caller owns flushed durable progress and external run caps. See the
[lazy-callback failure and controls](../inbox/2026-11-10-lazy-callbacks-are-not-completed-checkpoints.md).
