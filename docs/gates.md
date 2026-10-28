# Integrity gates (`cadagent.gates`)

Assembly-level checks computed from the CAD model, each written as one verdict file. They answer what per-part
checks cannot: is this part touching the one it should be fastened to, is the ball inside the hopper, is this wall
thick enough. The design behind them is [`design-process-plan.md`](design-process-plan.md) §4; the declarations
they read come from the dossier ([`dossier.md`](dossier.md)).

**What a gate does not do.** A gate checks the model against declared intent with stated tolerances. It does not
prove that printed parts fit, move or hold: no tolerance stack, no print shrink, no deflection. Every verdict says
`physical_fit_verified: false` and lists its assumptions.

Status: the shared machinery (T3), the minimum-wall gate (T8), the connectivity gate (T4), the containment gate (T5),
the gate bench (T12) and the dossier lint (T2, [`dossier.md`](dossier.md#lint-and-status)) are built, and so is the
motion gate (T7). Fasteners (T6) and assembly access (T9) build on them.

## The assembly and the relation table

```python
from cadagent.gates import Assembly, Tolerances, PairCache, relation_table, relate_pair, relate

asm = Assembly.from_build(build_result)                 # from a dossier build (live or load_geometry): see below
asm = Assembly()                                        # or by hand:
asm.add("base", base)                                   # CadQuery / build123d shape or TopoDS_Shape
asm.add("arm", arm, location=(40, 0, 12), body="arm", group="S2")
asm.add("lid", lid, cq.Location(...), content_hash=recorded)  # placement: Location, gp_Trsf, TopLoc, 3x4/4x4 rows
asm.add_cavity("hopper_cavity", void, part="hopper")    # a declared void: not a part, never in the pair table
asm = Assembly({"base": base, "lid": lid})              # or a mapping of shapes already placed
asm = Assembly.from_cadquery(cq_assembly)               # parts named by path, bodies by top-level child

table = relation_table(asm, Tolerances(), cache=PairCache(".cadagent-cache/gates"))
table.get("lid", "base")            # Relation, oriented as asked (see "Pairs the table did not examine")
table.get("lid", "far", exact=True) # run the kernel for a pair not yet examined
table.contacts()                    # touching + overlapping + contains: the contact-graph edges
table.interferences()               # overlapping + contains: shared volume
table.of("lid")                     # every exact relation of one part, with it as `a`
table.stats                         # parts, pairs, candidates, kernel_queries, cache_hits, seconds, states
table.to_dict()                     # JSON-ready evidence, with the kernel version

relate_pair(asm, "ball#3", "hopper_cavity", cache=cache)   # one named pair (parts or cavities), cached
relate(shape_a, shape_b)            # two bare shapes, uncached
asm.posed("arm", location)          # a copy with one body (and its cavities) moved; static parts untouched
```

A multi-solid part whose solids share volume is refused by `Assembly.add` (fuse it first): the boolean kernel
reports the common of such a compound with anything as done and empty. `solid_interference(shape)` lists the
offending solid pairs.

### From a dossier build

`Assembly.from_build(result)` takes a `cadagent.dossier` `BuildResult`, from the build itself or from
`load_geometry("exports/dossier-geometry.json")` in another process:

- parts and placed fasteners from `assembly_shapes(with_hashes=True)`, already in assembly coordinates, keyed as
  the build keys them (`"hopper"`, `"ball#3"`, `"screw_0"`), each with the **content hash recorded at build time**;
  a shape read back from BREP is never re-hashed, so the pair cache stays warm across processes;
- `Part.kind` from `result.kind(key)` (`"part"` or `"fastener"`) and `group` = the part's section;
- every cavity through `add_cavity`, with its recorded hash;
- `asm.joints` and `asm.fastener_axes` copied from the result for the motion and fastener gates;
- body labels from `moving_bodies(joints, fasteners, grounded)` (the rule is final; see the motion gate): a joint's
  `moving` part seeds its body, which grows transitively across `fixed` joints and fasteners (the fastener, what it
  clamps and what it threads into), never into a grounded part or a joint's `fixed` part.

### States

Following build123d-mcp's `clearance` (Apache-2.0, vendored; semantics adapted, no code copied):

| State | Meaning | Witness |
|---|---|---|
| `apart` | no shared volume, gap > `touch_mm` | `gap_mm`, closest points `point_a`, `point_b` |
| `touching` | no shared volume, gap ≤ `touch_mm` | as apart, plus `contact_area_mm2` (0 for point or line contact, and for a gap inside `touch_mm`) |
| `overlapping` | shared volume, neither inside the other | `overlap_mm3`, `a_outside_b_mm3`, `b_outside_a_mm3`, `overlap_centroid`, `overlap_box` |
| `contains` | one item has at most `contain_mm3` outside the other | as overlapping, plus `contained` (`a_in_b`, `b_in_a`, `both`), `wall_mm` and its `inner_point`, `outer_point` |
| `unknown` | the kernel failed, or its volumes disagreed (`error` says which) | a gate must fail on it |
| `unchecked` | from `get()` only: a pair excluded by `only=` or `skip_pairs` whose boxes do not prove a gap | a gate must fail on it or ask `exact=True` |

**`contains` between two parts is an interference.** A pin buried in a block is `contains`, not `overlapping`;
`Relation.interferes` and `table.interferences()` cover both. Only against a declared cavity solid is `contains`
the goal (the containment gate); between parts it needs an intended-overlap declaration like any other overlap.

### Tolerances (absolute)

| Field | Default | Meaning |
|---|---|---|
| `touch_mm` | 0.01 | a gap at or below this, with no shared volume, is touching |
| `overlap_mm3` | 0.001 | shared volume above this is an overlap (a 0.1 mm cube) |
| `contain_mm3` | 0.001 | an item with no more than this outside the other is inside it; a ball resting on a cavity wall has exactly 0 outside |
| `near_mm` | 1.0 | broad-phase margin: pairs whose boxes are within this get exact queries, so a 0.5 mm hover is measured |
| `volume_check_mm3` | 0.01 | allowed disagreement in `vol = common + cut` (plus 1e-6 of the larger volume) before a pair is `unknown` |

### Method, fail-safe rules and cost

AABB broad phase (`BRepBndLib.AddOptimal`, numpy over all pairs). For each candidate: `BRepAlgoAPI_Common` for the
shared volume and `BRepAlgoAPI_Cut` for each item's volume outside the other, all non-destructive (OCCT otherwise
raises the arguments' tolerances in place, changing the caller's shapes), then `BRepExtrema_DistShapeShape` for the
gap when nothing is shared.

OCP 7.9 binds no error report on these operations (`HasErrors` is absent; `DSFiller()` reports warnings but crashes
the interpreter at exit), and `IsDone()` stays true on invalid input. So every answer is cross-checked:
`vol(a) = common + cut(a, b)`, and the same for `b` when they overlap. A mismatch, an exception, a missing solid or a
self-interfering compound gives `unknown`, never `touching`, `apart` or `contains`.

Measured with `tools/gate_timing.py` on the synthetic 100-part assembly (4,950 pairs, 90 candidates), on a workstation
at load average 11: broad phase 0.006 s, narrow phase 1.9 s cold, 0.03 s warm from the cache. The cross-check's
extra `Cut` roughly doubled the cold narrow phase. Real parts with hundreds of faces cost 10–100× more per pair.

### Pairs the table did not examine

`get(a, b)` answers `apart` (with `exact=False` and `gap_lower_bound_mm`) only when the boxes prove a gap over
`touch_mm`; a pair the table skipped (`skip_pairs`, or outside `only=`) with touching boxes reads `unchecked`.

### The pair cache

`PairCache(directory)` stores one JSON file per pair, keyed by the sha256 of both items' keys, the tolerances, the
relation version and the OCP version (a kernel upgrade re-queries everything). An item's key is its content hash
(`cadagent.evidence.shape_content_hash`, shared with the dossier: sha256 of the BREP text without triangulation,
flag lines stripped) plus its placement matrix rounded to 1e-9. A rebuild that moves or changes one part re-queries
only that part's pairs, across processes. Keep the cache out of `exports/`: the default is `.cadagent-cache/gates/`,
which is gitignored; deleting it is always safe.

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
from cadagent.gates.wall import check_wall, wall_gate, mesh_thickness, brep_thickness, brep_thickness_near

check_wall("hopper", 2.4, mesh=shape_or_stl_or_trimesh, shape=brep)           # -> Check
wall_gate({"hopper": {"wall_mm": 2.4, "mesh": m, "shape": s}, ...}, out="exports/gates/wall.json")
```

Two samplers measure thickness by rays along the inward surface normal:

- **mesh rays** from every triangle centroid (sub-sampled by area to `max_rays`, seeded), using trimesh with
  `rtree` or an exact numpy fallback. The mesh is repaired first (vertices within 1e-5 mm merged, degenerate and
  duplicate triangles dropped): CadQuery's tessellation leaves open seams at sphere poles, cone apexes and fillet
  corners;
- **exact B-rep rays** from an n × n UV grid on every face, n ≈ √area / `spacing_mm` (2 mm), between `grid` (3) and
  `max_grid` (16), so a small face is probed whatever its area and a large curved one is not under-sampled.

With both given, every thin mesh sample (up to 500, thinnest first) is **re-measured exactly** from the nearest B-rep
point along its surface normal (`brep_thickness_near`); readings the B-rep does not confirm are chord or facet-normal
error and are dismissed (`dismissed_as_chord_error` in the evidence). A mesh still open after repair is then a
warning, with the B-rep rays as the evidence; without a B-rep it fails.

A check fails when a sample (a confirmed one, with a B-rep) is thinner than `wall_mm - tol_mm` (default 0.01 mm), or
when more than 1 % of rays find no exit. Evidence: per-sampler summaries (min, p1/p5/p50, thin samples and area)
and up to ten witnesses with entry point, exit point and thickness.

Limits. Walls met at a slant and regions between samples are not measured. A sharp edge (a cone's apex or rim, a
chamfer meeting a face at an acute angle) reads thin near its tip, which is correct. A mesh alone reads curved walls
thin by its chord error (0.03–0.09 mm seen on 2.4 mm shells tessellated at 0.05 mm), and on thick curved bodies a
sliver triangle's tilted normal can exit through a neighbouring face (16.7 mm read on a 20 mm filleted block): pass
the B-rep, or set `tol_mm` to cover it. The threshold is the part's own (the dossier's `material.wall_mm`).

## Containment (`cadagent.gates.containment`)

```python
from cadagent.gates.containment import containment_gate, check_contains, Contains, contains_declarations

containment_gate(asm, [{"container": "hopper", "cavity": "hopper_cavity", "what": "ball", "count": 8}],
                 out="exports/gates/containment.json")
containment_gate(asm, contains_declarations(dossier))          # every card's `contains:` entry
containment_gate(asm, decls, poses={"home": {}, "turned": {"turret": cq.Location(...)}})   # per pose
containment_gate(asm, decls, support="fail", down=(0, 0, -1), support_mm=0.05)
containment_gate(asm, decls, meshes={"ball#8": "scan.stl"})    # mesh-only items: sample-only
containment_gate(asm, decls, exclusions=[{"parts": ["ball#0", "hopper"], "reason": "..."}], cache=cache)
containment_gate(asm, [{..., "closed_by": ["lid"]}])           # the cavity may reach into the lid's box
check_contains(asm, decl, pose="turned")                       # -> [Check] for one declaration, one pose
```

The cavity must be a registered `@cavity` solid (`Assembly.add_cavity`); there are no derived cavities. Instances of
`what` are the parts named `what` or `what#0`, `what#1`, ... Checks per declaration (ids `contains:<cavity>:...`,
prefixed `<pose>/` when `poses` is given):

