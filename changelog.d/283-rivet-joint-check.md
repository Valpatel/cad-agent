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
- The rivet check takes e/D on the hole, as MIL-HDBK-5J does, with Fbru linear between e/D 1.5 and 2.0. When a
  sheet has no bearing value at the joint's e/D, it says which edge distance would give one. Rows follow the FAA's
  layouts: two rows at 4D with the rows 4D apart, and three or more staggered rows at 6D with the rows 3D apart
  (#283).
