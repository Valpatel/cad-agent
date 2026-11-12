# A correct rest pose does not validate a rotating component's pivot

## What happened

On 2026-10-28 the Gyropup user reported motors and a feed spinner moving out of the turret body during firing.
The product audit found a translated CAD assembly whose subjoint pivot metadata missed that translation. The
browser subtracted the same bad pivot when loading a mesh and added it back through the parent position: home
looked correct, while rotation exposed the wrong orbit. Product evidence belongs in Valpatel/gyropup; cad-agent
issue #60 tracks the generic validation gap.

## Receipt

Measured in the isolated cad-agent feature checkout on 2026-10-28:

```text
$ python -m pytest -q tests/mechanical/test_motion_trace.py
43 passed in 0.24s
$ python - <<'PY'
import runpy
from cadagent.mechanical.motion_trace import validate_motion_trace
f = runpy.run_path('tests/mechanical/test_motion_trace.py')
c = f['contract']()
r = validate_motion_trace(c, f['trace'](c, 'offset-pivot'))
print(r['status'])
print(r['components']['rotor'])
PY
fail
{'points': 4, 'joint': 'spin', 'max_error_mm': 96.0, 'max_anchor_error_mm': 96.0, 'max_radius_error_mm': 96.0, 'worst_sample': '6', 'worst_point': 0}
```

This receipt uses a synthetic 48 mm offset pivot with correct home placement. It is a regression proof of the
failure class, not a claim that cad-agent captured Gyropup's live browser in this command.

## Why the earlier guard missed it

The CAD motion gate poses CAD solids from its own joint definitions. It does not execute exported scene graphs.
Distances within a rigid mesh remain correct even under the wrong orbit, and a shared incorrect pivot declaration
can make both the animation and a same-source oracle agree.

## Corrective rule and limits

Capture actual rendered landmarks and compare them with independently sourced home frames, joint axes and
component ownership. Require off-axis samples and nested poses, plus home and travel limits; deliberately offset
a pivot and require failure. The guard is `tests/mechanical/test_motion_trace.py` in the existing pytest/CI runner; the
product must additionally capture its actual assets. Durable guidance is in
[the rendered-motion domain](../domains/rendered-motion.md).

The trace validates sampled kinematics only. It cannot prove reference truth, mesh identity, continuous collision
clearance, dynamics or hardware safety. Missing independent reference evidence remains a review limitation.


## A sampled group still needs other followers' home transforms

On 2026-11-12, maintainer follow-through for #581 / PR #582 reproduced two independently reviewed failures at
collaborator commit `3f6781b6`: containment and packet poses omitted `F = D + 10 mm` when independent joint C
moved with D held at zero. The full motion collision/closure path already placed F correctly, so the consumers
were checking different assemblies. The cause was forwarding only active-group matrices to containment and
building packet moves only from followers of the selected driver.

```text
PYTHONPATH=software <existing Python 3.12/CadQuery 2.8.0 provider> -m pytest -q \
  tests/review/test_gate_motion.py::test_containment_keeps_other_groups_follower_home_offset \
  tests/review/test_packet.py::test_independent_pose_preserves_follower_home_offset
2 failed in 2.65s (before implementation correction)
```

The native independent oracle explicitly placed container C and follower F at all four C/D endpoints and passed;
omitting F's offset failed. The packet oracle requires four noncoplanar assembly-frame landmarks to move by the
independently specified displacement, with positive/negative held-driver ranges and a nested carrier case.
A separate native shape probe uses an offset Y axis and closed-form trigonometry. These checks do not derive
expected points from the suspect follower resolver.

Corrective rule: pass the complete physical pose to geometric consumers; retain the active-body set only for
selecting relevant declarations. Initialize packet followers from their held driver values before overriding the
selected driver, and compose carrier transforms innermost first. When the move list also carries a cylindrical
joint, preserve both its rotation and slide in framing and native shape application.

Limits: these are discrete CAD, plan and native-shape checks, not renderer captures, continuous clearance,
constraint solving, load or physical qualification. The `follows` ratio remains a declared assumption, checked only
where an observable `closes` point is supplied. No printed product geometry was changed.