| Check | Fails when | Evidence |
|---|---|---|
| `<inst>:inside` | more than `contain_mm3` of the instance is outside the cavity, or the kernel was unsure | `outside_mm3`, `outside_fraction`, `depth_mm` and the `furthest_outside_point` with its `nearest_cavity_point`; for a contained one its `clearance_mm` from the boundary |
| `<inst>:wall` | the instance shares more than `overlap_mm3` with the container's solid (touching is the intended rest) | the relation, with the overlap volume and centroid |
| `<what>:interpenetration` | two instances share volume | every overlapping pair with `overlap_mm3` and its centroid |
| `<what>:count` | the instances found differ from `count` (or none is found) | declared, found (B-rep and mesh) |
| `<what>:support` | `support="fail"` and an instance rests on nothing; a warning with `"report"` (default); skipped with `"off"` | `unsupported`, `on_cavity`, `rests_on` |
| `<what>:cavity` | the cavity is not registered (`unknown-cavity`) or belongs to another part (`cavity-wrong-part`), the dossier lint's codes | `lint` |
| `<what>:cavity-fit` | the cavity shares volume with the container's material, or its box reaches outside the box of the container and its `closed_by` parts (by more than `touch_mm`) | the relation, `cavity_box`, `host_box`, `box_overshoot_mm` per axis |

