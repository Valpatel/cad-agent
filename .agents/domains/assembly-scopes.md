# A preassembled module has an internal sequence and a parent insertion

Do not fit its components separately in the parent merely to satisfy a one-part coverage checker. Internal assembly happens with different surrounding obstacles. Lowering a parent around a trapped component or declaring an overlap waiver is not proof that the real module can be inserted.

Use the [rigid-subassembly API](../../docs/subassembly-insertion.md): exact, disjoint member keys; a fully checked internal plan against those live members; one parent fit of the named module. All attached fastener solids must travel with it. Parent order may refer to a module, but external fastener/tool geometry must retain real part and receiver names. A query must consider every compound member, not just its carrier or a bounding envelope that loses protruding screws.

Module service is conditional on explicit removed parent keys. Retaining fasteners cannot be silently left in place, and internal screws remain attached. The resulting clear withdrawal does not prove removal of the prerequisite bumper/retainers or their tool access. Wiring, joint strength, rigidity, physical fit and ergonomics need separate evidence.

Keep a positive fixture where internal tool access clears off the parent but fails in the final surrounding base, an attached-screw-only insertion blocker, an external retainer tool blocker, and a later bumper that blocks conditional withdrawal. Structural mistakes must fail before geometry is offered as a pass. Existing single-part behavior remains a regression. See the [incident and validation](../inbox/2026-10-29-preassembly-needs-its-own-obstacle-scope.md).
