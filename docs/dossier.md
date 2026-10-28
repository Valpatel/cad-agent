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
