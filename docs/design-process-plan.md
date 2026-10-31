# Design process plan: dossier, integrity gates and section-by-section review

Status: plan, 2026-10-27. Research behind it: [`research/design-workflows.md`](../research/design-workflows.md)
(cited below as DW §n). Nothing here is implemented yet; tasks T1–T20 at the end are sized for one implementer each.

## 1. Why

A turret assembly in a robot project built with cad-agent rendered its ammunition outside the hopper that should
hold it, with subassemblies that read as boxes stuck on the side. Every per-part check passed: the parts were valid
solids, watertight, within the bed, and no two printed parts overlapped. Nothing asked whether the balls were
*inside* the hopper, whether each subassembly was *attached* to its neighbour, or whether anyone had *looked* at the
render with a checklist. The toolkit checks parts; it does not check the design.

What is missing is a process, and the tools that make the process cheap:

| Missing | Today | After this plan |
|---|---|---|
| Decomposition | one `build.py` per product, interfaces in the author's head or a loose JSON | a **dossier**: requirements → sections → parts and interfaces, declared beside the CAD |
| Justification | `decisions.yaml` at project level, written after the fact | a **spec card** per part and section: function, interfaces, loads, decisions with alternatives rejected, written *with* the geometry |
| Assembly integrity | pairwise overlap volume only | **gates**: connectivity, containment, floating parts, fastener and stack consistency, motion-range interference, assembly access |
| Visual review | renders are produced and linked | renders are **critiqued against a checklist** by a reviewer that did not build the part, with a sign-off record |
| Evidence | per-check JSON and a report | every dossier item carries its status and links its evidence; the site shows a section-by-section review page |

The practices come from DW §2–§5: the verified gains are from deterministic checks before visual ones (DW §2.5),
containment and interpenetration as first-class relations (build123d-mcp `clearance`, DW §4.2), structure
expectations declared by the author (agentcad `expect_solids`/`floating`, DW §2.2, §4.6), spec-driven conformance with
evidence tiers (build123d-mcp `verify_spec`, DW §2.2), and the engineering artefacts that have had the same shape for
decades: interface control documents, requirement traces, decision records, DFMEA rows and assembly sequences
(DW §3).

## 2. Principles

1. **Declare, then derive.** The author declares intent (what touches what, what sits inside what, what moves, what
   fastens what) in a few lines next to the geometry. The gates derive the geometry's actual relations and diff the two.
   Undeclared relations are findings, not silence.
2. **Deterministic before visual.** Every gate is a kernel query with a number. Visual review comes after, is
   checklist-driven, and is never the only evidence for a claim (DW §5).
3. **A missing declaration fails.** A part without a spec card, a section without requirements, an interface with
   one side only: all are failures in `cad-agent check`, the same as a missing check file today.
4. **Explained exclusions, never loosened thresholds** (lesson 07). Intended overlaps (inserts, press fits) and
   intended floating parts (loose balls, a lid shown exploded) are declared with a reason and reported in their own list.
5. **Generic.** Sections, parts, interfaces, joints and cavities are the vocabulary of any mechanical assembly. Nothing
   in `cadagent` knows what a turret or an enclosure is.
6. **Minimal boilerplate.** A project that only wants the gates adds one call to its build; a project that wants the
   whole process adds YAML it would have had to write anyway as a design review.

## 3. The design dossier

### 3.1 Model

```
Project
 ├─ requirements[]      R1..Rn: text, source (user quote | standard | derived), verify_by (analysis|inspection|test|demo), status
 ├─ sections[]          S1..Sn: title, purpose, requirements[], interfaces[], parts[], decisions[], review
 │    ├─ parts[]        the part spec cards (3.2)
 │    └─ interfaces[]   I1..In: between two parts or sections; kind, datum, loads, fastened_by, clearance, owner
 ├─ decisions[]         D1..Dn: as today (site decisions.yaml), plus `scope: project|section|part`, `alternatives[]` with reasons
 ├─ assembly            steps[]: order, what is fitted, from which direction, tool, access check id
 └─ gates               the integrity-gate configuration (4.1) and the per-gate verdicts once run
```

Requirements, sections and decisions are the three lists every design review already needs (DW §3.2–§3.4). An
interface is the smallest unit of an interface control document: two parties, a datum, what crosses it, who owns it
(DW §3.1). The assembly list is the Boothroyd-Dewhurst/DFA sequence table (DW §3.6, §3.9).

### 3.2 The part spec card