- **A cavity drawn too big** would pass contents that are not in the container: a ball beside the box, or stacked
  above its rim, touches no material, so the wall check cannot see it. The `cavity-fit` check looks at the cavity
  itself. It does not catch a cavity that stays within the container's box and outside its material (beside an
  L-shaped container): contents in that extra volume read inside.
- **Tangent contact is inside.** A ball resting on a cavity wall has 0 mm³ outside and is `touching` the container.
- **Contact probe.** OCCT's surface intersection can miss a shallow near-tangent crossing: a 4 mm sphere pushed
  0.03–0.1 mm through a cone wall read 0 mm³ outside at 5 of 50 positions tried, a consistent common = volume, cut = 0
  that the `vol = common + cut` cross-check cannot see. So every instance whose exact gap to the cavity boundary is
  within `touch_mm` is re-checked: points on its surface are classified against the cavity with
  `BRepClass3d_SolidClassifier`, which uses no surface intersection. The points are the tessellation nodes
  (`probe_deflection_mm`, 0.01) plus a UV grid of about `probe_spacing_mm` (0.5) on every face, trimmed to the face:
  BRepMesh puts no node inside a plane or along a cylinder's or cone's straight direction, so nodes alone are blind
  to a crossing in the middle of such a face. A point outside by more than `touch_mm` fails the instance with its
  depth (`kernel_missed_crossing`; the volume is not measured). Blind spots: a crossing whose footprint falls between
  samples (the grid is at most 64 × 64 per face, so coarser than the spacing on faces over 32 mm across), or no deeper
  than `touch_mm`. On a 4 mm ball against a cone wall, every crossing of 0.015 mm or more was caught at 16 angles; at 0.01 mm (= `touch_mm`) the boolean and the probe both missed 5 of 16. It
  costs about 0.3–0.5 s per touching ball; `probe=False` turns it off. **This limit applies to the relation table too** (a
  near-tangent `touching` between two parts can be a shallow overlap); only the containment gate probes for it.
