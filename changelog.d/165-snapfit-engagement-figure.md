**New**
- `cadagent.mechanical.compliant.snapfit.engagement()`: a cantilever snap's closed form along the insertion. It gives
  the root strain, the deflection force and the push to mate as the mating edge rides the hook's lead, slides along its
  land and drops off. Its peak is `check_cantilever`'s numbers, the guide's Example I among them (P 32.5 N, W 58.5 N).
  `travel_at_strain()` gives where the strain first reaches an allowable (#165).
- An animated figure of a printed snap arm engaging, on the snap-fit page, the new `compliant/` README and the animated
  figures page (`docs/img/compliant/snap-engagement.svg`). One arm laid flat in two filaments: its root strain rises to
  1.38 %, a pass at 68 % of Polymaker PolyMide CoPA's 2.02 % and a fail at 139 % of Bambu PETG-CF's 1.00 % (the V3.0
  sheet), with CoPA's push to mate peaking at 10.1 N into a CoPA part. It is the calculator's output on stated inputs, recorded in
  `tools/anim/snap-engagement.scene.json`, not a measurement. The scene also records the hook's 7.4° turn with the
  tip, which the closed form ignores, and the push on the turned face (13.7 N for CoPA): near the top of a steep lead
  the closed form under-states the push. `tools/readme_anim.py --extract snapfit` records it again, and `--check`
  fails when the SVG is stale (#165).

**Changed**
- `cad-agent snapfit --output` and `check_spec_entry()`: each snap's `material` names the `friction` its forces used,
  or `null` where the guide's table has none (PLA, PETG) and none was declared, and its `friction_basis`: `given`,
  `same material` (the default: the plastic on itself) or `against steel` (#165).
