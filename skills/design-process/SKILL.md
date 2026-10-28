---
name: design-process
description: 'Use when building or changing a mechanical design with cad-agent (an enclosure, a robot, a mechanism, any assembly). Work section by section: frame each section with its requirements and interfaces before drawing, write a small spec card per part with its geometry, declare cavities, joints, fasteners and assembly steps in the build script, run cad-agent gates and cad-agent dossier and fix them in order, render the section review packet and critique it against the checklist with the measurements first, then hand the section to a separate reviewer. Includes the work-tracking rules.'
---

# Design process: section by section

A design that passes every per-part check can still be wrong as an assembly: contents outside the container that
should hold them, subassemblies that only touch by coincidence, boxes where a mechanism should be, and nobody who
looked. This process makes the design *declared* (what touches, holds, moves and fastens what), *measured* (the
gates), *justified* (a decision with the alternatives rejected for each part) and *reviewed* (a separate reviewer
with a checklist), one section at a time.

References: [`docs/dossier.md`](../../docs/dossier.md) (the YAML and the build-script declarations),
[`docs/gates.md`](../../docs/gates.md) (what each gate measures), [`docs/review-packet.md`](../../docs/review-packet.md)
(the packet and the checklist), [`docs/design-process-plan.md`](../../docs/design-process-plan.md) §5 (why).

## Before you start

- **Track it, as if the session could end any minute** (token budgets, crashes): one GitHub issue per section or
  piece of work, a `feat/` branch pushed at once, a draft PR with `Closes #N`. Commit and push at least every 30
  minutes, WIP commits included, and leave a checkpoint comment on the issue: done, next, what is running and where.
  The `cad-work-tracking` skill of the cad-agent agent kit spells this out, where it is installed.
- **Long runs go off the shared machine** (`cad-agent all`, the gates on a large assembly, FEA, CFD): run them
  detached on a compute host and record host role, command, log and done marker in the issue (the
  `cad-remote-runs` skill, where installed). Where agents share a workstation, one `nice`d job at a time.
- **Set `CAD_AGENT_ACTOR`** to your session id. Builds record it; a reviewer's sign-off is refused when it equals the
  build's.

## The loop, per section

### 1. Frame the section: no geometry yet

