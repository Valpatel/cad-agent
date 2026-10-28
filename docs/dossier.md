# The design dossier

The dossier records a design the way a design review needs it: **requirements**, the **sections** the design is
broken into, a **spec card** for every part, the **interfaces** between parts and sections, the **decisions** with
the alternatives rejected, and the **assembly sequence**. It is written beside the CAD, in YAML, and joined by id to
the geometry the build script registers (`cadagent.dossier.registry`, [below](#declaring-geometry-in-the-build-script)).
The gates and the review site check it; the plan behind it is [`design-process-plan.md`](design-process-plan.md) §3.

What it does not do: a dossier that loads and lints proves the design is *declared*, not that it is right. The gates
check the geometry against the declarations; a reviewer checks the declarations against the requirements. Nothing in
it proves physical fit or strength.

## Layout

```
cad-agent.yaml                 cad: dossier: dossier/project.yaml
dossier/project.yaml           title, requirements, sections, interfaces, decisions, assembly, gates
dossier/sections/<id>.yaml     one section and its part cards
dossier/parts/<name>.yaml      a part card split out of its section (optional)
dossier/decisions.yaml         project decisions (the site's decisions format, extended)
dossier/reviews/<section>-<date>.json   reviewer sign-off records (written by the reviewer pass only)
exports/dossier-geometry.json  what the build script registered (written by the registry's build())
exports/dossier-status.json    every item's computed status and the lint findings (written by `cad-agent dossier`)
exports/gates/dossier-lint.json  the lint as a gate verdict
```

Paths inside the dossier are relative to the directory of `project.yaml`. `sections:` entries may be globs
(`"sections/*.yaml"`, loaded in sorted order) or inline mappings; a section's `parts:` entries may be paths to card
files or inline cards.

YAML, not JSON: requirements are user quotes and decisions need comments.

```python
from cadagent.dossier import load_dossier, load_project_dossier
d = load_dossier("dossier/project.yaml")             # raises DossierError on any error
d = load_project_dossier(load_project("."))           # via cad-agent.yaml; None when it has no dossier: key
d = load_dossier(path, strict=False)                  # errors in d.errors instead of raising (for a lint)
d.parts["hopper"].section, d.decisions["D41"].scope, d.findings   # findings: unknown keys, interface conflicts
```

## Ids, errors and findings

- Every id starts with a letter and uses letters, digits, `_`, `-` or `.`. Ids share **one namespace** across
  requirements, sections, parts, interfaces and decisions, so an interface's `between: [a, b]` is never ambiguous.
  Prefixes (`R4`, `S3`, `I7`, `D41`) are a convention, not a rule.
- **Errors** carry the file and line: a malformed id, a duplicate id, a reference to an id that does not exist or is
  of the wrong kind, an empty file (reported at the line that names it), a gate exemption without a reason ("… names 'R4', which is not an interface in this dossier (it is a requirement)"), a wrong type,
  a value outside its enumeration, a duplicate YAML key, invalid YAML, a missing file. `load_dossier` raises one
  `DossierError` listing all of them (`.issues`, and `.file`/`.line` of the first). When a file fails to parse,
  references are not resolved, so its ids do not cascade into unknown-id errors.
- **Findings** are warnings, never fatal: an unknown key (reported with its line and the keys that are known), and an
  interface declared differently by its two sections.
- References the loader does **not** resolve, because they point outside the YAML: `checks` (check and gate ids,
  resolved by the lint against `cad-agent.yaml` checks and the gate verdicts), fastener catalogue keys (`screws`,
  `fastened_by`, step `fasteners`), cavity names (`contains[].cavity`, resolved against the registry), a decision's
  `confirmation`. The lint (plan T2) and the registry join ([below](#joining-cards-and-geometry)) report those.

## Schema

`project.yaml`:

```yaml
title: Turntable feeder                    # optional
requirements:
  - id: R4
    text: Holds 40 balls
    source: {kind: user, quote: "it has to hold forty"}   # kind: user | standard | derived | research | agent
    verify_by: inspection                  # analysis | inspection | test | demo
    parent: R1                             # optional: the requirement this is derived from
    rationale: ...                         # optional
    checks: [gate:containment]             # optional: checks that verify it directly
    status: waived                         # optional; computed by the lint, so only `waived` belongs in YAML
sections: [sections/base.yaml, "sections/*.yaml"]
interfaces: [...]                          # project-level interfaces (usually between sections)
decisions: decisions.yaml                  # a file (list, or {decisions: [...]}) or an inline list
assembly:
  steps:
    - order: 1                             # unique integer; steps are sorted by it
      fit: pan_base                        # the part fitted at this step
      onto: bench_base                     # a part id or a list of them
      direction: -Z                        # +X..-Z or [x, y, z]: the way the part moves to its seat
      tool: hex_2.5
      fasteners: [screw_m4x12, screw_m4x12, screw_m4x12]
      access_check: gate:assembly          # optional check id
      note: ...
gates:                                     # the integrity-gate configuration (plan §4.1)
  touch_tol_mm: 0.01
  grounded: [bench_base]                   # parts the connectivity gate treats as ground
  free_parts: [{part: ball, reason: loose in the hopper}]     # a reason is required (a bare id is an error)
  intended_overlaps: [{parts: [hopper, insert_m3], reason: heat-set insert}]   # reasons required here too
  ignore_pairs: [{parts: [lid_a, lid_b], reason: variants, never fitted together}]
  strict_interfaces: false                 # true: an undeclared contact fails instead of warning
  motion_samples: 12
  # any other key is kept in GateConfig.extra (and reported) so a new gate option works before the schema knows it
```

A section (`sections/<id>.yaml`), with its part card exactly as in plan §3.2:

```yaml
id: S3
title: Hopper and feed                     # required
purpose: Hold 40 foam balls and present one at a time to the feed wheel
requirements: [R4, R7, R12]
author: agent-session-12                   # optional; the reviewer pass compares it with the reviewer
interfaces:
  - id: I9
    between: [hopper_flap, hopper]         # two different parts or sections
    kind: revolute                         # see "Interface kinds"
    datum: flap pivot axis, hopper frame
    loads: {torque: "0.1 N·m at the stop"}
    fastened_by: pin_3x20                  # optional catalogue key
    clearance: 0.2                         # mm: the gap the connectivity gate accepts along this interface
    owner: S3                              # the section (or part) that may change the datum
    description: ...
parts:
  - id: hopper
    function: Contain the ball store and funnel balls to the feed throat under gravity
    interfaces: [I7, I8, I9]
    loads: {static: "40 balls, 0.26 kg, on the floor cone", shock: "1 m drop on a corner (R12)"}
    material: {name: PETG, process: FDM, print_axis: "+Z", wall_mm: 2.4}   # or a bare name
    fasteners: [{to: pan_base, screws: screw_m3x8, qty: 4, via: I7}]
    contains: [{what: ball, count: 40, cavity: hopper_cavity, free: true}]
    decisions:
      - id: D41
        decision: Single-wall cone with a 55° floor
        why: Balls roll at 35°; 55° clears the feed throat without a stirrer
        alternatives:
          - {option: Stirrer paddle, rejected: adds a motor and a jam mode (DFMEA F3)}
          - {option: Vibrating floor, rejected: no evidence it clears 40 mm foam balls}
    checks: [gate:containment, gate:connectivity, fea:hopper-drop, print:hopper]
    status: reviewed                       # draft | built | gated | reviewed | signed_off
    author: ...
  - parts/hopper_flap.yaml                 # a card in its own file, loaded in place
decisions: [...]                           # section-scope decisions
review: {self: {...}}                      # the author's self-critique (plan §5.1); free-form here
```

**The minimum card** is three fields: `function`, `interfaces`, and one decision with `why` and one rejected
alternative. Everything else is added when it is known (loads when the FEA is set up, `contains` when the part holds
something, `fasteners` when the joint is chosen). Keep it that small at first; the lint asks for what is missing.

Decisions (`decisions.yaml`, or nested in a section or card):

```yaml
- id: D1
  title: Print in PETG
  decision: PETG for every printed part    # required
  why: tougher than PLA
  status: decided                          # decided | open | superseded
  date: 2026-10-27
  source: {kind: user, quote: "use PETG", ref: chat 2026-10-27}
  alternatives:                            # {option, rejected}; a bare string (the site's older format) loads
    - {option: PLA, rejected: creeps above 50 °C}   # with no reason, and the lint reports it
  consequences: ...
  confirmation: print:hopper               # MADR's confirmation: the check that shows the decision still holds
  superseded_by: D7
  author: agent-session-12
  scope: section                           # only in decisions.yaml: project (default) | section | part,
  section: S3                              #   with the section or part it applies to
```

A nested decision takes its scope from where it is written (`section` in a section, `part` in a card); `to_dict()`
leaves the implied scope out so the card round-trips. The site's `site: decisions:` key keeps working: point it at
the same file.

### Interface kinds

| Kind | Meaning | What the connectivity gate expects |
|---|---|---|
| `fastened`, `bonded`, `press_fit`, `snap_fit`, `contact` | rigid, 0 DOF | touching or overlapping (an overlap needs `gates.intended_overlaps`) |
| `gap` | rigid with a designed gap | apart by at most `clearance` |
| `revolute`, `slider`, `cylindrical`, `planar`, `ball` | a mechanism | a registered `@joint` with this interface id; contact is not required |
| `electrical`, `thermal`, `fluid`, `other` | what crosses is not (only) mechanical | nothing geometric unless also registered |

## Round trip

Every dataclass has `to_dict()`, which writes the YAML shape back with fields at their default left out. A card
split into its own file is written back as its path. `dump_yaml(section.to_dict())` gives YAML that loads to the same
section. Comments are not preserved: the dossier is edited by hand, `to_dict()` is for tools and tests.

## The `dossier:` key

`cad-agent.yaml` gains one key in its `cad:` section, `dossier: dossier/project.yaml`. `CadProject.dossier` is the
resolved path (None when absent), and `load_project_dossier(project)` loads it with file names shown relative to the
project root.

## Declaring geometry in the build script

Only the build code knows which solid is the cavity, where a joint axis is and where each screw sits, so those
facts are declared in code, next to the geometry (`cadagent.dossier.registry`). The YAML cards and the code are
joined by id.

```python
from cadagent.dossier import Axis, part, cavity, joint, fastener, assembly, build

@part("bench_base", section="S1", grounded=True)       # ground for the connectivity gate
def bench_base(p): ...

@part("hopper", section="S3")                          # registers the shape; joined to card "hopper"
def hopper(p): ...                                     # returns a shape in assembly coordinates, as today

@cavity("hopper", "hopper_cavity")                     # the void the containment gate tests against
def hopper_cavity(p): return hopper_inner(p)           # always a declared solid: the gates do not derive one

@part("ball", section="S3", free=True, reason="loose in the hopper")   # allowed to float; a reason is required
def balls(p): return [sphere_at(c) for c in p["ball_centres"]]         # a list = one instance per item

@joint("I9", kind="revolute", axis=lambda p: Axis(p["flap_pivot"], (0, 1, 0)), range_deg=(0, 70),
       parts=("hopper_flap", "hopper"), intended_contacts=[("hopper_flap", "hopper_stop")])
def flap_pivot(p): ...                                 # optional body, never called; joint() also works bare

fastener("screw_m3x8", clamps="hopper", into="pan_base", via="I7", tool="hex_2.5",
         at=lambda p: [Axis((x, y, p["flange_z"]), (0, 0, -1)) for x, y in p["flange_holes"]],
         length_mm=8, thread_start_mm=lambda p: p["flange"], min_engagement_mm=4,
         shape=lambda p: mcmaster_screw("91292A111"))  # optional solid, modelled in the McMaster screw frame

assembly.step(1, fit="pan_base", onto="bench_base", direction="-Z", tool="hex_2.5", fasteners=["screw_m4x12"] * 3)

if __name__ == "__main__":
    build()            # parameters from cad/parameters.json; writes exports/dossier-geometry.json
```

| Declaration | Arguments | Notes |
|---|---|---|
| `@part(name, section="", *, place=None, grounded=False, free=False, reason="")` | function `(p)` or `()` returning a CadQuery shape, Workplane, Assembly, build123d object or `TopoDS_Shape`; a list for several instances | `place`: a `cq.Location`, an `(x, y, z)` translation, or a list of them (instances); then the function returns the shape in its own frame |
| `@cavity(part, name)` | function returning one solid | in the part's frame: it follows the part's `place` |
| `joint(interface, kind="revolute", *, parts=(moving, fixed), axis, range_deg=None, range_mm=None, intended_contacts=(), samples=None)` | `kind`: `fixed`, `revolute` (needs `range_deg`), `slider` (`range_mm`), `cylindrical` (both), `planar`, `ball` | the axis is in assembly coordinates; `axis` may be a function of the parameters |
| `fastener(key, *, clamps, into, at, name="", via="", tool="", length_mm, diameter_mm, thread_start_mm, thread_depth_mm, min_engagement_mm, shape=None)` | `at`: one `Axis` per screw, from the head seat in the direction the screw advances | `thread_start_mm`: seat to first engaged thread; numbers may be functions; `shape` is placed at every axis (McMaster frame: origin on the seat, +Z out of the hole) |
| `assembly.step(order, fit, onto=None, *, direction="", tool="", fasteners=(), access_check="", note="")` | `direction`: `+X`..`-Z` or `(x, y, z)` | steps may also be written in `project.yaml`; when both exist with the same order they must agree |

Declarations are checked when they are made (a free part without a reason, a part both grounded and free, a revolute
joint without a range, an unknown kind, a bad id raise `RegistryError`). The same declaration run twice (a re-import)
replaces itself; the same name declared at two places raises. Parts, fasteners and cavities are separate kinds: a
fastener or cavity named like a part is refused, and fastener names (default `key:clamps-into`) never contain `#`. A
cavity belongs to a single-instance part (the containment gate must know which container it is).

**Which registry.** The module-level `part`, `cavity`, `joint`, `fastener`, `assembly.step` and `build` write to the
*current* registry: the innermost `with use_registry(reg):` block, else `cadagent.dossier.REGISTRY`.
`build_module()` builds every script in a fresh registry of its own, so nothing leaks between two builds in one
process (a test session, a watch loop, `cad-agent gates`); modules under the project root that the script imports are
re-imported, so their declarations land in that build too. A tool or test can also use its own `Registry()` and its
methods (`reg.part`, `reg.assembly.step`, ...).

`build(params=None, *, out_dir="exports", root=None, write=True)` calls every declaration with the parameters
(a mapping, a JSON path, or `cad/parameters.json` under `root`), and returns a `BuildResult`. A declaration that
fails raises `RegistryError` naming it and its `file:line`. `build_module("cad/build.py")` executes a build script
and builds it, adding `print_parts()`/`dossier_items()` (called again on every build, so new parameters give new
shapes). **`root`** defaults to the project root, `project_root(script)`: the nearest directory above the script with
`cad-agent.yaml` or `vptest.yaml` (else the parent of a `cad/` directory), never the current directory. `out_dir`
must be inside it. Every path in the record is relative to the root; a declaration made in a file outside the root
is recorded by its file name only, so the committed record carries no machine paths.

One `out_dir` holds one geometry record: a project with several build scripts gives each its own `out_dir`
(a second build into the same directory replaces the record and removes the first build's shape files).

### Migrating an existing build: `dossier_items()`

A build that keeps `print_parts() -> {name: shape}` adds one function, and moves parts to decorators one at a time
(a decorated part wins over a `print_parts()` entry of the same name):

```python
def dossier_items():
    return {
        "parts": {"hopper": {"section": "S3"}, "ball": {"section": "S3", "free": True, "reason": "loose"}},
        "cavities": {"hopper_cavity": {"part": "hopper", "shape": hopper_inner(P)}},
        "joints": [{"interface": "I9", "kind": "revolute", "parts": ("hopper_flap", "hopper"),
                    "axis": Axis(P["flap_pivot"], (0, 1, 0)), "range_deg": (0, 70)}],
        "fasteners": [{"key": "screw_m3x8", "clamps": "hopper", "into": "pan_base", "at": [...]}],
        "assembly": [{"order": 1, "fit": "pan_base", "onto": "bench_base", "direction": "-Z"}],
    }
```

Every `print_parts()` shape is registered; a part not yet given a section here is still a shape, and the join reports
it as a shape without a card until its card exists. That list is the migration's to-do list. The same checks apply
as for decorators (a free part needs a reason; grounded and free together are refused; a joint needs `interface`).

### `exports/dossier-geometry.json`

```json
{
 "schema": "cad-agent.dossier-geometry/1", "units": "mm",
 "hash": "cadagent.evidence.shape_content_hash: sha256 of the OCCT BREP text ...",
 "actor": "agent-session-12",
 "parameters": {"file": "cad/parameters.json", "sha256": "..."},
 "out_dir": "exports", "shapes_dir": "exports/dossier-shapes",
 "parts": {"ball": {"section": "S3", "grounded": false, "free": true, "free_reason": "loose in the hopper",
                    "sha256": "<hash of the instance hashes>", "count": 8, "declared_at": "cad/build.py:24",
                    "instances": [{"key": "ball#0", "sha256": "...", "file": "dossier-shapes/<sha256>.brep",
                                   "bbox": {"min": [x, y, z], "max": [x, y, z]}, "volume_mm3": 523.6,
                                   "solids": 1, "valid": true}]}},
 "cavities": {"hopper_cavity": {"part": "hopper", "sha256": "...", "file": "...", "bbox": {}, "volume_mm3": 0,
                                "solids": 1, "valid": true, "declared_at": "cad/build.py:20"}},
 "joints": {"I9": {"kind": "revolute", "moving": "hopper_flap", "fixed": "hopper",
                   "axis": {"origin": [31, 0, 70], "direction": [0, 1, 0]}, "range": [0, 70], "unit": "deg",
                   "intended_contacts": [["hopper_flap", "hopper"]], "samples": null, "declared_at": "..."}},
 "fasteners": {"screw_m3x8:hopper-pan_base": {"key": "screw_m3x8", "clamps": "hopper", "into": "pan_base",
               "via": "I7", "tool": "hex_2.5", "length_mm": 8, "thread_start_mm": 2.4, "min_engagement_mm": 4,
               "count": 4, "instances": [{"key": "screw_m3x8:hopper-pan_base#0", "origin": [-25, -25, 12.4],
               "direction": [0, 0, -1], "sha256": "...", "file": "...", "bbox": {}}], "declared_at": "..."}},
 "assembly": {"steps": [{"order": 1, "fit": "pan_base", "onto": ["bench_base"], "direction": "-Z",
                         "tool": "hex_2.5", "fasteners": ["screw_m4x12", "screw_m4x12", "screw_m4x12"],
                         "declared_at": "cad/build.py:40"}]},
 "physical_fit_verified": false
}
```

- **Hashes** are content hashes from one shared function, `cadagent.evidence.shape_content_hash(shape) -> str`
  (also exported as `cadagent.dossier.shape_content_hash` and `shape_sha256`): sha256 of the shape's BREP text, OCCT
  format version 1, without triangulation or normals, with the 7-digit per-shape flag lines removed. The registry
  and the gates use the same function, so a recorded hash is a valid gate cache key.
  - The same shape built the same way gives the same hash in any process and run (tested in a subprocess); a changed
    dimension or placement changes it (the location is part of the text, so even `place=(0, 0, 0)` changes it: the
    safe direction). Queries (`Volume`, `BoundingBox`, `isValid`, `fix`) and tessellation do not.
  - Two different constructions of the same geometry may hash differently: a cache miss, never a false match. An OCCT
    upgrade may change every hash, which only invalidates sign-offs.
  - A shape **read back** from its BREP file may hash differently, because the reader recomputes frame directions
    and location matrices (last-digit noise, signed zeros). Keep the recorded hash with the shape
    (`assembly_shapes(with_hashes=True)`, `content_hashes()`); never re-hash a loaded shape to identify it.
    `evidence.brep_content_hash(file_bytes)` checks a stored file against its record.
- **`actor`** is `CAD_AGENT_ACTOR` from the environment (an agent or session id, or a person), `unknown` when unset:
  the reviewer pass compares it with the reviewer's (plan §5.3).
- **Shapes** are written once each to `exports/dossier-shapes/<sha256>.brep` (content-addressed; files no longer
  referenced are removed). The directory gets its own `.gitignore` (`*`): it is build output, regenerated by every
  build. The JSON is the record to commit. Any gate cache belongs in a gitignored directory too.
- Numbers are rounded to 1e-6 mm so the JSON diffs cleanly; `bbox` is the tight OCCT box.
- Instance keys are `name` for a single instance and `name#0`, `name#1`, ... for several.

### Hand-over to the gates

The gates (`cadagent.gates`, plan §4) consume the registry through two calls and never import the build script:

```python
from cadagent.dossier import build_module, load_geometry

result = build_module("cad/build.py")                    # in the build process, or
result = load_geometry("exports/dossier-geometry.json")  # in another process (cad-agent gates): reads the BREPs,
                                                         # checks each file against its recorded hash; the root
                                                         # comes from the record's out_dir
shapes = result.assembly_shapes()          # {key: cq.Shape in assembly coordinates}: "hopper", "ball#3",
                                           # "screw_m3x8:hopper-pan_base#0" (placed fasteners; fasteners=False omits)
pairs = result.assembly_shapes(with_hashes=True)   # {key: (cq.Shape, content hash recorded at build time)}:
                                           # what the gates' Assembly.from_build() takes, nothing re-hashed
result.content_hashes()                    # {key: hash} for every instance, placed fastener and cavity
result.owner("ball#3")                     # "ball": the part an instance key belongs to
result.kind("ball#3")                      # "part" | "fastener" (None when unknown)
result.parts["ball"]                       # [cq.Shape, ...] instances in order
result.cavities["hopper_cavity"]           # cq.Shape, in assembly coordinates
result.joints["I9"]                        # {"kind", "moving", "fixed", "axis": Axis, "range", "unit", ...}
result.fastener_axes[name]                 # [Axis(origin=seat, direction=advance), ...]
result.geometry                            # the JSON above: grounded / free flags, hashes for cache keys
```

What each gate reads: connectivity uses `assembly_shapes()`, `grounded` and `free` (union of the code flags,
`gates.grounded`/`gates.free_parts` and `contains[].free` in the YAML), the joints and the dossier interfaces;
containment uses `cavities` and the instances of `contains[].what`; the fastener gate uses `fasteners` (axes, stack
numbers, placed solids) and the steps; the motion gate uses `joints` (axis, range, `intended_contacts`, `samples`,
else `gates.motion_samples`); the assembly gate uses the steps. Pair caches key on the recorded hashes.

What moves with a joint (settled, final): a joint names one `moving` part, and its body is the transitive closure
from it over `fixed` joints and fastener declarations (the fastener, what it clamps and what it threads into),
stopped at grounded parts and at any joint's `fixed` part (`cadagent.gates.relations.moving_bodies`, used by
`Assembly.from_build`, the connectivity gate and the motion gate). In a chain, a child joint's `fixed` part is
therefore its parent's moving part itself; see [`gates.md`](gates.md#motion-range-interference-cadagentgatesmotion).

### Joining cards and geometry

`join(dossier, geometry)` (geometry: a `BuildResult` or the JSON mapping, so the lint needs no CAD kernel) returns
`Issue`s with `file:line` (the card's YAML line, or the build script's declaration line):

| Code | Severity | When |
|---|---|---|
| `card-without-shape` | error | a part card no `@part` or `print_parts()` registers |
| `shape-without-card` | error | a registered part with no card |
| `section-mismatch` | error | `@part(section=...)` differs from the section the card is in |
| `unknown-cavity`, `cavity-wrong-part` | error | `contains[].cavity` missing, unregistered, or on another part |
| `contains-count` | error | `contains[].count` differs from the instances the build made |
| `joint-without-interface`, `joint-parts-mismatch`, `joint-kind-mismatch` | error | a joint with no interface of its id, other parties, or another kind (`fixed` matches any rigid kind) |
| `interface-without-joint` | error | a mechanism interface (`revolute`, `slider`, ...) with no `@joint` |
| `unknown-part`, `unknown-interface` | error | a joint, fastener, cavity or step names something that does not exist |
| `fastener-count` | error | a card's `fasteners[].qty` differs from the axes `fastener()` places |
| `fastener-not-registered`, `step-fastener-unregistered` | warning | declared in the card or a step, not yet in code |
| `step-conflict` | error | a step in `project.yaml` and in code with the same order disagree |

The dossier lint runs this with its own checks; every code in this table is an error or warning of the lint under
the same name.

## Lint and status

`cad-agent dossier` lints the dossier and computes the status of every part card and section. It writes
`exports/dossier-status.json` (the site and the report read this, never the YAML) and the lint verdict
`exports/gates/dossier-lint.json` (`cadagent.gate/1`, one check per finding plus one passing check per rule).
`cad-agent check` runs the same lint as its `cad-dossier` feature, and `cad-agent all` runs it after the build (as the last
step of `cad-agent gates`, [gates.md](gates.md#running-the-gates-cad-agent-gates)).
It needs no CAD kernel: it reads files only.

```python
from cadagent.dossier.lint import lint, lint_project, project_evidence, write_outputs, Evidence, RULES

res = lint_project(load_project("."))            # None without a dossier: key
res = lint(load_dossier(path, strict=False), Evidence(geometry=..., gates={...}, checks={...}, reviews=[...]))
res.findings          # Finding(code, message, where=file:line, severity, item, parts): sorted by file and line
res.parts["hopper"]   # {"status": "gated", "blocked_by": ["no current reviewer record"], "checks": [...], ...}
res.sections["S3"], res.requirements["R4"], res.decisions["D41"]
res.passed            # no error
write_outputs(res, "exports")
```

**What it reads.** The loaded YAML (loaded with `strict=False`, so loader errors such as `unknown-id` become findings
with their file and line), `exports/dossier-geometry.json`, every verdict in `exports/gates/`, the `cad.checks` of
`cad-agent.yaml` (a check passes when every `pass_key` is `true`, as in the report) and the reviewer records in
`dossier/reviews/*.json`.

**Check ids.** A `checks:` entry (on a card or a requirement, a decision's `confirmation`, a step's `access_check`)
is `gate:<name>` (the verdict `exports/gates/<name>.json`; `unrun` until it exists, and an error when `<name>` is
neither a known gate nor a written verdict) or the `id` of a `cad.checks` entry. Any other id is `unknown-check`.

### Rules

`cadagent.dossier.lint.RULES` is the list; every finding gives its file, line and code. Errors fail
`cad-agent check`; warnings are reported.

| Code | Severity | What must hold |
|---|---|---|
| `card-no-function` | error | a part card states its `function` |
| `card-no-interfaces` | error | a part card lists its interfaces (a free part, or a one-part dossier, may not) |
| `card-no-decision` | warning | the card, or another card or the section it is in, records a decision |
| `interface-not-party` | error | a card lists only interfaces whose `between` names the part or its section |
| `interface-one-sided` | error | an interface between two parts is listed on both parts' cards |
| `interface-datum-conflict` | error | two sections that declare one interface agree on its datum (plan §5.4) |
| `interface-conflict` | warning | they agree on its other fields |
| `fastener-via-mismatch` | error | a card's fastener runs `via` an interface between this part and `to` |
| `wall-undeclared` | error / warning | a card checked by `gate:wall` (error), or made by an additive process (warning), declares `material.wall_mm` |
| `decision-incomplete` | error | a decided decision has a `why` and at least one alternative |
| `alternative-no-reason` | error | every alternative says why it was `rejected` |
| `decision-open` | warning | an open decision; it also blocks its section's sign-off |
| `unknown-check` | error | every check id resolves (above) |
| `requirement-untraced` | error | every requirement is served by a section (or derived into one that is) |
| `requirement-unchecked` | error | every requirement has a check: its own, or one on a card of a section that serves it |
| `waiver-no-rationale` | error | a `waived` requirement says why |
| `requirement-status-ignored` | warning | a requirement's status is computed; only `waived` belongs in YAML |
| `section-no-requirements` | error | a section names the requirements it serves |
| `section-no-parts` | warning | a section has part cards |
| `section-below-gated` | error | every section has reached the required status (default `gated`, plan §5.4) |
| `status-not-earned` | error | a card says `reviewed` or `signed_off` only when a current reviewer record gives it |
| `status-overclaimed` | warning | a card's YAML status is not above the computed one |
| `review-invalid` | error | a reviewer record is JSON with `section`, `date`, `actor`, `signed_off` and `hashes` |
| `review-unknown-section` | error | a reviewer record names a section of the dossier |
| `review-same-actor` | error | the reviewer is not the build's actor, and neither is `unknown` (plan §5.3) |
| `review-stale` | warning | the latest review still matches the geometry; otherwise its sign-off no longer counts |
| `signoff-open-decision` | error | a section with an open decision is not signed off |
| `geometry-missing` | warning | the geometry record exists (without it every card stays `draft`) |
| `geometry-invalid`, `verdict-invalid` | error | the geometry record and the gate verdicts are readable |
| `verdict-stale` | error | a gate verdict's inputs match the current geometry record ([gates.md](gates.md#verdicts)); a stale or unbound verdict is not a pass |

The loader's errors and warnings ([above](#ids-errors-and-findings)) and the join's codes
([Joining cards and geometry](#joining-cards-and-geometry)) are findings under their own codes.

### The status machine

Each part card climbs one step at a time, and stops at the first step its evidence does not reach. `blocked_by`
says why it is not one step higher.

| Status | Reached when |
|---|---|
| `draft` | the card exists; it stays here while it has a lint error, or the build registered no shape for it |
| `built` | lint-clean, and the geometry record has its shape and content hash |
| `gated` | every check that applies passes: the card's `checks` plus every gate verdict in `exports/gates/`. A gate counts against the part when a failing finding names it, an instance `name#i`, a fastener that clamps it or threads into it, or a cavity of it, and against every part when a failing finding names nothing known; at least one check must apply |
| `reviewed` | a reviewer record for its section, by a separate actor, whose `hashes` match the current hash of every part in the section |
| `signed_off` | that record says `signed_off: true` and the section has no open decision |

A section's status is the lowest of its parts' (`draft` when it has no cards or a lint error of its own). Open
decisions count against the section they are in, or the section of the part they are scoped to (a `part:` decision
in `decisions.yaml` included). A lint error on any line inside a card is that card's (with `Evidence.root` set, as
`lint_project` does).

A requirement's evidence is its **own** `checks` and its derived requirements (`parent:`). The checks on the cards
of the sections that serve it satisfy the trace rule and are listed as `covered_by`, but they verify nothing on their
own: a wall gate passing says nothing about "the lid stays on". A requirement is

- `verified` when it has evidence and all of it passes (every own check passes, every derived requirement is
  `verified` or `waived`; for `verify_by: inspection`, also every section that serves it is at least `reviewed`);
- `failed` when an own check fails or a derived requirement failed;
- `not_tested` for `verify_by: test` or `demo` (cad-agent cannot run a test or a demonstration), and for a parent
  whose only open children are `not_tested`;
- `waived`, or else `unverified`.

**Geometry changes void sign-off.** A reviewer record binds the content hash of each part it reviewed (the
`sha256` of `parts.<name>` in `dossier-geometry.json`, the hash recorded at build time). When a part is rebuilt with
different geometry, no record matches any more: the section falls back to `gated` if its gates still pass on the new
build (`built` if not), the status file shows the voided record under `invalidated` with the parts that changed, and
the lint warns `review-stale`. A card that still says `status: signed_off` in its YAML is then `status-not-earned`:
statuses are computed, so leave `status:` out of the cards.

The status uses the newest record whose hashes match, so a revert to reviewed geometry restores its sign-off.

**Reviewer records** (`dossier/reviews/<section>-<date>.json`; the full schema and the reviewer pass are plan T11).
The lint reads these fields:

```json
{"schema": "cad-agent.review/1", "section": "S3", "date": "2026-10-28", "actor": "review-agent-7",
 "signed_off": true, "hashes": {"hopper": "<sha256>", "hopper_flap": "<sha256>"}, "findings": []}
```

A record whose `actor` is `unknown` or empty, or equals the build's `actor`, or a build whose `actor` is unknown, is
refused (`review-same-actor`); with no geometry record nothing is built, so no record is refused or counted. This is
only as strong as `CAD_AGENT_ACTOR`: a harness that sets the same value for both passes, or two different values for
one agent, defeats it. And the geometry record holds one `actor`, that of the **last** build, not of the build that
produced each hash (plan §5.3 asks for the latter; the registry does not record it yet). So a reviewer who rebuilds
unchanged geometry has their own sign-off refused (rebuild as someone else, or not at all, before signing off), and an
author whose unchanged geometry someone else rebuilt could sign their own work off. Per-part build actors in
`dossier-geometry.json` would close both; that belongs with the reviewer pass (T11).

**Stale verdicts.** A gate verdict counts only when it was computed from the current geometry record: its
`inputs.geometry.digest` must equal the record's (`cadagent.gates.verdict.geometry_digest`). Otherwise, or when it
has no `inputs`, the lint reports `verdict-stale` with the shapes that changed, the gate's checks read `stale`, and
the parts stay `built` until `cad-agent gates` runs again. Rebuilding the same geometry (another actor, a
declaration moved to another line) keeps verdicts current. For a project (`lint_project`, `cad-agent dossier`) the
lint also compares the gate's declarations and options, as `cad-agent check` does ([gates.md](gates.md#verdicts)).

**Limits.** A clean lint means the design is declared and agrees with the build. It does not mean the geometry is
right (the gates check that) or that it meets its requirements (the reviewer checks that).
