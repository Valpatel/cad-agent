**New**
- `cadagent.mechanical.rivets` checks a riveted lap joint of sheet parts: the grip band with each sheet's thickness
  tolerance, the hole against the maker's drill range, edge distance (2D full strength, 1.5D floor), pitch (3D, 4D
  for several rows), t/D, the thinnest aluminium under an open-end rivet, the rivet's metal against each sheet, and
  the strength per pitch. Each check names its `sm-rivet-*` rule in `research/process-profiles.yaml`. It lists POP and
  McMaster-Carr blind rivets with hole, grip and rated strength, and `rivets_for()` finds those whose grip covers a
  stack (#283).
- `cadagent.formulas` gains riveted lap-joint equations: `rivet_shear_force`, `bearing_force`, `tearing_force`,
  `solid_sheet_force` and `lap_joint` (strength and efficiency per pitch). They are tested against MIL-HDBK-5J's shear
  and bearing tables and the worked lap joints of Abbud's lecture notes (#283).
