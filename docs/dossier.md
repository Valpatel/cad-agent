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
  of the wrong kind ("… names 'R4', which is not an interface in this dossier (it is a requirement)"), a wrong type,
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
  free_parts: [{part: ball, reason: loose in the hopper}]     # or a bare id (the lint asks for a reason)
  intended_overlaps: [{parts: [hopper, insert_m3], reason: heat-set insert}]
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

Declarations are checked when they are made (a free part without a reason, a revolute joint without a range, an
unknown kind, a bad id raise `RegistryError`). The same declaration run twice (a re-import) replaces itself; the same
name declared at two places raises. The module-level functions write to `cadagent.dossier.REGISTRY`; a tool or test
can use its own `Registry()` and its methods (`reg.part`, `reg.assembly.step`, ...).

`build(params=None, *, out_dir="exports", root=None, write=True)` calls every declaration with the parameters
(a mapping, a JSON path, or `cad/parameters.json` under `root`), and returns a `BuildResult`. A declaration that
fails raises `RegistryError` naming it and its `file:line`. `build_module("cad/build.py")` imports a build script and
builds it, adding `print_parts()`/`dossier_items()` when the script has them.

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
it as a shape without a card until its card exists. That list is the migration's to-do list.

### `exports/dossier-geometry.json`

```json
{
 "schema": "cad-agent.dossier-geometry/1", "units": "mm",
 "hash": "sha256 of OCCT BREP text v1, no triangulation",
 "parameters": {"file": "cad/parameters.json", "sha256": "..."},
 "shapes_dir": "exports/dossier-shapes",
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

- **Hashes** are content hashes: sha256 of the shape's BREP text (OCCT format version 1, no triangulation, so
  meshing for an STL changes nothing). The same build gives the same hash in any process; a changed dimension or
  placement changes it. An OCCT upgrade may change every hash, which only invalidates sign-offs (the safe
  direction). The reader recomputes some frame values when it loads a BREP, so a shape read back may write different
  bytes: compare the *recorded* hashes, never re-hash a loaded shape. `shape_sha256(shape)` is the function.
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
                                                         # checks each file against its recorded sha256
shapes = result.assembly_shapes()          # {key: cq.Shape in assembly coordinates}: "hopper", "ball#3",
                                           # "screw_m3x8:hopper-pan_base#0" (placed fasteners; fasteners=False omits)
result.owner("ball#3")                     # "ball": the part an instance key belongs to
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
else `gates.motion_samples`); the assembly gate uses the steps. Pair caches key on the recorded `sha256` values.

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

The dossier lint (plan T2) runs this with its own checks and decides what fails `cad-agent check`.
