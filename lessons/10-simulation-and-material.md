# 10 — Simulation, material and airflow

### Identify the exact bought part before sizing anything around it
- **Rule:** before an envelope, a clearance or a thermal model depends on a bought part, pin down its exact SKU and
  datasheet, and record the source next to the number. "Same vendor, same board, same purpose" is not the same part.
- **Incident:** the J501 enclosure was sized for a 110 × 100 × 50 mm cooler taken from Seeed's *reComputer mini J501*
  heatsink datasheet (SKU 100099421). The README's reference cooler is a different Seeed product, the WS-RDN-601
  (p-5970), 100 × 87 × 34 mm. The lid was about 16 mm taller than it needed to be, and the intake gap was wrong for
  airflow. Found on 2026-10-26 while building the thermal model from the datasheet.
- **Check:** every part dimension in the parameters names its source document. Where the user owns the part, ask them to
  measure it before printing.

### Judge material savings on slicer grams, not CAD volume
- **Rule:** a filament-reduction claim uses the slicer's grams and print time with a named profile
  (`cad-agent slice`). CAD volume misleads: walls and floors print as perimeters, skins and sparse infill.
- **Incident:** the Rev 0.7 base is 293 cm³ of solid, which would be 363 g of PLA, but it slices to 196 g. The lid is
  198 cm³ but slices to 164 g, because its 6 mm hex grille is mostly perimeters. The two parts don't scale the same way.
- **Gotcha:** Bambu Studio's command line needs flattened profiles (the system profiles inherit from parents;
  unflattened, the filament density is 0 and it reports 0 g) and `from: system` (a `User` process fails the printer
  compatibility check).

### A thinner shell must be re-checked under load, and the check must catch it
- **Incident:** the first Rev 0.8 lid had a 3.5 mm roof (down from 6 mm). Under 300 N on the lid it:
  - deflected 2.4 mm, twice Rev 0.7's 1.19 mm;
  - reached a 99.9th-percentile stress of 19.4 MPa, a safety factor of 1.3 on PLA's layer strength. Rev 0.7 had
    6.4 MPa.

  Its "design" stress (the peak away from the supports) read 56 MPa, but that was one element at a notch.
  - **Ribs:** the roof topology study showed radial ribs from the intake ring to the walls and corners.
  - **Sweep:** a parametric sweep (roof 3.5 / 4 / 4.5 mm × no, cross or star ribs, nine FEA runs) picked a 4.5 mm
    roof with the star ribs: 0.87 mm, 11.7 MPa (safety factor 2.1), 133 cm³ against Rev 0.7's 198 cm³.
  - **Where the stress was:** the hottest elements located the remaining weak points. Ribs ended on the lid's
    vent slots, and the rib-to-ring junctions were sharp inside corners.
- **Rule:** report deflection, a percentile stress (99.9th) and the peak with its location. One element at a notch is a
  mesh-dependent spike; a stiffness loss is real. Compare against the previous revision computed the same way, with
  the acceptance criteria fixed before the sweep.

### Thermal models of printed enclosures
- Check the plastic, not just the chip. PLA's heat-deflection temperature is 57 °C and PETG's is 69 °C (Bambu TDS); air
  leaving a cooler can exceed that. Report the walls' air temperature against a design limit below the HDT.
- A fan is a curve, not a flow rate. Model it on its datasheet curve (`cadagent.sim.cfd.Fan`) so the grille, fins and vents
  set the operating point.
- **Check that still air stays still before believing a buoyant case.** The first J501 runs used a uniform *static*
  pressure on the open boundary (`prghTotalPressure`). Real room air needs the hydrostatic gradient, so the model blew
  a fake wind through the room: about 350 m³/h, nine times the fan's free-air flow. That made the intake air read as
  room temperature and every number optimistic. The separate review agent on the cad-agent PR caught it from the
  boundary velocities (air going *down* through the top of a heated room). Fixed with `p_rgh` uniform (hydrostatic).
  An unheated test room now stays at 0.009 m/s mean, against 0.62 m/s before. All results were re-run.
- **Close the energy balance.** The heat leaving with the air must equal the heat put in. That check would have
  caught both the draft and a calibration that targeted the wrong power.
- Stacked 0.2-0.3 mm fins cannot be meshed at enclosure scale. Use a compact model: a porous block fitted to an
  analytic plate-fin model (`cadagent.sim.heatsink`). Then turn the CFD's fan flow and intake temperature into the plate
  temperature with the same model, and say so.
- Measure recirculation directly: the air temperature entering the fan, against the room. An intake ring from the
  grille to the fan is the fix when it is above room temperature.

### Steady CHT of a box in an open room converges slowly: calibrate on local quantities
- With the stable settings (velocity relaxation 0.3, energy 0.7), the heat leaving the room and the intake temperature
  drifted for more than 2000 iterations. That's the buoyancy-coupled circulation settling, not the linear solver:
  multigrid for energy changed nothing. Tighter energy solves, less energy relaxation, and frozen-flow energy passes
  all diverged in the first iterations.
- What works:
  - start cautious;
  - restart with faster relaxation once the flow has formed;
  - set the fin temperature from the block's own heat, exactly hA (T_fin - mean block air temperature), which is
    local and settles early;
  - keep the room's energy balance as the honest "has everything caught up" indicator;
  - give the room only modest margins (30 mm sides, 40 mm above): every extra litre of slow air is more iterations.
- The fan flow changed by 2× between a 16 mm and an 8 mm base mesh: thin shroud plates and grilles need their cells.
  Compare designs on the same mesh, and say which mesh it was.

### Compute is shared: one heavy solver at a time
- MPI CFD runs only as fast as its slowest rank. With topology optimisation, FEA (MKL/PARDISO threads) and another
  session's jobs on the same 24 cores, the solver slowed from 6 s to about 60 s per iteration. Pause or nice the
  others (`kill -STOP` on the ranks is safe), and never `pkill -f` a pattern that appears in your own command line.

- **Source:** 2026-10-26 (J501 session, Rev 0.8 thermal and material work); `cad/parameters.json` (`thermal`, `cooler`);
  `tools/thermal.py`, `tools/structure.py`, `tools/topology.py`; Seeed datasheets S03 and S05.