- **Furthest point outside.** The furthest of the vertices of a tessellation of the escaped piece (`cut(instance,
  cavity)`), then climbed to the piece's extreme point along the outward direction: exact for a ball through a flat
  or cylindrical wall, a lower bound in general.
- **Support.** An instance rests on X when moving it `support_mm` along `down` pushes more than `overlap_mm3`
  *further* out of the cavity or into another instance than before the move, so volume already outside or overlapping
  is not support (boolean volumes; for a pair sharing no volume and within `support_mm`, the surface probe as
  fallback, counting only points the move takes across);
  supported means resting on the cavity, or on a supported instance, followed down the chain. A static contact test
  along one direction, not a settling or stability simulation; other parts (a board in the hopper) do not count.
- **Poses.** `poses={name: {body: location}}` applies `Assembly.posed` per body. A container that turns while its
  contents are modelled in fixed positions (the incident) fails in the pose where they part.
- **Mesh-only items** (`meshes={key: trimesh | STL path | shape}`) are **sample-only**: points uniform in the mesh's
  box are kept when inside it (generalised winding number, no `rtree` needed; computed in chunks sized to keep about
  128 MB of temporaries whatever the triangle count, so time, not memory, grows with the mesh) and classified against the exact cavity
  and container solids, so the outside and wall volumes are Monte Carlo estimates with a standard error
  (`mesh_samples`, 4000, seeded); the mesh's vertices give the furthest-outside witness. Mesh items get no
  interpenetration or support check.
- **Cost.** The 8-ball gate bench: about 2 s cold (the four balls on the floor are probed); 40 balls in a cone: about
  9 s cold on a loaded workstation. Every query goes through `cache` (`PairCache`), keyed on the content hashes and
  placements, so an unchanged rerun reads the cache.

## Connectivity and floating parts (`cadagent.gates.connectivity`)

Does every part hang on something, and is every declared connection really there?

```python
from cadagent.gates.connectivity import Declarations, connectivity_gate, connectivity_from_build, analyse, to_dot

decl = Declarations.from_build(result, dossier, extra)     # build record + YAML dossier + plain-data extras
v = connectivity_gate(Assembly.from_build(result), decl, cache=cache, out="exports/gates/connectivity.json")
v = connectivity_from_build(result, dossier, out=...)      # the same in one call
decl = Declarations(grounded=["base"], free={"ball": "loose in the hopper"},     # or by hand
                    interfaces=[{"id": "I7", "between": ["hopper", "base"], "kind": "fastened", "clearance": 0.2}],
                    joints={"I9": {"kind": "revolute", "moving": "flap", "fixed": "hopper"}},  # None: assembly.joints
                    fasteners={"m3": {"clamps": "lid", "into": "insert_0",          # axes and length let a fastener
                                      "axes": [((17.4, 22.4, 47), (0, 0, -1))], "length_mm": 8}},  # without a solid count
                    contains=[{"what": "ball", "cavity": "hopper_cavity"}],      # container: the cavity's part
                    intended_overlaps=[{"parts": ["hopper", "insert_0"], "reason": "heat-set"}],
                    strict_interfaces=False, touch_mm=None, max_joint_gap_mm=1.0)
```

