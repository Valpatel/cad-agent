**New**
- `cadagent.formulas`: `torsion_shear_strain_rect` and `torsion_snap_bar` (a rectangular bar twisted by a lever, one
  bar or a rocker on two, against the Covestro allowable shear strain (1 + ν) ε), checked against Saint-Venant's series
  solution. It flags a twist large enough for the trapeze effect to add more than a tenth to the torque (#161).
- `cadagent.formulas`: `thread_radial_pressure`, `boss_hoop_stress` and `screw_boss` (a thread-forming screw in a
  plastic boss: the clamp band from a friction band, the stripping force and torque, Covestro's tightening window, the
  hoop stress at the bore and the DELTA PT maker's 2 d proportions) (#161). The drive torque makes no clamp: pass a
  measured `drive_torque`, or the clamp band allows for as much as the window permits.
- `cadagent.mechanical.bosses.printed_boss`: the same check for a boss printed in a datasheet filament, upright or
  lying, with DELTA PT sizes and where each number comes from. No published pull-out data for printed bosses was
  found, so it says the result is a starting point to test, not a rating (#161).
- Two site demos: the torsion-snap explorer, `<cad-torsion-snap>`, on Snap fits, and the screw-boss explorer,
  `<cad-printed-boss>`, on the new Screw bosses page. Both run the browser port of the Python, tested on shared
  vectors (#161).

**Changed**
- `nut_factor` takes the thread's flank angle (default 60°, the ISO thread), for 30° thread-forming screws (#161).
- `PrintedMaterial` gains `strength(direction)`: the lowest datasheet tensile strength along or across the layers
  (#161).
