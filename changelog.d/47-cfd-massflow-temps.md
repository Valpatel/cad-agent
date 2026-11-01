**New**
- `cadagent.simulation.cfd`: each fan's inlet and outlet air temperatures, mass-flow-weighted over the annulus at each end of its zone and computed by the solver (`surfaceFieldValue`, `weightedAverage` with `weightField phi`). They come with the net mass flows and the heat the outlet stream carries above the room: `fans[<fan>]['inlet_c']`, `['outlet_c']`, `['inlet_kg_s']`, `['outlet_kg_s']` and `['heat_carried_w']`. Use them in energy balances (Q = ṁ c_p ΔT). `air_through_fan_c` stays the fan zone's volume average (#47).
- `cadagent.simulation.cfd.energy_check()` and `results()['energy_conserved']`: a result whose heat leaving is more than 5 % off the heat put in (0.5 W when nothing is put in) says so in `warnings`. `stream_heat_w()` gives ṁ c_p (T − T_room) (#47).
- `tools/cfd_fan_figure.py`: two real runs of a 20 W box with an exhaust fan, recorded for the tests and drawn in the toolkit docs. A fan just under its opening carries more heat than is put in, because air goes round it again; a ducted fan with its hub plugged carries what is put in (#47).

**Changed**
- `steady` now also holds each fan's inlet and outlet temperatures to 1 °C, like every other temperature, in cases written from this release on. The convergence chart draws them, and labels the volume-average line "mean over the fan zone (by volume)" (#47).

**Projects must change**
- To get the weighted temperatures, write the case again (`ThermalCase.write`) and run it. A case written before this has no inlet or outlet faces, and continuing it does not add them, so its results keep only `air_through_fan_c`. Re-reading an old run moves no number (#47).
- Replace energy balances that use `air_through_fan_c` or `zones[<fan>]['T_c']` with `inlet_c` or `outlet_c` and that face's mass flow. A back-calculated temperature such as T_fan − Q/(ṁ c_p) moves by the gap between the two averages: #47 expects about 1 K with a dead hub and tip recirculation, and it is 0.1 K or less in the two recorded runs. Check `heat_carried_w` against the heat put in: more means the fan moves recirculated air, and its ṁ is not the flow through the parts upstream (#47).
- New runs judge two more temperatures per fan for `steady`, so `run_until_balanced` may continue a case longer (#47).