`from_build` joins: `grounded` and `free` flags, fastener axes and lengths from the build record; `gates:`
(`grounded`, `free_parts`, `intended_overlaps`, `ignore_pairs`, `strict_interfaces`, `touch_tol_mm`) and every
interface and card `contains` from the dossier; the same keys from `extra` (the bench passes its plain-data
declarations there). A `contains` with `free: true` makes its items allowed-free with that as the reason.
Interfaces declared twice are merged when equal; differing ones keep the first and warn (`duplicate:interface:<id>`).

**The graph.** Nodes are the assembly's keys (instances and placed fasteners). Edges:

| Edge | From |
|---|---|
| `contact` | the relation table: `touching`, `overlapping` or `contains` between two parts (`ignore_pairs` dropped) |
| `contained` | an instance of a declared `contains` that lies inside its registered cavity (`relate_pair`), touching or not |
| `fastener` | a fastener with no modelled solid whose axis, from the seat over `length_mm`, comes within `touch_mm` of what it clamps and of what it threads into (`fastener_reach`) |
| `joint` | every joint instance pair, with the measured gap and whether it `holds` |

**Bodies.** Each non-fixed joint's `moving` instances seed a moving body, which grows transitively across `fixed`
joints and fastener declarations (the fastener, what it clamps, what it threads into). A link from a body into a
grounded part, a joint's `fixed` part or another body fails `bodies:<b>` (a moving part bolted to what it moves
against). Parts labelled into a moving body by the assembly keep that label; everything else is the static frame.
Group ids are `static` and `body:<name>`.

**Rigid edges.** An edge holds something up when both ends are in one group, neither end is an allowed-free part,
and it is not a joint (a `fixed` joint counts when it holds). A contact across groups (the arm on its stop) or with a
loose part is kept in the graph but holds nothing up: a static part touching only a moving body floats (it stays
behind when the body moves), and so does a part resting only on a loose ball.

**Joints hold when measured.** A non-fixed joint holds a moving instance when the instance is within the declared
`clearance` of an interface with the joint's id, else within `max_joint_gap_mm` (1 mm), of a `fixed` instance; a
`fixed` joint needs contact or a declared clearance. Every instance is checked. A component is grounded when it
holds a grounded part, or a held moving instance whose `fixed` part is in a grounded component (chains followed).

**Checks** (ids in the verdict):

| Id | Fails when |
|---|---|
| `ground` | no grounded part, a grounded name not a part in the assembly (sections are refused), or a grounded part in a moving body. `ground:<name>` warns when a grounded part has several instances (each is ground) |
| `connect:static`, `connect:body:<b>` | a component of the group is not grounded. One check per group; each island has its witness: the nearest grounded part (same group first), the exact gap, both closest points, what it touches across bodies or among loose parts, and the joints that do not hold it |
| `joint:<id>` | a party is not a part; a moving instance not within its limit of a `fixed` instance; the `fixed` part in the moving body itself or not grounded; a `fixed` joint across two bodies |
| `bodies:<b>`, `body-label:<key>` | a declared rigid link ties a moving body to ground, a joint's fixed part or another body (fail); a part's given moving-body label differs from the derived one (warn) |
| `interface:<id>` | not two parties; a mechanism kind (`revolute`, `slider`, `cylindrical`, `planar`, `ball`) with no joint of that id, or one between other parts; any other geometric kind with no contact between its parties and no gap within `clearance` (`gap` needs a `clearance`). Parties are part names, instance keys or section ids; one contact between any instances realises it |
| `fastener:<name>` | a modelled solid that does not touch what it clamps or what it threads into; a fastener without a solid whose measured axis misses either. Without a solid and without axes or length it warns and joins nothing |
| `contact:<a>\|<b>` | a contact no interface, joint (its parts or `intended_contacts`), fastener, `contains` or intended overlap declares, and neither part free: a **warning**, a failure with `strict_interfaces` |
| `free:<part>` | an allowed-free part with no reason (fail; it is then checked like any part) or one naming nothing (warning) |
| `relation:<a>\|<b>` | the kernel could not decide the pair (`unknown`) |
| `tolerances` | (warning) the declarations' `touch_mm` differs from the given table's, which is used |