```yaml
# dossier/sections/hopper.yaml  (one file per section; parts are nested, or `parts: [file.yaml]` to split)
id: S3
title: Hopper and feed
purpose: Hold 40 foam balls and present one at a time to the feed wheel
requirements: [R4, R7, R12]
parts:
  - id: hopper
    function: Contain the ball store and funnel balls to the feed throat under gravity
    interfaces: [I7, I8, I9]
    loads: {static: "40 balls, 0.26 kg, on the floor cone", shock: "1 m drop on a corner (R12)"}
    material: {name: PETG, process: FDM, print_axis: "+Z", wall_mm: 2.4}
    fasteners: [{to: pan_base, screws: screw_m3x8, qty: 4, via: I7}]
    contains: [{what: ball, count: 40, cavity: hopper_cavity, free: true}]     # drives the containment gate
    decisions:
      - id: D41
        decision: Single-wall cone with a 55° floor
        why: Balls roll at 35°; 55° clears the feed throat without a stirrer
        alternatives:
          - {option: Stirrer paddle, rejected: adds a motor and a jam mode (DFMEA F3)}
          - {option: Vibrating floor, rejected: no evidence it clears 40 mm foam balls}
    checks: [gate:containment, gate:connectivity, fea:hopper-drop, print:hopper]
    status: reviewed          # draft | built | gated | reviewed | signed_off
```

Fields and where they are checked:

| Field | Checked by |
|---|---|
| `interfaces` | every id exists, has two parties, and this part is one of them; the connectivity gate expects contact or a declared gap along each |
| `fasteners` | the fastener gate: a modelled fastener per entry, its stack (seat, grip, thread start, engagement) consistent with the two parts' geometry; tool access at the assembly step that installs it |
| `contains` | the containment gate: each instance of `what` inside the named cavity of this part; `free: true` exempts them from the floating-part gate |
| `material.wall_mm` | the minimum-wall gate (threshold per part, not per project) |
| `decisions[].alternatives` | the dossier lint: a decision with no alternative or no `why` is `incomplete`; a section with an open decision cannot be signed off |
| `checks` | each id resolves to a gate verdict or a configured check; the card's status cannot pass `gated` while one fails |
| `status` | only the reviewer pass (5.3) may set `reviewed` and `signed_off`; a change of the part's geometry hash voids the review, and the status falls back to what the current evidence supports (`gated` when its gates still pass, else `built`). As built (T2), every status is computed into `exports/dossier-status.json`; a YAML `status:` above the computed one is a finding |

### 3.3 Storage

- `dossier/project.yaml`: requirements, sections list (file per section), assembly steps, gate config.
- `dossier/sections/<id>.yaml`: the section and its parts (3.2). Parts may be split into `dossier/parts/<name>.yaml`
  when a section grows; `parts: [path]` entries are loaded in place.
- `dossier/decisions.yaml`: the existing site format, extended with `scope` and structured `alternatives`. The site's
  `site: decisions:` key keeps working; the dossier adds section and part scopes.
- `dossier/reviews/<section>-<date>.json`: reviewer sign-off records (5.3), written by the reviewer pass only.
- `exports/dossier-status.json`: the compiled dossier with every item's status and evidence links, written by
  `cad-agent dossier`; the site and the report read this file, never the YAML.
- `exports/gates/<gate>.json`: one verdict file per gate, in the existing check shape (`pass`, limits, findings,
  exclusions, `physical_fit_verified: false`).

YAML, not JSON, for the hand-written files: comments and quotes matter in a dossier (requirements are user quotes,
lesson 02). `cad-agent.yaml` gains one key: `dossier: dossier/project.yaml`.

### 3.4 Declaration from build scripts with minimal boilerplate

Build scripts keep returning shapes. They declare the geometric facts the gates need, in code, because only the code
knows which solid is the cavity and where a joint axis is:

```python
from cadagent.dossier import part, cavity, joint, fastener, assembly

@part("hopper", section="S3")                 # registers the shape and its dossier card
def hopper(p): ...                            # returns a cq Shape as today

@cavity("hopper", "hopper_cavity")            # the void the containment gate tests against
def hopper_cavity(p): return hopper_shell_inner(p)

@joint("I9", kind="revolute", axis=lambda p: Axis(p["flap_pivot"], (0, 1, 0)), range_deg=(0, 70),
       parts=("hopper_flap", "hopper"))
def flap_pivot(p): ...                        # optional body; the joint is what matters

assembly.step(1, fit="pan_base", onto="bench_base", direction="-Z", tool="hex_2.5", fasteners=["screw_m4x12"] * 3)
```

The registry (`cadagent.dossier.REGISTRY`) collects parts, cavities, joints, fasteners and assembly steps at import
time; `build()` runs them with `parameters.json` and writes `exports/dossier-geometry.json` (content hashes of every
shape as defined in 4.1, bounding boxes, cavity and joint frames, and the `actor` that ran the build, from the
`CAD_AGENT_ACTOR` environment variable, see 5.3) next to the STEP files. A project that does not use decorators can instead return a
dict from `print_parts()` as today plus `dossier_items()`, so existing builds migrate one part at a time. The YAML
cards and the code registry are joined by id; a card without a registered shape, or a shape without a card, is a
lint finding.

