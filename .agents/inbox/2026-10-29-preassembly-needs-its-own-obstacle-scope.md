# Preassembly needs its own obstacle scope, not an invented parent order

On 2026-10-29, a serviceable electronics carrier exposed the v0.4.0 assembly checker's one-part `fit`/`first_fit` limitation. The board, carrier, inserts and inward screws assemble off the parent, then move rigidly into it. Flattening that into parent steps either checks internal tools inside the trapping base or lowers the base around a module that must actually enter through its opening. Neither proves the intended assembly sequence.

The generic correction (issue #68 / PR #69) executes an internal plan against only the module's exact member geometry, then translates every member together through the parent path. Internal fasteners are not re-driven. Parent retainer ordering may use the module identity, but the actual tool query receives the original fastener declaration and real member/receiver names. Compound member relations retain the blocking member pair; no whole-module overlap waiver is accepted.

Initial focused command evidence on 2026-10-29, before the final disabled-tool and conditional-removal guards:

```text
$ PYTHONDONTWRITEBYTECODE=1 <CAD-environment>/bin/python -m pytest -q tests/test_gate_subassembly.py tests/test_gate_assembly.py tests/test_gate_fasteners.py
103 passed in 25.04s
```

The BREP positive fixture passes the internal screw tool sweep on the bench; explicitly querying the same screw/tool against the final base reports a blocked path. A second fixture makes only the attached screw head hit an entry lip and checks that the parent insertion fails with `member_pair = [board_screw, lip]`. A third keeps insertion clear but blocks the external retainer tool with a parent guard. These distinguish assembly scope and full membership from a bounding-box-only or carrier-only approximation.

The heat-set fixture initially inserted the insert after the board and correctly failed on the board. Moving the insert before the board fixes the actual order; the explicit insert/carrier overlap declaration does not waive collisions with other members. This is why scoped preassembly still needs a complete internal sequence.

`service_after` reports a reverse-path check after named parent items are assumed removed. It records `prerequisite_removal_verified = false` and `prerequisite_tool_access_verified = false`; retainers must be listed and internal screws remain in the moving module. Do not relabel that conditional result as a proven teardown plan. Product harness disconnection/slack remains unverified when not modelled.

The feature uses live geometry in one call, not a caller-supplied “passed” boolean or stale receipt. Project environments were not reinstalled: pytest selects this owned worktree's `src`, and an explicit `PYTHONPATH=src` import check resolved the feature checkout. The fixtures are small local BREP checks, not a product CAD/FEA solve. Full product validation remains separate, and neither sequence proof nor a rigid-body assumption establishes printed fit, joint strength or hardware readiness.

Final local checks on 2026-10-29: the complete kernel-free suite passed 801 tests with 166 optional-dependency skips in 35.36 s; the new subassembly suite in the CAD environment passed all 36 tests (including four BREP fixtures) in 3.66 s. Current-head CI and independent review remain separate release gates.

## Service requests must survive a change of assembly scope

Independent review of `3e2af8c` found a second scope error: `assembly_gate(..., subassemblies=modules, service=["board"])` in the small BREP fixture returned `pass=true`, `limits.service=true`, no service checks and no findings. The board and carrier had been replaced by the module in the parent world, but their requested service names were still forwarded to that world and silently ignored. The same result was reproduced for `service=["carrier"]`; requesting the module name itself already failed without prerequisites.

The correction validates every explicit target before any geometry check. Member keys/owner aliases, unknown targets and fastener-only requests fail as unsupported; a member-removal request is not silently converted into whole-module withdrawal. Valid parent aliases resolve to exact instances with individual service checks, and `service=True` retains parent-part plus explicitly conditional module evidence. Kernel-free regressions assert no geometry/tool calls for rejected targets; BREP regressions assert the verdict fails instead of reporting service enabled with no findings. This is limited to the new scoped API; existing single-part semantics remain unchanged, and internal member teardown still needs a separately supported operation.

Correction validation on 2026-10-29: the complete kernel-free suite passed 820 tests with 172 optional-dependency skips in 28.08 s. The CAD-enabled `tests/test_gate_subassembly.py tests/test_gate_assembly.py tests/test_gate_fasteners.py` run passed all 133 tests in 26.22 s. These are local regression results; current-head CI and independent recheck are still required.
