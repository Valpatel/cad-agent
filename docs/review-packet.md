# The section review packet (`cadagent.render.review_packet`)

A fixed set of captioned renders of one dossier section, with the measurements that come first: the gate verdicts
and findings for the section, their witness points, the content hash of every part shown, and the render checklist
the reviewer answers. The skill [`skills/design-process`](../skills/design-process/SKILL.md) tells an agent when to
make one; the plan behind it is [`design-process-plan.md`](design-process-plan.md) §5.1–§5.2 (task T10).

**What a packet is for.** Renders are for *diagnosis*, not proof. The gates measure (containment, contact, gaps,
engagement, clearances, counts); the renders let a reviewer see what the numbers describe and catch what no gate was
declared for (a part that is a plain box, a mating feature that is missing, a part in the wrong place). The research
behind this ([`research/design-workflows.md`](../research/design-workflows.md) §5): vision models do well on a few
named views with specific yes/no questions and measurements given first; they do badly at counting, small gaps,
hidden parts and unusual viewpoints. So the packet puts the measurements first, cuts and x-rays the section to show
the hidden parts, and the checklist never asks an image for a count or a gap.

## Making one

```python
from cadagent.render import review_packet

manifest = review_packet("S3", root=".")              # renders exports/review/S3/*.png + manifest.json
manifest = review_packet("S3", root=".", size=(1400, 1000), explode=1.0, context="neighbours", only=None)
```

```bash
cad-agent review-packet S3            # one section; with no section: every section of the dossier
cad-agent review-packet --list        # the views each section would get, without rendering (no CAD kernel)
cad-agent review-packet S3 --view solid-iso exploded     # re-render these; the others are kept while current
```

It reads, from the project at `root`: the geometry record (`exports/dossier-geometry.json` and its BREP shapes, via
`cadagent.dossier.load_geometry`), the YAML dossier (`cad: dossier:`), every gate verdict in `exports/gates/`, and
`exports/dossier-status.json` when it exists. It needs CadQuery, VTK and Pillow (the `cad` extra); without them it
raises `MissingDependency`. Run `cad-agent gates` first: a packet made from stale or missing verdicts says so in
its measurements, it does not hide it.

`cadagent.packet` has the kernel-free half: `plan_packet(section, record, dossier=None, verdicts=None,
status=None, lint=None, expected=None, ...)` works out the views, cut planes, framing, explode offsets, poses,
findings, witness points and the checklist from the JSON alone and returns the manifest without image hashes;
`plan_project_packet(section, root=...)` does the same from a project's files; `project_sections(root)` lists the
sections. `review_packet` renders the plan (`render_views`) and writes it (`write_manifest`).

| Argument | Default | Meaning |
|---|---|---|
| `section` | | a section id of the dossier, or (without a dossier) a `section=` value the build registered |
| `root` | `.` | the project root (with `cad-agent.yaml`) |
| `out_dir` | `<exports>/review/<section>` | where the PNGs and `manifest.json` go |
| `size` | `(1400, 1000)` | image size in pixels |
| `explode` | `1.0` | scale of the exploded offsets (0 turns the exploded view off) |
| `context` | `"neighbours"` | other sections' parts drawn faint: `neighbours` (sharing an interface, a fastener or a joint, or whose box is within 10 % of the section's size), `all`, or `none` |
| `only` | `None` | render only these view ids; another view keeps its earlier image while that image is current (same geometry digest, section hash and planned view, and the file still matches its hash), else it gets `file: null` and its old image is removed |

## The views

Every image is captioned with the section id and title and the view's name, with the section hash and the part
count in the subtitle, and a note saying what the view is for. Section parts are coloured one colour each (listed
in the manifest); parts allowed to float (`free`) are a contrast orange; placed fasteners are dark steel; context
parts from other sections are light grey and translucent. Each view is framed on its own box (`fit`): the
section, the cavity's part, the joint's parties, a box around the screw, the exploded or posed parts; context
outside it is cropped.

