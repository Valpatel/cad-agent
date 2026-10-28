# Integrity gates (`cadagent.gates`)

Assembly-level checks computed from the CAD model, each written as one verdict file. They answer what per-part
checks cannot: is this part touching the one it should be fastened to, is the ball inside the hopper, is this wall
thick enough. The design behind them is [`design-process-plan.md`](design-process-plan.md) §4.

**What a gate does not do.** A gate checks the model against declared intent with stated tolerances. It does not
prove that printed parts fit, move or hold: no tolerance stack, no print shrink, no deflection. Every verdict says
`physical_fit_verified: false` and lists its assumptions.

Status: the shared machinery (T3), the minimum-wall gate (T8) and the gate bench (T12) are built. Connectivity (T4),
containment (T5), fasteners (T6), motion (T7), assembly access (T9) and the dossier lint (T2) build on them.

## The relation table

```python
from cadagent.gates import Assembly, Tolerances, PairCache, relation_table, relate

asm = Assembly()
asm.add("base", base)                                   # CadQuery / build123d shape or TopoDS_Shape
asm.add("arm", arm, location=(40, 0, 12), body="arm", group="S2")
asm.add("lid", lid, cq.Location(...))                   # or a gp_Trsf, TopLoc_Location, 3x4/4x4 rows
asm = Assembly({"base": base, "lid": lid})              # or a mapping of shapes already placed
asm = Assembly.from_cadquery(cq_assembly)               # parts named by path, bodies by top-level child

table = relation_table(asm, Tolerances(), cache=PairCache(".cadagent-cache/gates"))
table.get("lid", "base")            # Relation, oriented as asked; broad-phase-only pairs come back
                                    # apart with exact=False and gap_lower_bound_mm
table.get("lid", "far", exact=True) # run the kernel for a pair the broad phase skipped
table.contacts()                    # touching + overlapping + contains: the contact-graph edges
table.by_state("overlapping")
table.of("lid")                     # every exact relation of one part, with it as `a`
table.stats                         # parts, pairs, candidates, kernel_queries, cache_hits, seconds, states
table.to_dict()                     # JSON-ready evidence

relate(ball, cavity_solid)          # one exact pair, no broad phase or cache (a part against a cavity)
asm.posed("arm", location)          # a copy with one body moved (the motion gate's poses)
```

### States

Following build123d-mcp's `clearance` (Apache-2.0, vendored; semantics adapted, no code copied):

| State | Meaning | Witness |
|---|---|---|
| `apart` | no shared volume, gap > `touch_mm` | `gap_mm`, closest points `point_a`, `point_b` |
| `touching` | no shared volume, gap ≤ `touch_mm` | as apart, plus `contact_area_mm2` (0 for point or line contact, and for a gap inside `touch_mm`) |
| `overlapping` | shared volume, neither inside the other | `overlap_mm3`, `a_outside_b_mm3`, `b_outside_a_mm3`, `overlap_centroid`, `overlap_box` |
| `contains` | one part has at most `contain_mm3` outside the other | as overlapping, plus `contained` (`a_in_b`, `b_in_a`, `both`), `wall_mm` and its `inner_point`, `outer_point` |
| `unknown` | the kernel failed on the pair (`error` says how) | a gate must fail on it, never read it as apart |

### Tolerances (absolute)

| Field | Default | Meaning |
|---|---|---|
| `touch_mm` | 0.01 | a gap at or below this, with no shared volume, is touching |
| `overlap_mm3` | 0.001 | shared volume above this is an overlap (a 0.1 mm cube) |
| `contain_mm3` | 0.001 | a part with no more than this outside the other is inside it; a ball resting on a cavity wall has exactly 0 outside |
| `near_mm` | 1.0 | broad-phase margin: pairs whose boxes are within this get exact queries, so a 0.5 mm hover is measured |

### Method and cost