Fasteners come from the existing McMaster catalogue entries (`skills/mcmaster-parts`) or `cadagent.geometry.fasteners`
envelopes; a `fastener` declaration names the catalogue key, the head seat face and the part it threads into, which
is what the stack gate needs (lesson 04).

### 3.5 Rendering on the review site

A new page `site/review.html` (and `cad-agent site` section "Design review by section"):

- one row per section: title, requirements covered, part count, gate status (pass/fail/unrun), review status
  (unreviewed / findings open / signed off), the reviewer's date and record link;
- expanding a section shows each part card (3.2) with every check as a pill linked to its evidence (gate JSON, FEA
  page, render), the decisions with their alternatives, and the section's renders with the reviewer's findings
  overlaid as a list beside each image;
- a requirements table at the top: each requirement, the sections and checks that trace to it, and its status
  (unverified until every linked check passes; `test` requirements stay "not tested" because cad-agent cannot set them);
- a gates page `site/gates.html`: the connectivity graph drawn as an SVG (parts as nodes, declared interfaces as
  edges, undeclared contacts dashed red, floating components highlighted), the containment table, motion sweep results.

The existing overview keeps its decisions section; decisions with a section scope also appear in that section's card.

As built (T15, [`dossier.md`](dossier.md#on-the-review-site)): the pages live in `site/review/` (`index.html`, one
`section-<id>.html` per section instead of expanding rows, `requirements.html` on its own page, `gates.html`); the
gates page has a row per gate and each gate's findings with witnesses rather than gate-specific containment and
motion tables, and the connectivity graph follows the DOT the gate writes (undeclared contacts orange, unrealised
declarations red dashed).

## 4. Integrity gates (`cadagent.gates`)

All gates take the same input: `Assembly` = `{part_name: shape in assembly coordinates}` plus the dossier geometry
(cavities, joints, fasteners, assembly steps) and the dossier declarations. All write the existing check JSON shape.
The CLI `cad-agent gates [--only NAME]` runs them after `build`; `cad-agent check` collects them like any check.

### 4.1 Common machinery (T3)

- **Broad phase.** Axis-aligned bounding boxes with a tolerance, all pairs (4,950 for 100 parts) in milliseconds;
  only overlapping boxes go to the kernel. A measured run on 100 synthetic solids: 100 candidates from 4,950 pairs in
  3 ms (DW §4.1).
- **Narrow phase.** `BRepExtrema_DistShapeShape` for the minimum gap (about 10 ms per simple pair), `BRepAlgoAPI_Common`
  volume for exact overlap (about 3 ms per simple pair) on the synthetic benchmark
  ([`research/bench/gate_timing.py`](../research/bench/gate_timing.py)). Real parts cost more: the 10–100× figure in
  DW §4.1 is an **estimate**, and `DistShapeShape` on freeform or heavily filleted faces, or `Common` on shelled parts,
  can take seconds per pair. T3's acceptance therefore includes one real, filleted and shelled pair, and the budget in
  4.9 is a target to be measured, not a claim.
- **Shape identity (content hash).** OCP's `TopoDS_Shape` hash is identity plus location, not content, and is not
  stable across processes, so it is never used as a key. A shape's id is `cadagent.evidence.shape_content_hash`: the
  sha256 of its BREP text (`BRepTools.Write_s`, format version 1, without triangulation or normals, so meshing does
  not change it) with the per-shape flag lines removed (the kernel flips them on its own). The shape's assembly
  location is part of that text. Shown deterministic across processes in the registry's tests. A shape read back
  from BREP may hash differently (the reader recomputes frames), so the hash recorded at build time travels with the
  shape and is never recomputed from a loaded copy. This is the same byte-hash discipline as `cadagent.evidence`,
  which hashes files with sha256. The same hash is what `dossier-geometry.json` records per part and what sign-off
  records (5.3) are bound to.
- **Pair cache.** Results are cached by the two content hashes (and, for the motion gate, the pose transform of the
  moving part, 4.5) in `.cad-agent/cache/gates/` under the project root. The directory is created with a `.gitignore`
  containing `*` so it is never committed; only the verdict JSON goes to `exports/`. A rebuild that changes one part
  re-queries only its pairs.
- **Relations.** For each candidate pair, one of `apart(gap)`, `touching`, `overlapping(volume)`,
  `contains(a_in_b | b_in_a)`, following build123d-mcp's four-state `clearance` (DW §4.2). `touching` is
  `gap ≤ touch_tol_mm` with the common volume below `vol_tol_mm3`; `contains` is common volume equal to the smaller
  shape's volume within `vol_tol_mm3`. Tolerances are absolute, not relative, because boolean results on curved solids
  carry fuzzy-value and integration error: `vol_tol_mm3 = max(0.01, touch_tol_mm × area_mm2(smaller shape))`, that is,
  a skin of thickness `touch_tol_mm` over the smaller part. This table is the input to every gate below, computed once.
- **Config** in `dossier/project.yaml` → `gates:`: `touch_tol_mm` (default 0.01), `vol_tol_mm3` (override of the
  default above), `intended_overlaps` (`[{parts, reason}]`, e.g. heat-set inserts), `free_parts` (intended loose),
  `ignore_pairs` (variants that never coexist).

### 4.2 Connectivity and floating parts (T4)

- Build the contact graph: nodes are parts, edges are `touching` or `overlapping` relations, plus declared joints
  (a revolute joint with a clearance fit is not a contact but is a connection).
- Ground: the dossier names one or more `grounded` parts (the base, the bench stand). Every connected component that
  contains no grounded part is a **floating component**, unless every member is in `free_parts` or is a `contains`
  item with `free: true`.
- Diff against declarations: each declared interface must be realised by an edge (or by a declared gap within its
  `clearance`); each edge not covered by an interface is an **undeclared contact**. Both are findings with the
  witness points from the extrema query so the reviewer can look at the right place.
- Output: `exports/gates/connectivity.json` with components, floating parts, undeclared contacts, unrealised
  interfaces, and the graph for the site. Fails on any floating component or unrealised interface; undeclared contacts
  are warnings until the project sets `gates.strict_interfaces: true`.
- Tests: a frame of touching boxes plus a floating box fails; marking it free passes; a declared interface with a
  2 mm gap fails and passes once `clearance: 2.5` is declared; a revolute joint links a part that touches nothing.

### 4.3 Containment (T5)

- For each `contains` declaration: resolve the cavity solid, which **must be registered** by `@cavity` (there is no
  derived cavity: OCP has no B-rep convex hull, and a hull-minus-part result would be a mesh, not a solid `Common` can
  use; a `contains` declaration without a registered cavity is a lint finding). Then for every instance of `what`,
  `outside_mm3 = instance.Volume() − common(instance, cavity).Volume()`; the instance is inside when
  `outside_mm3 ≤ vol_tol_mm3` (4.1). Report the volume outside and the witness point from `DistShapeShape`.
  `BRepClass3d_SolidClassifier` on the instance's vertices and centre is the fast pre-check (24 points in 7 ms).
  Mesh-only items (an STL with no B-rep) are tested with trimesh `contains` against the tessellated cavity, reported as
  `sample-only`.
- Tangent contact is a first-class test case: a ball resting on the cavity floor (coincident or tangent faces) must
  report inside, with `outside_mm3` under the tolerance, not a false `interpenetrating`.
- Also the inverse: a part declared `inside` another part's cavity must not be `overlapping` with the container's
  material (the "wall-piercing" case, build123d-mcp `interpenetrating`).
- Fails when any instance is partly or wholly outside; `count` mismatch is a finding too.
- Tests: 40 spheres in a cone; one moved 5 mm up through the wall fails with the right volume outside; a sphere
  tangent to the cone wall passes; a `contains` declaration with no registered cavity is a lint finding; a mesh-only
  item takes the `sample-only` path.

### 4.4 Fastener and stack consistency (T6)

Extends `cadagent.geometry.fasteners.blind_insert_stack` from numbers to geometry:

- For each dossier fastener: locate the screw solid (catalogue STEP placed by the build, or envelope), the head seat
  face on the clamped part, the thread-start on the mating part (insert top or tapped hole start, from the declaration),
  and compute seat Z, grip, engagement, tip clearance in the fastener's own axis frame; compare with the stocked
  length and the required engagement; flag uncommon lengths (lesson 04).
- The screw's shank must not overlap the clamped part (the clearance hole must be at least shank + declared clearance,
  checked as a hole diameter), and its only overlap with the mating part must lie inside that part's declared thread
  region (an insert or tapped hole); any overlap elsewhere is a finding.