| View id | Kind | When | What it shows |
|---|---|---|---|
| `solid-iso` | `solid` | always | the section in place, front iso |
| `solid-rear` | `solid-rear` | always | the opposite iso, from behind and the other side |
| `xray-iso` | `xray` | always | the section's parts translucent, free items and fasteners opaque: what sits inside what |
| `cut-cavity-<cavity>` | `cut` | per registered cavity of a section part | a vertical plane through the cavity's box centre, normal +Y, seen from −Y |
| `cut-cavity-<cavity>-plan` | `cut` | the same | a horizontal plane through the centre, seen from above: the walls as a ring around the contents (an item through a wall shows here even when another item hides it in the side cut) |
| `cut-joint-<interface>` | `cut` | per joint with a party in the section | a plane containing the joint axis, as near vertical as possible |
| `cut-fastener-<name>` | `cut` | per group of fasteners with one catalogue key and one clamped part | a plane containing the first screw's axis: head, stack and thread (the fastener gate measures every screw; alike screws need one look) |
| `exploded` | `exploded` | when steps fit section parts | each part moved back out along its step's direction, later steps further; fasteners back out along their own axis from where their install step's part went |
| `access-from-<side>` | `access` | per distinct fastener axis direction | looking along the screws' advance from the tool's side (`top`, `bottom`, `front` = −Y, `back`, `left`, `right`, or the rounded vector), with neighbouring parts opaque since they can block the tool |
| `pose-<interface>-min`, `-max` | `pose` | per ranged joint whose moving part is in the section | the moving body at each end of its declared range |
| `findings` | `findings` | when a failing or warning finding has a witness point | `solid-iso` with a numbered callout at each witness |

## `manifest.json`

Written next to the images, `exports/review/<section>/manifest.json`. Schema `cad-agent.review-packet/1`. File
names in `views[].file` are relative to the manifest's directory; every other path is relative to the project
root. The file has no timestamp: an unchanged packet writes identical JSON.

```json
{
  "schema": "cad-agent.review-packet/1",
  "toolkit": "0.1.0",
  "dir": "exports/review/S3",
  "section": {"id": "S3", "title": "Hopper and feed", "purpose": "...", "requirements": ["R4", "R7"],
              "status": "gated", "blocked_by": ["no current reviewer record"], "file": "dossier/sections/hopper.yaml"},
  "geometry": {"file": "exports/dossier-geometry.json", "digest": "<geometry_digest(record)>", "actor": "agent-12"},
  "section_hash": "<sha256 over the sorted 'name sha256' lines of the section's parts>",
  "parts": {
    "hopper": {"sha256": "<parts.hopper.sha256 in the record>", "kind": "part", "count": 1, "free": false,
               "grounded": false, "color": "#3b7dd8", "function": "<the card's function>",
               "decisions": [{"id": "D41", "decision": "..."}], "status": "gated",
               "bbox": {"min": [0, 0, 0], "max": [60, 60, 80]}, "volume_mm3": 41200.5,
               "instances": [{"key": "hopper", "sha256": "..."}]},
    "screw_0": {"sha256": "...", "kind": "fastener", "count": 1, "key": "m3_shcs", "clamps": "lid",
                "into": "insert_0", "color": "#4a4f55", "instances": [{"key": "screw_0", "sha256": "..."}]}
  },
  "context": [{"key": "base", "section": "S1", "kind": "part", "sha256": "..."}],
  "measurements": {
    "gates": {"containment": {"file": "exports/gates/containment.json", "sha256": "<verdict_digest>",
                              "status": "pass", "pass": true, "stale": null, "checks": 12,
                              "section_checks": [{"id": "contains:hopper_cavity:ball#0:inside",
                                                  "status": "pass", "message": "..."}]}},
    "missing_gates": ["motion"],
    "lint": {"file": null, "computed": true, "sha256": "<verdict_digest>", "status": "pass",
             "pass": true, "stale": null, "section_checks": []}
  },
  "findings": [
    {"id": "F1", "gate": "containment", "check": "contains:hopper_cavity:ball#3:inside", "status": "fail",
     "message": "...", "parts": ["ball#3", "hopper"], "scope": "section", "stale": null,
     "witness": [{"label": "furthest_outside_point", "point": [31.0, 4.2, 40.0]}], "views": ["findings"]}
  ],
  "views": [
    {"id": "cut-cavity-hopper_cavity", "kind": "cut", "file": "cut-cavity-hopper_cavity.png", "sha256": "<png>",
     "caption": "S3 Hopper and feed: cut through hopper_cavity, side", "note": "...",
     "camera": [0, -1, 0], "clip": {"origin": [30, 30, 40], "normal": [0, 1, 0]},
     "fit": {"min": [8, 8, 2], "max": [62, 62, 84]},
     "target": {"cavity": "hopper_cavity", "part": "hopper", "contains": ["ball"]},
     "keys": ["hopper", "ball#0", "..."], "offsets": {}, "pose": null, "callouts": []}
  ],
  "rendered": 11,
  "dossier_digest": "<sha256 of the quoted dossier text>",
  "options": {"explode": 1.0, "context": "neighbours"},
  "render": {"size": [1400, 1000]},
  "checklist": {
    "schema": "cad-agent.render-checklist/1",
    "instructions": ["Read measurements and findings before the images", "..."],
    "answers": ["yes", "no", "unclear"],
    "measured_only": [{"id": "count", "topic": "how many items there are", "answered_by": ["gate:containment"]}],
    "items": [{"id": "contained-inside", "kind": "cut", "per": "cavity", "bad_answer": "no",
               "gate": "containment", "question": "In the cut through {cavity}, is every {what} ..."}],
    "questions": [
      {"id": "contained-inside:hopper_cavity:ball", "item": "contained-inside",
       "question": "In the cut through hopper_cavity, is every ball fully inside the inner wall of hopper?",
       "views": ["cut-cavity-hopper_cavity", "cut-cavity-hopper_cavity-plan"], "bad_answer": "no",
       "gate": "containment"}
    ]
  },
  "not_rendered": [{"what": "joint I12", "why": "planar joints have no range to pose"}],
  "limits": ["Renders are for diagnosis, not proof: ...", "..."],
  "physical_fit_verified": false
}
```

