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
- **Incident:** the Rev 0.8 lid's first roof (3.5 mm, down from 6 mm) under 300 N on the lid: deflection 2.4 mm, twice
  Rev 0.7. The design-stress safety factor came out at 0.44, set by one sharp corner. The FEA step caught it before any
  print; ribs placed by the roof topology study fixed it.
- **Rule:** report deflection and a percentile stress (99.9th) next to the peak, plus the peak's location. A single
  element at a notch is a mesh-dependent spike; a stiffness loss is real.

### Thermal models of printed enclosures
- Check the plastic, not just the chip. PLA's heat-deflection temperature is 57 °C and PETG's is 69 °C (Bambu TDS); air
  leaving a cooler can exceed that. Report the walls' air temperature against a design limit below the HDT.
- A fan is a curve, not a flow rate. Model it on its datasheet curve (`cadagent.cfd.Fan`) so the grille, fins and vents
  set the operating point. The J501 fan delivers only about a seventh of its free-air flow.
- Stacked 0.2-0.3 mm fins cannot be meshed at enclosure scale. Use a compact model: a porous block fitted to an
  analytic plate-fin model (`cadagent.heatsink`). Then turn the CFD's fan flow and intake temperature into the plate
  temperature with the same model, and say so.
- Measure recirculation directly: the air temperature entering the fan, against the room. An intake ring from the
  grille to the fan is the fix when it is above room temperature.

### Compute is shared: one heavy solver at a time
- MPI CFD runs only as fast as its slowest rank. With topology optimisation, FEA (MKL/PARDISO threads) and another
  session's jobs on the same 24 cores, the solver slowed from 6 s to about 60 s per iteration. Pause or nice the
  others (`kill -STOP` on the ranks is safe), and never `pkill -f` a pattern that appears in your own command line.

- **Source:** 2026-10-26 (J501 session, Rev 0.8 thermal and material work); `cad/parameters.json` (`thermal`, `cooler`);
  `tools/thermal.py`, `tools/structure.py`, `tools/topology.py`; Seeed datasheets S03 and S05.