Write `dossier/sections/<id>.yaml`: its `purpose`, the `requirements` it serves (in `project.yaml`, each with the
user's words as `source.quote`), the `interfaces` to its neighbours with a `datum` and an `owner`, and the parts it
needs. An interface is a contract: the owner section changes the datum, the other side rebuilds.

Open questions become `status: open` decisions. If the model can answer one (a stack height, a screw length, a
clearance), compute it and decide; ask the user only what the model cannot know. An open decision blocks sign-off.

### 2. Write each part's card with its geometry

The minimum card is three things, in the same commit as the code that makes the part:

```yaml
- id: hopper
  function: Hold the ball store and funnel balls to the feed throat under gravity
  interfaces: [I7, I8, I9]
  decisions:
    - id: D41
      decision: Single-wall cone with a 55° floor
      why: balls roll at 35°; 55° clears the throat without a stirrer
      alternatives: [{option: stirrer paddle, rejected: adds a motor and a jam mode}]
```

Add the rest when it is known, not before: `material` with `wall_mm` when the process is chosen, `fasteners` when
the joint is chosen, `contains` when the part holds something, `loads` when the analysis is set up, `checks` naming
the gates and checks that verify it. Leave `status:` out: it is computed. The lint asks for what is missing.

### 3. Declare the geometry facts in the build script

Only the code knows which solid is the cavity, where an axis is, where each screw sits:

```python
from cadagent.dossier import Axis, part, cavity, joint, fastener, assembly, build

@part("hopper", section="S3")
def hopper(p): ...
@cavity("hopper", "hopper_cavity")                  # always a declared solid; nothing is derived
def hopper_void(p): ...
joint("I9", "revolute", parts=("flap", "hopper"), axis=lambda p: Axis(p["pivot"], (0, 1, 0)), range_deg=(0, 70))
fastener("screw_m3x8", clamps="lid", into="insert_0", name="screw_0", via="I7", tool="hex 2.5",
         at=lambda p: [Axis(p["seat_0"], (0, 0, -1))], length_mm=8, thread_start_mm=3, min_engagement_mm=4)
assembly.step(3, fit="lid", onto="hopper", direction="-Z", tool="hex 2.5", fasteners=["screw_0"])
```

Every part goes in exactly one assembly step with a direction; every fastener in the step that drives it. Model the
bought part (the McMaster STEP, the `mcmaster-parts` skill) and the mating connector, not a bounding box. Keep one
parameter authority (`cad/parameters.json`); never copy a number into the YAML that the build computes.

### 4. Build, gate and lint, and fix in order

```bash
cad-agent gates --build        # every gate that applies, then the dossier lint; exit 1 on a failure
cad-agent dossier              # the per-section status table and the lint findings
```

Fix in this order, rerunning after each group (a fix early in the list often clears findings later in it):

1. **Loader and join errors** (`unknown-id`, `card-without-shape`, `shape-without-card`, `unknown-cavity`): the
   declarations must agree before any gate means anything.
2. **Connectivity**: floating components and unrealised interfaces first; they are usually a part in the wrong place.
3. **Containment**: contents outside their cavity, contents in the container's wall.
4. **Fasteners**: seat, stack, holes, engagement, tip, length, then tool access.
5. **Assembly access**: coverage, then blocked insertions and tools at their steps.
6. **Motion**: collisions over each joint's range.
7. **Wall**, then the **lint's status rules** (decisions, traces, checks).

Never lower a threshold or widen a tolerance to pass. A finding that is not a defect becomes an explained
exclusion: `gates.free_parts` (a loose item), `gates.intended_overlaps` (a heat-set insert, a press fit, a screw's
thread envelope, which may name the fastener or an instance key) or `gates.ignore_pairs` (variants never fitted
together), each with a `reason`. A verdict read as **stale** is not a pass: rerun the gates. A section is done with
this step when `cad-agent dossier` shows it `gated`.

### 5. Render the section's review packet

```bash
cad-agent review-packet S3     # exports/review/S3/*.png and manifest.json
```

The packet is solid, opposite iso, x-ray, cuts through each cavity (side and plan), joint axis and fastener group,
exploded along the steps, access views along the screws, each joint's range ends, and the findings at their
witness points, captioned with the section and content hashes. Open every image before you use it: current,
lit, showing the feature.

### 6. Critique it yourself, measurements first

Read the manifest's `measurements` and `findings` before the images. Then answer every question in
`checklist.questions` (yes / no / unclear) from the views it names, and write the answers into the section's
`review: {self: ...}` block with the view file each refers to. Do not answer a count, a gap, a wall or an
engagement from an image: the gates measured those (`checklist.measured_only`). If an image and a measurement
disagree, the measurement wins and the disagreement is a finding (a wrong declaration or a misleading view). Fix
what you find and go back to step 4; do not hand over a section you would not sign.

### 7. Hand the section to a separate reviewer

Do not set `reviewed` or `signed_off` yourself; nothing you write can. Ask for a reviewer pass by an agent or person
that did not build the section (plan §5.3, task T11) and give it:

- the section YAML and `git diff <last reviewed commit> -- dossier/ cad/` (what changed since the last review);
- `exports/gates/*.json` and `exports/dossier-status.json`;
- the packet directory `exports/review/<section>/`, whose `manifest.json` carries the checklist and the part hashes.

The reviewer answers the checklist, marks each decision `justified`, `weak` (why) or `missing alternative`, checks
each requirement's trace, and writes `dossier/reviews/<section>-<date>.json` with its findings, its answers,
`signed_off`, its own `actor` and the `hashes` from the manifest's `parts.*.sha256`. Until `cad-agent
review-section` (T11) exists, the reviewer writes that record by hand in the shape `docs/dossier.md` gives. Any
change to a part's geometry voids the sign-off; the reviewer must not rebuild before signing (the record holds the
last build's actor). Answer every reviewer finding: fix it, or explain in the record why it stands.

### 8. Report

One line per requirement touched (its status from `exports/dossier-status.json`), per gate, per open finding, per
section with its status. Say what is not verified: CAD and simulation do not prove physical fit, strength, print
quality or that a mechanism works.

## For the agent that splits the work

Plan the sections from the requirements first, agree the interfaces between them, then hand one section per
implementer with this skill and its section file; sections whose interfaces are agreed can be built in parallel.
Run the reviewer pass on each section as it comes in and the full gates on the integrated assembly. Nothing is done
while a finding is open, a verdict is stale or a section lacks its sign-off; `cad-agent check` fails while any
section is below `gated`.