Field notes:

- **`parts`** holds the section's parts and the placed fasteners that clamp or thread into them. `sha256` is the
  hash the geometry record holds for the part (`parts.<name>.sha256`, a hash of its instance hashes; for a
  fastener, of its placed instances): the same hash a reviewer record (`dossier/reviews/*.json`, T11) binds in its
  `hashes`. `section_hash` changes when any of them does.
- **`measurements`** comes before the views on purpose: a reviewer (and the site) reads it first. Per gate:
  `sha256` is `verdict_digest` of the verdict quoted (its canonical JSON), `status` and `pass` its own, `checks` how
  many it has; `stale` is null for a current verdict, else the reason (`cadagent.gates.verdict.stale_reason`
  against the geometry record and, for a project, the gate's declarations and options, as `cad-agent check` judges
  it: an old verdict is shown as stale, not as a pass). `section_checks` are the verdict's checks that name a
  section part, an instance of one, a fastener of the section, or a cavity of a section part. `missing_gates` lists
  the gates a section card names in `checks` that have no verdict. `lint` is the dossier lint, which
  `review_packet` runs itself when it plans (the lint file records no inputs, so it cannot say whether it is
  current), so its `file` is null and `computed` true (a lint passed in from a file names the file, is marked
  stale, and makes the packet stale); its `section_checks` are only those that are not passing. `section.status` and `blocked_by` come from
  the same lint run.
- **`findings`** are the failing and warning checks among them (and every failing check that names no known part,
  with `scope: "unattributed"`, since it may concern any part). `stale` is the stale reason of the verdict it comes
  from (null when current). `views` names the views that show it (`findings` when it has a callout). `witness` collects the 3D points in the check's
  evidence (keys containing `point` or `centroid`, nested witnesses included), at most four per finding. The
  `findings` view numbers them F1, F2, ... as callouts; a finding without a point is listed, not drawn.
- **`views`**: `file` is null for a view not rendered (`only=`); `rendered` counts the views with an image (0 in a
  plan). `options` are the planning options and `render` the rendering ones (`size`; null in a plan): an earlier
  image is reused by `only=` only when both, the section hash, the geometry digest and the context all match.
  `keys` are the assembly keys drawn in the section's colours (plus the context parts in an access view);
  `offsets` (`{key: [dx, dy, dz]}`) the exploded displacements; `pose` (`{interface, kind, value, unit, body,
  keys, axis}`, plus `slide_mm` for a cylindrical joint) the joint position shown, as an offset from the modelled
  position, right-handed about the axis; `callouts` (`[{code, finding, label, point, text}]`) the numbered witness
  points; `fit` the box the camera frames. `camera` is a named view (`iso`, ...) or the direction from the scene
  to the camera; `clip` keeps the side its normal points to.
- **`not_rendered`** lists what the packet could not show and why: a card with no shape, a planar or ball joint
  (no range to pose), a fastener without axes, parts no step places (drawn in place in the exploded view).
- **`checklist`** is the machine-readable render checklist (below), instantiated for this section: one question
  per applicable item and target, each naming the views that answer it.
- **`context[]`**: each context item's assembly key, its section (empty for a fastener), `kind` (`part` or
  `fastener`) and content hash.