An island made only of allowed-free parts is an `exclusion` with their reasons. `not_checked` lists what the gate
could not check: non-geometric interfaces (`electrical`, `thermal`, `fluid`, `other`), fasteners without a solid
that could not be measured, `contains` whose cavity is not registered, interfaces whose pairs are all ignored, and
pairs the table skipped. The verdict's other extra keys: `graph` (`nodes` with `group`, `body_given`, component,
`grounded`, `free`, `held`, `floating`; `edges` with `rigid` and `declared_by`; `components` with `grounded` and
`via_joint`; `groups`; `missing`: unrealised declarations), `floating`, `undeclared_contacts`, `unrealised` and
`relation_stats`. `to_dot(verdict)` / `write_dot(verdict, path)` give a Graphviz graph (one cluster per group,
floating parts red, joints that do not hold and unrealised declarations red); `connectivity_gate(out=...)` writes it
beside the verdict as `.dot`. Render it with `dot -Tsvg` where Graphviz is installed; the toolkit does not need it.

A relation table passed in (`table=`) is read, never changed: witness and joint queries go through `relate_pair`
and the cache. `analyse(nodes, relations, declarations, contained=..., measure=..., lower_bounds=...,
fastener_reach=...)` is the kernel-free core: it runs on any relation rows, which is how the rules are tested in core
CI.

Limits. The graph is the model's geometry within the relation tolerances: contact in the model does not prove that
printed parts meet, stay put or carry load. A joint within its allowed gap is trusted as a connection; the gap is
reported. A fastener without a solid is judged by its axis line alone (no thread, no head seat). A multi-instance
grounded part makes every instance ground. Body labels are derived from declarations, not from motion. Witness search
spends at most three extra exact queries per island or interface on pairs the table did not measure; a
joint measures every moving × fixed instance pair.

**Where this differs from the plan (§4.2).** The plan's single graph becomes per-group graphs, so a cross-body or
loose-part contact cannot hold a part up; items in a declared cavity count as held (`contained`); a joint is a
connection only within a measured gap; a mechanism interface is realised by its joint, not by contact; contacts
involving a free part are not reported as undeclared; the graph is exported as DOT for the site (T15) to render as
SVG.

## Motion-range interference (`cadagent.gates.motion`)

Does anything that moves hit something over its declared range?

```python
from cadagent.gates.motion import motion_gate, motion_from_build, run_motion

v = motion_gate(asm, out="exports/gates/motion.json")          # joints from Assembly.from_build (asm.joints)
v = motion_gate(asm, {"I9": {"kind": "revolute", "moving": "flap", "fixed": "hopper",       # or by hand
                             "axis": ((31, 0, 70), (0, 1, 0)), "range": [0, 70], "unit": "deg",
                             "intended_contacts": [("flap", "hopper_stop")], "samples": 24}},
                cache=PairCache(), samples={"I9": 30}, default_samples=12, max_step_deg=2.0, max_step_mm=1.0,
                combine=[["I9", "I10"]], intended_contacts=[("flap", "seal")], strict_contacts=False,
                intended_overlaps=[{"parts": ["brush", "drum"], "reason": "bristles"}], ignore_pairs=[("a", "b")],
                refine_steps=8, max_poses=2000,
                contains=[{"container": "cup", "cavity": "cup_void", "what": "ball"}], containment_options={})
v = motion_from_build(result, dossier, extra)    # from_build + gates: (motion_samples, intended_overlaps,
                                                 # ignore_pairs, touch_tol_mm) + cards' contains
```

**What moves.** A joint's `moving` part's body, as `Assembly.from_build` labels it with `moving_bodies`: the
transitive closure over `fixed` joints and fastener `clamps`/`into`, stopped at grounded parts and at any joint's
`fixed` part. This settles the open question in `dossier.md` and is final (the connectivity gate uses the same
rule). A hand-built `Assembly` uses its own `body=` labels. A chain therefore hangs each child joint's `fixed`
part on its parent's moving part itself, or labels the bodies by hand: a bracket fastened to the parent body and
also a child joint's `fixed` part stays in the static frame, which the connectivity gate reports (`bodies:`).