- **Tool access**: at the assembly step that installs the fastener, sweep the declared tool envelope (driver
  diameter × length, or hex key with swing) from the head along the axis; it must not overlap any part present at that
  step. Reuses the plug-sweep machinery of `cadagent.geometry.connectors.check_ports`.
- Output `exports/gates/fasteners.json`: a table per fastener, as lesson 04 asks for; fails on engagement below the
  declared minimum, tip collision, or no tool access.
- Tests: the existing `test_fasteners` cases turned into geometry; a screw whose driver is blocked by a gusset.

### 4.5 Motion-range interference (T7)

- Input: the declared joints with ranges. For each joint, pose the moving subtree at N samples across the range
  (default 12, plus the ends), and run the exact pairwise relation table (4.1) between the moving set and everything
  else, with intended contacts (stops, bearings) declared per joint. The cache key for these pairs includes the pose
  transform. Exact B-rep queries per pose are affordable at this N (4.9); when a project needs hundreds of poses, the
  scale-up path is the one DW §4.4 recommends: tessellate once into a trimesh `CollisionManager`, sample densely, and
  confirm each mesh hit on the exact B-rep at that pose.
- Swept volume by sampling, not exact: the sampled approach is what robotics collision checking does in practice
  (DW §4.4); the gate reports the sample density and the smallest clearance seen, and refuses to claim more. A project
  can raise N where the clearance is small relative to the motion per step.