- **Staleness.** `cadagent.packet.packet_stale(manifest, record, verdicts=None, expected=None, lint=None)` is None
  while the packet is current evidence, else the reason: the geometry record changed; the packet quoted a verdict
  that was already stale, or a lint read from a file; or, given the current verdicts (with each gate's expected
  declarations and options) and lint, one of them was rewritten, added or removed, or is stale now (a dossier edit
  that changes a gate's declarations makes the quoted verdicts stale without touching the geometry).
  With `current=` (the packet planned again), it is also stale when the dossier text it quotes changed:
  `dossier_digest` covers the section's title, purpose and requirements, each part's function and decisions and the
  checklist questions (top-level `dossier_digest` in the manifest). `project_packet_stale(manifest, root)` gathers
  all of that for a project, kernel-free. A packet is evidence only
  for the hashes and verdicts it lists.

## The render checklist (`cadagent.packet.CHECKLIST`)

Specific yes/no questions, each tied to a view kind (plan §5.2). `per` says what an item is asked for: once per
section, or once per cavity and contents (from the cards' `contains`), joint, fastener group, access direction or
pose. `answers` are `yes`, `no` or `unclear`; `unclear`
is a valid answer and is never read as a pass. `bad_answer` is the answer that is a finding.

| Item | Asked of | Question (templated) | Finding when |
|---|---|---|---|
| `contained-inside` | `cut-cavity-*` (side and plan) | In the cut through {cavity}, is every {what} fully inside the inner wall of {part}? | no |
| `joint-bearing` | `cut-joint-*` | In the cut through {interface}, does {moving} turn or slide on a real bearing feature of {fixed} (a bore around the pin, a slot around the slider), with no material in its path? | no |
| `fastener-stack` | `cut-fastener-*` | In the cut through {fastener}, does the head sit on {clamps} and does the thread end inside {into}? | no |
| `mating-feature` | `exploded` | In the exploded view, does every part have a visible mating feature (bore, boss, slot, seat, screw hole) that meets one on its neighbour? | no |
| `assembly-order` | `exploded` | Does the explode order (later steps further out) look buildable: nothing shown going in through a part fitted before it? | no |
| `plain-box` | `solid-iso`, `solid-rear` | Does any part appear as a plain box with no features where a mechanism or interface should be? | yes |
| `matches-card` | `solid-iso`, `solid-rear` | Does every part look like the function its card states (`parts.*.function`)? | no |
| `floating` | `solid-rear` | Is anything floating in the opposite iso: a part with nothing visibly holding it? | yes |
| `hidden-overlap` | `xray-iso` | In the x-ray, does any part sit inside another part's material where no insert or press fit is declared? | yes |
| `fastener-access` | `access-from-*` | Looking along the screws' axis from the tool's side, is every head of {fasteners} visible and unobstructed? | no |
| `motion-contact` | `pose-*` | At this end of {interface}'s range ({value}), does {moving} touch anything other than its declared contacts ({contacts})? | yes |
| `findings-located` | `findings` | Is each numbered callout on the parts its finding names? | no |

**Not asked of an image** (`MEASURED_ONLY`): how many items there are, gaps and clearances under about a
millimetre, wall thickness, thread engagement and screw length, overlap volumes, and whether something moves
clear between the drawn poses. The gates measure those; the checklist names the gate for each and tells the
reviewer to read it from `measurements` instead. When a measurement and an image disagree, the measurement wins
and the disagreement is itself a finding (a wrong declaration, or a view that misleads).

## How a reviewer uses it (hand-off to T11)

The reviewer pass (plan §5.3, T11) is given the section YAML, the gate verdicts, this manifest and its images, and
the diff since the last review. It reads `measurements` and `findings` first, then answers every question in
`checklist.questions` from the views listed with it, and writes its record (`dossier/reviews/<section>-<date>.json`)
with the part hashes from `parts.*.sha256`. The answer shape T11 is expected to use:

```json
{"checklist": [{"id": "contained-inside:hopper_cavity:ball", "answer": "yes", "view": "cut-cavity-hopper_cavity-plan",
                "note": ""}]}
```

## Limits

The packet shows the model, not the part: renders do not prove fit, strength or that a mechanism works. A view is
tessellated (chord error), so a small gap or overlap can look closed or open; that is why the checklist does not
ask for one. Cut planes are fixed (through a cavity's box centre, through an axis); a defect away from the plane is
only seen in the other views. Poses are the declared range ends, not the path between them (the motion gate samples
the path). Exploded offsets are illustrative: their direction comes from the declared steps, their length from the
section's size.
