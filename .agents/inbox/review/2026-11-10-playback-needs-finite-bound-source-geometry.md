# Playback paths need finite travel and source geometry before an assembly claim

Date: 2026-11-10. Context: extending the existing ordered guide player and assembly access gate (#512).

## Evidence

The existing `sweep_pair` starts beyond each obstacle. The browser player translates a single exact instance
from its authored offset to zero, and installs earlier arrivals within the same step before the next arrival.
The product collection binds STL bytes and source inputs but contains no serialized BREP identity. A same-named
replacement CAD solid therefore cannot establish that the displayed geometry was checked.

Bounded regression command (2026-11-10; existing CAD environment, owned source on `PYTHONPATH`):

```text
python3 -m pytest -q tests/review/test_gate_assembly.py -k 'finite_playback or playback'
22 passed, 24 deselected in 3.46s
```

The analytic fixture puts a distant blocker at X=8..9 and an arriving part at X=0..1. The ordinary -X insertion
starts beyond the blocker and fails; finite travel 3 mm has a whole-path box gap bound of 4 mm and clears.
A three-part side-insertion fixture fails when the blocker precedes the insert and clears after the explicitly
authored order is reversed. The real BREP fixture exports the actual meshes from the same in-memory shapes
and exercises both reports. Original failure evidence remains separate from the corrected report.

Inspection also found `Relation.state == "unchecked"` could fall through the old sweep's unknown-only branch
and become a clear answer when no gap was available. The new regression seeds unchecked at the seat and
on the path; both retain unchecked state. Query exceptions retain earlier collision findings as well.

## Cause and corrective rule

Presentation order and explode offsets are not a mechanical plan by themselves. Use the existing path engine
with an explicitly bounded path, exact within-step order and complete instance coverage. Emit BREP payloads,
placements and hashes beside the guide meshes from the same source shapes; verify those frozen bytes before
queries. Keep missing provenance, unknown kernel answers and exhausted sample budgets visible. A binding
records the exporter's CAD-to-mesh correspondence declaration; hashes do not prove tessellation equivalence.

## Limits

The first adapter checks rigid finite straight translations and final overlap against prior instances, with
the existing near-contact sample limitations. It has no inferred overlap exemption, internal compound plan,
fastener/tool proof, tolerance stack or physical qualification. Support, fixture retention and gravity are
unknown until explicit, source-bound physics inputs justify their own check. Native product export and long
validation runs use a compute host; this bounded fixture result is not a whole-robot clearance result.

## Independent review: hashes alone did not reject an inconsistent placement

On 2026-11-10 an independent reviewer ran the real fixture, retained its blocked result, then changed only
`binding["instances"]["insert"]["matrix"][3] += 100`. The initial adapter reported a pass despite unchanged
guide, mesh and BREP bytes ([review](https://github.com/Valpatel/cad-agent/pull/513#discussion_r4526495305)).
The check had moved the CAD away from the displayed geometry. The correction compares located exact CAD,
actual captured STL vertices and model bounds before path queries, with a bounded explicit tessellation
allowance. A stale-shift and a double-applied-placement mutant must both fail. This is a gross frame screen,
not proof of shape/tessellation equivalence; the original producer declaration remains a stated limit.