AABB broad phase (`BRepBndLib.AddOptimal`, numpy over all pairs), then for each candidate `BRepAlgoAPI_Common`
(run non-destructive, so the caller's shapes are never modified) for the shared volume and
`BRepExtrema_DistShapeShape` for the gap. Measured with `tools/gate_timing.py` on the synthetic 100-part assembly
(4,950 pairs, 90 candidates) on a loaded workstation: broad phase 0.012 s, narrow phase 1.3–1.5 s cold, 0.03 s
warm from the cache. Real parts with hundreds of faces cost 10–100× more per pair.

### The pair cache

`PairCache(directory)` stores one JSON file per pair, keyed by the sha256 of both parts' content hashes, the
tolerances and the relation version. A part's content hash is `shape_hash(shape)` (sha256 of the BREP text without
triangulation and with the kernel's state flags stripped) plus its placement matrix rounded to 1e-9, so a rebuild
that moves or changes one part re-queries only that part's pairs, across processes. OCP's own `TopoDS_Shape` hash is
identity-based and cannot be used. Keep the cache out of `exports/`: the default is `.cadagent-cache/gates/`, which
is gitignored; deleting it is always safe.

## Verdicts

```python
from cadagent.gates import Check, verdict, write_verdict

checks = [Check("wall:hopper", "fail", "thinnest 0.800 mm < 2.4 mm", parts=["hopper"], evidence={...})]
data = verdict("wall", checks, assumptions=["rays along the inward normal ..."], limits={"tol_mm": 0.01},
               exclusions=[{"parts": ["insert_0", "hopper"], "reason": "heat-set knurl"}])
write_verdict("exports/gates/wall.json", data)
```

The file (`schema: cadagent.gate/1`) has `pass`, `status` (`pass`/`warn`/`fail`), `counts`, `checks`, `findings`
(the checks that are not pass), `exclusions`, `limits`, `assumptions` and `physical_fit_verified: false`. `pass` is
false when any check fails **or when no check ran**. Warnings never fail the gate. At least one assumption is
required, every exclusion needs a reason, and the file has no timestamp, so an unchanged run writes identical bytes.
Point a `cad.checks` entry at the file to put it in the report.

## Minimum wall (`cadagent.gates.wall`)

```python
from cadagent.gates.wall import check_wall, wall_gate, mesh_thickness, brep_thickness

check_wall("hopper", 2.4, mesh=shape_or_stl_or_trimesh, shape=brep)           # -> Check
wall_gate({"hopper": {"wall_mm": 2.4, "mesh": m, "shape": s}, ...}, out="exports/gates/wall.json")
```

Two samplers measure thickness by rays along the inward surface normal:

- **mesh rays** from every triangle centroid (sub-sampled by area to `max_rays`, seeded), using trimesh with
  `rtree` or an exact numpy fallback;
- **exact B-rep rays** from a `grid` × `grid` UV sample on every face, so a small face is probed whatever its area.

A check fails when any sample is thinner than `wall_mm - tol_mm` (default 0.01 mm), when the mesh is not
watertight, or when more than 1 % of rays find no exit. The evidence holds per-sampler summaries (min, p1/p5/p50,
thin samples and area) and up to ten witnesses: the entry point, the exit point and the thickness. Pass both the
mesh and the shape where you can; they miss different things. The threshold is the part's own (the dossier's
`material.wall_mm` once T1 lands; a plain number now). Limits: walls met at a slant and regions between samples are
not measured; a curved wall's mesh reading is low by up to the chord deviation, which the B-rep rays do not have.

## The gate bench (`tests/fixtures/gate_bench/build.py`)

A generic mechanism (a base, a hopper with a declared cavity and eight loose balls, a board, a lid held by four
screws into heat-set inserts, a bracket on a boss, an arm on a pin with a stop and an overhead frame) with its
declarations as plain data, and the plan's ten seeded defects (`SEEDS`). `tests/test_gate_bench.py` runs every gate
on the clean bench (no finding allowed) and every seed (its gate must fail with a finding that names the seeded
part). A gate not built yet has an adapter that raises `NotImplementedError` and strict-xfail cases; its implementer
writes the adapter and removes the mark. `dossier_items(bench)` is the hook for the dossier registry (T13).

## Where this differs from the plan

- **Cache location and key**: `.cadagent-cache/gates/` (gitignored), not `exports/gates/cache/`; content hash of the
  BREP text, not OCP's identity hash.
- **Containment tolerance**: absolute (`contain_mm3`), not 1e-6 relative.
- **Wall probe**: exact B-rep rays replace the negative-offset probe. `BRepOffsetAPI_MakeOffsetShape` by −t/2
  returned a shell or a null shape on a 0.8 mm rib and on a 2.4 mm-walled box, the cases it was meant for.
- **Derived cavities** ("convex hull minus part") are not a B-rep operation; containment takes a declared cavity
  solid (the bench declares `hopper_cavity`).
- **Seed harness file**: `tests/test_gate_bench.py` (pytest only collects `test_*.py`), fixture directory
  `gate_bench` (importable name).