- Compound motions (two joints) are sampled on a grid only when the dossier declares them `coupled`.
- Output `exports/gates/motion.json`: per joint, the minimum clearance over the range, the first colliding pose, the
  pair, and a render of that pose. Fails on any collision outside the intended contacts.
- Tests: a flap on a pivot that clears at 0° and hits a wall at 60°; the stop contact declared intended passes.

### 4.6 Minimum wall and feature size (T8)

- Ray-cast thickness on the print mesh (as text-to-cad's `dfam-check`, MIT, DW §4.5): per-face inward rays, the
  distribution of thickness, and the faces under the part's `material.wall_mm`. Add a negative-offset probe on the
  B-rep for thin ribs where rays miss (offset by −t/2 and see which solids vanish).
- Output per part; fails under the declared wall; the threshold is per part card, not global.

### 4.7 Assembly-sequence access (T9)

- For each assembly step: the parts present are the union of earlier steps; the fitted part is swept along its declared
  direction from outside the present set's bounding box to its final position; any overlap with a present part is a
  finding (the slide-in path check of lesson 07, generalised). Fastener tool sweeps (4.4) run at the step that installs
  them, with only the parts present then.
- Every part in the dossier must appear in exactly one step; every fastener in the step that installs it.
- Output `exports/gates/assembly.json`: steps, swept clearances, blocked steps.

### 4.8 Dossier lint (T2)

Not geometric. Loads the YAML, resolves ids, checks the table in 3.2, the requirement trace (every requirement is
referenced by a section and at least one check), decisions with alternatives, each section's review status, and the
join with the code registry. Writes `exports/gates/dossier-lint.json`.

### 4.9 Performance budget

Targets for 100 parts, to be measured in T3 (DW §4.1's real-part figure is an estimate): broad phase < 0.1 s; relation
table within a few minutes cold on real parts, seconds warm from the cache; motion gate
= samples × moving pairs, so 12 samples × 20 pairs ≈ 240 narrow-phase queries, under a minute. Gates run as
`cad-agent.yaml` steps after `build`, so a project can put the slow ones (motion, assembly) in a separate step and run
them only when geometry changed (the cache keys make an unchanged assembly free).

## 5. The review workflow for agents

### 5.1 Skill `skills/design-process/SKILL.md` (T10)

Built: [`skills/design-process/SKILL.md`](../skills/design-process/SKILL.md), the packet and the checklist in
[`review-packet.md`](review-packet.md) (`cadagent.publish.render.review_packet`, `cad-agent review-packet`).

Tells an agent building or changing a design to work in this order, per section:

1. **Frame the section**: write (or update) its YAML: purpose, requirements it serves (quote the user), interfaces to
   neighbouring sections with datums, the parts it needs. No geometry yet. Open questions become `open` decisions, and
   the agent decides them itself where the model can answer (lesson 02), recording the alternatives rejected.
2. **Write the spec card with the geometry**: function, loads, material, fasteners, `contains`, decisions, in the same
   commit as the build code; declare cavities, joints, fasteners and assembly steps in code.
3. **Build and gate**: `cad-agent build && cad-agent gates`. Fix every finding or declare the exclusion with a reason.
   Never lower a threshold to pass.
4. **Render for review**: a fixed packet per section (iso, opposite iso, the section cut through each cavity and joint,
   the assembly step poses, the motion extremes), captioned with the section id and the geometry hash, with the parts
   coloured by section and declared-free items in a contrast colour.
5. **Self-critique against the checklist** (5.2) and write the answers into the section's `review.self` block, with
   the render file each answer refers to.
6. **Hand to the reviewer pass** (5.3). Do not set `reviewed` yourself.
7. **Report**: one line per requirement touched, per gate, per open finding; say what is unverified.

The skill also carries the rules the lessons already state (one parameter authority; model the mating part, not its
bounding box; compute what the model can compute; classify false positives) so a fresh agent gets them in one place.

### 5.2 The render checklist

Specific yes/no questions, each tied to a view, which is what works for vision models (DW §5): "In the section cut
through `hopper_cavity`, is every ball fully inside the inner wall?", "In the exploded view, does every part have a
visible mating feature on its neighbour?", "Does any part appear as a plain box with no features?", "Are the fastener
heads visible from the direction the assembly step names?", "Is anything floating in the opposite iso?", "Does the
motion-extreme pose show contact other than the declared stop?". Counting and small gaps are not asked of the
image; the gates answer those, and the checklist says so.

### 5.3 Reviewer pass and sign-off (T11)

Built: `cadagent.dossier.review`, `cad-agent review-section` ([`dossier.md`](dossier.md#the-reviewer-pass)). The
separate-reviewer switch is the dossier's `gates: require_separate_reviewer`, and the build actor is recorded per
part (`parts.<name>.actor`).

A separate agent (or person) that did not write the section, given: the section YAML, the gate JSON, the render
packet, the checklist, and the diff since the last review. It:

- answers the checklist from the renders (and may request extra views by name);
- reads each decision and marks it `justified`, `weak` (why) or `missing alternative`;
- checks each requirement's trace;
- writes `dossier/reviews/<section>-<date>.json`: findings with severity, the render each refers to, the checklist
  answers, the decision verdicts, `signed_off: true|false`, the content hashes (4.1) of every part reviewed, and
  `actor`.

**Who is who.** Every build and every review record carries an `actor` string read from the `CAD_AGENT_ACTOR`
environment variable (an agent or session id, or a person's handle, set by the harness or the person who starts the
session; empty is recorded as `unknown`). `dossier-geometry.json` records the actor of the build that produced each
part's hash; the review record records the reviewer's. When `gates: require_separate_reviewer: true` (the default),
`cad-agent dossier` refuses a sign-off whose actor equals the build actor for any part in the section, or is `unknown`.
This makes the separate-reviewer rule checkable, but it is only as strong as the variable: a harness that sets the same
actor for both passes defeats it, and the plan says so rather than pretending otherwise.

`cad-agent dossier` sets the section's status from the latest record whose hashes match the current build; any geometry
change invalidates sign-off (the status falls back to `gated` when the gates pass on the new geometry, else `built`). The site shows who signed what and when. The reviewer
must not change geometry or YAML other than its own record; a reviewer who changes a part becomes that part's builder,
so its own sign-off is refused.

### 5.4 How the main agent and implementers use it

- The main agent plans sections from the requirements and hands each to an implementer with the skill and the section
  file; implementers work in parallel on sections whose interfaces are agreed (the interface list is the contract).
- Interfaces are owned: the owner section's implementer changes the datum; the other side rebuilds. The lint fails when
  both sides declare different datums.
- The main agent runs the reviewer pass on each section as it comes in, and the full gates on the integrated assembly;
  nothing is reported as done with an open finding or a missing sign-off.
- `cad-agent check` fails while any section is below `gated`, so the pipeline, not the agent's memory, holds the bar.

## 6. Evaluation

**Before/after on a real assembly.** Take the assembly from the incident as it was when it happened. Run the gates
on that snapshot: the containment gate must report the items outside their cavity, the connectivity gate must report
the subassemblies that only touch by coincidence or not at all. Then apply the process: dossier, gates, review. Record
the findings count, the time spent, and the review's sign-off. The same on a second, already heavily checked project as
a control: the gates should find little and nothing false, and every false positive becomes a test.

**Seeded defects.** A fixture assembly in `tests/fixtures/gate-bench/` (20 synthetic parts: a frame, a hinged flap, a
box with loose items, four fasteners, one bearing fit) with a script that injects defects one at a time:

| Seed | Must be caught by |
|---|---|
| move one contained item 5 mm through the wall | containment |
| delete the interface boss so a bracket floats | connectivity (floating) |
| shift a bracket 0.5 mm so it hovers | connectivity (unrealised interface) |
| lengthen a screw 4 mm into a cavity | fasteners (tip clearance) |
| shorten a screw so engagement < 3 threads | fasteners (engagement) |
| add a gusset under a screw head | fasteners (tool access) |
| raise the flap stop so the flap hits the wall at 50° | motion |
| thin one wall to 0.8 mm | minimum wall |
| reorder two assembly steps so the lid goes on before the board | assembly access |
| remove a decision's alternatives | dossier lint |

CI runs the seeded set; each gate's test asserts the defect is found with the right witness and that the clean fixture
passes with zero findings. The target is 10/10 seeds caught and 0 false positives on the clean fixture and the control
project.

**Visual review.** For the render checklist, keep a small labelled set (the incident renders, the fixed renders, the
seeded-defect renders) with the expected checklist answers; run the reviewer pass over them and report agreement.
This is the only part of the evaluation whose result is expected to be imperfect (DW §5), which is why the gates come
first.

## 7. Tasks

Each is one implementer, one PR into `dev`, with tests. Dependencies in brackets; tasks in the same wave run in parallel.

| # | Task | Files | Acceptance | Deps |
|---|---|---|---|---|
| **Wave 1** | | | | |
| T1 | Dossier schema and loader: `cadagent.dossier` dataclasses (Requirement, Section, PartCard, Interface, Decision, AssemblyStep, GateConfig), YAML loading with id resolution, `cad-agent.yaml` `dossier:` key, `docs/dossier.md` with the schema | `src/cadagent/dossier/{__init__,model,load}.py`, `tests/test_dossier_load.py`, `docs/dossier.md` | round-trips the example in 3.2; unknown keys reported; bad ids raise with the file and line | none |
| T3 | Gate machinery: `Assembly` container, AABB broad phase, pairwise relations (apart/touching/overlapping/contains) with witnesses and absolute tolerances (4.1), content hashing of shapes, pair cache in `.cad-agent/cache/gates/` keyed by content hashes (and pose), verdict JSON writer; `research/bench/gate_timing.py` folded in as a benchmark | `src/cadagent/gates/{__init__,relations,cache,hashing,verdict}.py`, `tests/test_gate_relations.py`, `tests/test_gate_hashing.py` | the synthetic 100-part run under 5 s and one real filleted, shelled pair timed and reported; the content hash is identical across two processes and changes when the shape changes; cache hit skips the kernel; relation states match build123d-mcp's definitions on the four textbook pairs plus tangent contact | none |
| T8 | Minimum wall gate on print meshes (ray-cast) plus B-rep negative-offset probe, threshold from the card's `material.wall_mm` | `src/cadagent/gates/wall.py`, `tests/test_gate_wall.py` | a 2.4 mm box passes at 2.4, fails at 2.5; a 0.8 mm rib is found (seed 8) | T1 (the card field; the gate itself can start with a plain threshold argument) |
| T13 | Build-script registry: `@part`, `@cavity`, `@joint`, `fastener()`, `assembly.step()`, `exports/dossier-geometry.json` with content hashes and `actor`, and the `dossier_items()` migration path | `src/cadagent/dossier/registry.py`, `tests/test_dossier_registry.py`, `docs/dossier.md` | the example in 3.4 builds; a card without a shape and a shape without a card are lint findings | T1 (same implementer as T1 is the natural split) |
| T12 | Gate-bench fixture (20 synthetic parts declaring cavities, joints, fasteners and steps through the T13 registry) and the seeded-defect harness | `tests/fixtures/gate_bench/build.py`, `tests/gate_bench.py` | the fixture builds under the `full` CI job and the test skips cleanly under `core` (no `cad` extra); every seed in 6 is a parametrised case that the matching gate must catch once that gate exists | T13 (until it lands, the fixture declares its items in a plain dict with the same keys) |
| **Wave 2** | | | | |
| T2 | Dossier lint and `cad-agent dossier` (compile to `exports/dossier-status.json`, status machine, content-hash invalidation, the YAML-to-registry join) | `src/cadagent/dossier/lint.py`, `cli.py`, `tests/test_dossier_lint.py` | the 3.2 table's rules each have a failing and passing test; seed 10 caught; `cad-agent check` picks the lint up | T1, T13, T3 (hashing) |
| T4 | Connectivity and floating-parts gate, with the declared-vs-actual diff and the graph export | `src/cadagent/gates/connectivity.py`, `tests/test_gate_connectivity.py` | 4.2's tests; seeds 2 and 3 caught | T1, T3, T13 (joints and `grounded` come from the registry) |
| T5 | Containment gate (registered cavity only; mesh `sample-only` fallback for mesh items) | `src/cadagent/gates/containment.py`, `tests/test_gate_containment.py` | 4.3's tests; seed 1 caught with the right outside volume; tangent contact passes | T1, T3, T13 (`@cavity`) |
| **Wave 3** | | | | |
| T6 | Fastener and stack gate with tool-access sweep | `src/cadagent/gates/fasteners.py`, `tests/test_gate_fasteners.py` | seeds 4–6 caught; the lesson-04 table is the output | T3, T13 |
| T7 | Motion-range gate | `src/cadagent/gates/motion.py`, `tests/test_gate_motion.py` | seed 7 caught; sample density reported; intended stop contact passes | T3, T13 |
| T9 | Assembly-sequence access gate | `src/cadagent/gates/assembly.py`, `tests/test_gate_assembly.py` | seed 9 caught; every part in exactly one step | T3, T13 |
| T14 | `cad-agent gates` command, step integration, report rows, `exports/gates/*.json` collected by `check` | `cli.py`, `report.py`, `tests/test_cli.py` | `cad-agent all` runs every gate after build; a failing gate fails `check` | T4, T5, T6, T7, T8, T9 (the command can land after T4/T5 with the others registered as they merge) |
| **Wave 4** | | | | |
| T10 | Skill `skills/design-process/SKILL.md` with the section workflow, the render packet spec and the checklist; `cadagent.publish.render.review_packet(section)` helper | `skills/design-process/SKILL.md`, `src/cadagent/render.py`, `tests/test_render.py` | the packet renders the fixture's sections with captions and hashes; the skill passes the repo's skill lint if any | T13, T14 |
| T11 | Reviewer pass: `cad-agent review-section <id>` prompt bundle (YAML, gates, renders, checklist, diff) and the sign-off record schema and validator; `actor` from `CAD_AGENT_ACTOR` in build and review records; status invalidation on hash change | `src/cadagent/dossier/review.py`, `cli.py`, `tests/test_dossier_review.py` | a record with stale hashes does not sign off; a record whose actor equals the build actor, or is `unknown`, is refused while `require_separate_reviewer` is on | T2, T10 |
| T15 | Site: section review page, requirements table, gates page with the connectivity SVG | `src/cadagent/site.py`, `webkit/`, `tests/test_site.py` | pages built from the fixture; every link resolves (`html_pages`) | T2, T14 |
| **Wave 5** | | | | |
| T16 | Evaluation: before/after on the two real projects (in their own repos, results summarised generically in `docs/design-process-eval.md`), labelled render set for the checklist, CI job for the seeded set | `docs/design-process-eval.md`, `.github/workflows/ci.yml` | 10/10 seeds, 0 false positives on the control; the eval doc states what the visual review got wrong | all |

| **Wave 6 (stage 2, lower value for the effort; after the gates have run on a real project)** | | | | |
| T17 | DFMEA rows in the dossier (`fmea:` per part: function, failure mode, effect, cause, S/O/D, action priority from a declared simplified band table), lint for completeness, and geometric prevention controls that resolve to gate ids | `src/cadagent/dossier/fmea.py`, `docs/dossier.md`, tests | every H-priority row has an action; a control naming a gate fails when the gate fails | T2 |
| T18 | DFA worksheet derived from the contact graph and mates: part and fastener counts, insertion directions, symmetry classes from principal inertia, the three necessity criteria with criterion 3 left to a human; a declared simplified time table (DW §3.6: no open Boothroyd tables exist) | `src/cadagent/dossier/dfa.py`, site section, tests | the fixture's worksheet matches a hand count; the table's source is printed on the page | T4, T13 |
| T19 | Tolerance stack-up helper: loops along a named direction from the mate graph, nominals from the model, tolerances from the dossier or a general class or the process table (Hubs FDM figures, DW §3.7), worst-case and RSS, flagged when only RSS passes | `src/cadagent/dossier/stackup.py`, tests | the textbook three-plate example reproduces the WC and RSS results | T13 |
| T20 | Drawing coverage: title block from the dossier, every critical dimension in the card appears on the drawing, datums declared, revision equals the model revision; drawings by the vendored text-to-cad `engineering-drawing` skill (MIT), never draftwright (AGPL) in-process | `src/cadagent/dossier/drawings.py`, skill update, tests | coverage report for the fixture; a missing critical dimension fails | T2, T13 |

**Parallelism.** Wave 1 has two independent roots, T1 and T3; T13 follows T1 on the same branch, T8 needs only the
card field from T1, and T12 needs T13's registry (or a plain-dict stand-in until it lands). Wave 2's gates share T3's
API and T13's declarations, so both should merge first. Wave 3 is three gates in parallel plus the CLI, which grows as
each gate merges. Wave 4 is the process layer. One implementer per task; a single session can carry a wave's tasks
sequentially if people are short.

**First tasks to hand out:** T3 with T12 and T8 on one branch (gate machinery, fixture, wall gate), and T1 with T13
on another (dossier schema and registry). T4 and T5 are the two gates that would have caught the incident, so they
follow as soon as both branches merge.

## 8. Out of scope, risks

- No new CAD kernel or viewer; everything is OCP through CadQuery, as today. Projects on build123d use `.wrapped`.
- Exact swept volumes are not attempted; sampled poses with a stated density are what the motion gate claims.
- The reviewer pass's quality depends on the vision model; the evaluation measures it rather than assuming it.
- Dossier YAML is work for the author. The lint makes a missing card a failure, which is the point, but the skill must
  keep the minimum card small (function, interfaces, one decision) so the process is used rather than skipped.
- Licences: ideas and API shapes are taken from MIT and Apache-2.0 projects (text-to-cad, build123d-mcp, agentcad);
  no code is copied from projects with other licences (DW §7).