**Sampling.** Ranges are offsets from the pose the model was built in (0 = as modelled); axes are in assembly
coordinates at that pose. A revolute joint rotates (right-handed about the axis direction), a slider translates
along it, a cylindrical joint does both on a grid of the two. A joint needs the ranges of its kind (a revolute `range_deg`,
or `range` with `unit: deg`; a slider `range_mm`; a cylindrical both), else `joint:<id>` fails. Each axis gets
`samples={id: n}` (the caller's override), else the joint's own `samples`, else `default_samples` (12;
`gates.motion_samples` from the dossier), raised until the step is at most `max_step_deg`/`max_step_mm`, evenly
spaced with both ends included. A zero-length range is one pose and a `range:` warning. `planar` and `ball` joints
have no range: a warning, listed in `not_checked`; `fixed` joints are rigid links, not sampled.

**Chains and combinations.** A joint whose `fixed` part lies in another joint's moving body rides on it: the chain
is one group, sampled on the full grid (parent samples × child samples), each child's transform carried by its
parent's. Independent joints are sampled one at a time with the others at home (0 clamped into their range);
`combine=[[...]]` grids them together. Independent groups whose swept boxes come within `near_mm` of each other
get a `combination:` warning, since nothing sampled them moving at once. A grid over `max_poses` (2000) is
coarsened evenly on every axis, with a `density:` warning.

**Pairs and cost.** Per pose: every part of a moving body against every part outside it (the static frame, other
bodies, both bodies of a chain). Pairs that never move relative to each other, static against static and parts of
one body, are the same in every pose and are never queried: they are the relation table's and the connectivity
gate's. Broad phase: each part's exact home box, its corners moved with the pose (a box enclosing the moved part),
against `near_mm`; the narrow phase is `relate` (contact area off), memoised in memory and through `cache` on both
parts' content hash and posed placement (the pose is in the key), so a repeated pose costs nothing and an unchanged
rerun reads only the cache.

| Check | Fails when | Evidence |
|---|---|---|
| `collision:<a>\|<b>` | a moving part shares more than `overlap_mm3` with another (overlapping or contains) at any pose, unless declared in `intended_overlaps`; also an intended contact driven into its face (`intended_contact: true`) | `first_pose`: the colliding pose nearest home (the sum over axes of the distance from home as a fraction of the range; ties in sweep order), the one met first moving out from rest; its `overlap_mm3`, `overlap_centroid` and `overlap_box`; `last_clear_pose`, its clear grid neighbour nearest home (one sample away on one axis), with `last_clear_gap_mm` and the closest points `point_a`/`point_b`; `colliding_poses`, `worst_pose`, `worst_overlap_mm3`; the `onset` bisected between the two along that axis (`joint`, `clear`, `hit`, the overlap at the hit side and the gap and closest points at the clear side; `others` gives the other axes' values, held fixed, on a grid) |
| `contact:<a>\|<b>` | (warning) a moving part touches one that is not an intended contact; fails with `strict_contacts` | first pose, number of poses, closest points |
| `relation:<a>\|<b>` | the kernel could not decide a pair at some pose (`unknown`) | the relation |
| `motion:<group>` | any of the above in the group; passes otherwise | per axis `density` (samples, declared samples, `step` in deg or mm, the largest radius from the axis of the parts it carries, over the sampled poses, and `max_travel_per_step_mm`); the smallest exact clearance (touching included) among the non-intended pairs measured (`min_clearance_mm`, `at`: pair, pose, points) and, when smaller, the box distance of the nearest pair never measured (`unmeasured_gap_at_least_mm`: its gap is at least this); the intended contacts and the poses where they touch |
| `joint:<id>` | a joint's part is missing, its `fixed` part is in its own moving body, two joints drive one body, joints carry each other in a loop, or a ranged joint has no range; a warning for `planar`/`ball` | |
| `combination:<g1>+<g2>`, `density:<g>` | (warnings) see above | |
| `containment@<group>/<pose>/...` | with `contains=`: the containment gate's checks at every pose of a group that moves the container's cavity or the contents | as the containment gate |

**Intended contacts.** A joint's `intended_contacts`, its own `moving`/`fixed` pair (the bearing) and the
`intended_contacts` argument may touch at any pose: an arm resting on its stop at the range end passes. Shared
volume between them over `overlap_mm3` still fails. The onset is where shared volume first exceeds `overlap_mm3`,
so it lies slightly past the first touch (about 0.02° for a corner 45 mm from the axis at the default tolerances).

**Density, honestly.** The verdict reports the step between samples and the furthest any carried point moves in
one step: step × the largest distance from the axis of the corners of the carried parts' boxes, over every sampled
pose (a child joint's motion included, so a turret carrying an arm slid out is measured at full reach). It bounds
the travel at the sampled poses; on a chain, a child pose between samples can reach a little further. A collision
shorter than one step, or a feature thinner than that travel, can pass between samples: raise `samples` or set
`max_step_*` where the smallest clearance is small next to the travel per step. The verdict never claims a swept
volume.

**Containment per pose.** With `contains=` (`motion_from_build` passes the cards' and `extra`'s), every declaration
whose cavity or contents a group moves runs through `containment_gate` at that group's poses; the others are
listed in `not_checked`. The cost is the containment gate's per pose.

`run_motion(world, joints, ...)` is the kernel-free core: `world` gives part names, body labels, home boxes and
`relate(mats, a, b)` per pose (`AssemblyWorld` wraps an `Assembly`), which is how the rules are tested in core CI.

**Cost.** Gate bench, one joint at 12 samples: 12 poses, 48 exact queries, 0.8 s cold (on a workstation at load 6).
The synthetic 100-part assembly (`tools/gate_timing.py --motion 20`) with three joints at 20 samples each: 60 poses,
92 candidate pairs plus 32 bisection queries, 1.7 s cold, 0.07 s warm from the pair cache. The broad phase keeps
the queries to the pairs that come near: real parts cost more per query (see the relation table), not more queries.

Limits. Sampled poses, not a swept volume. Rigid bodies on ideal axes: no backlash, play, deflection or tolerance
stack, so a clear pose in the model does not prove printed parts clear. Contacts are classified by the relation
table's tolerances (`touch_mm`; the near-tangent blind spot of the boolean kernel applies, see containment). Joint
limits are the declared ranges; nothing checks that a stop actually ends the motion there.

## The gate bench (`tests/fixtures/gate_bench/build.py`)

A generic mechanism declared through the dossier registry: a base, a hopper with filleted corners and a declared
cavity, eight loose balls (one part, eight instances), a board, a lid held by four fasteners into heat-set inserts,
a bracket on a boss, an arm on a pin (a revolute joint) with a filleted stop and an overhead frame, and the
assembly steps. What belongs in the YAML dossier (interfaces, intended overlaps, `contains`, decisions, walls,
tool envelopes) is plain data until the bench gets a `dossier/` directory. `build(seed)` returns the
`BuildResult`, `Assembly.from_build` of it and those declarations, for the clean bench or one of the plan's ten
seeded defects (`SEEDS`).

`tests/test_gate_bench.py` runs every gate on the clean bench (no finding allowed) and on every seed (its gate must
fail with a finding that names the seeded part; the wall seed's witnesses must lie on the thinned wall). A gate not
built yet has an adapter that raises `NotImplementedError` and strict-xfail cases; its implementer writes the
adapter and removes the mark.

## Where this differs from the plan

- **Cache location and key**: `.cadagent-cache/gates/` (gitignored), not `exports/gates/cache/`; the shared content
  hash plus placement, the tolerances and the OCP version, not OCP's identity hash.
- **Containment tolerance**: absolute (`contain_mm3`), not 1e-6 relative.
- **Wall probe**: exact B-rep rays replace the negative-offset probe. `BRepOffsetAPI_MakeOffsetShape` by −t/2
  returned a shell or a null shape on a 0.8 mm rib and on a 2.4 mm-walled box, the cases it was meant for.
- **Derived cavities** are not built; containment takes a declared cavity solid.
- **Containment, mesh-only items**: classified against the exact B-rep cavity (`BRepClass3d`), not with trimesh
  `contains` against a tessellated cavity (the cavity is always a B-rep; trimesh `contains` needs `rtree`).
- **Containment, additions**: the contact probe for near-tangent crossings, the support check and per-pose runs are
  not in the plan; the plan's "40 spheres in a cone, one moved 5 mm up through the wall" moves it 5 mm along the
  wall's outward normal (the cone opens upwards, so "up" leads away from the wall).
- **Motion**: no pose renders (the verdict gives the poses and witness points; T10's render packet can pose them);
  chains are always gridded and independent joints combined on request (`combine`), where the plan grids only
  joints declared `coupled`; pairs that do not move relative to each other are never queried rather than taken
  from the full per-pose table; the collision onset of a one-axis joint is bisected; containment can run per pose.
- **Seed harness file**: `tests/test_gate_bench.py` (pytest only collects `test_*.py`), fixture directory
  `gate_bench` (importable name).
