# A clean connectivity DRC does not establish differential routing or return continuity

2026-10-26: the original A0 boards passed native ERC/DRC/parity, but a native copper extraction showed H/L separation and asymmetric layer paths. The first paired-route iteration still passed electrical clearances while the independent `tools/check_can_routing.py` found a 19.2809 mm reference-plane gap on two-port CAN0-L and a 21.8135 mm gap on four-port CAN3-H. These are geometric measurements, not oscilloscope results.

Cause: the general autorouter optimized net connectivity; neither pair coupling nor the reference plane below the pairs was constrained. Auxiliary tracks consumed ground immediately below paired top tracks. A total-copper-length sum also mixes termination branches with the actual connector path.

Correction: route CAN trunks as offset paths first; lock them before routing auxiliary nets. Add native bottom track/via keepout corridors with **copper pour allowed**, then refill both ground zones. Measure the shortest layer-aware host-to-DE9 copper path, require both TVS pads on those paths, compare layer transitions and length imbalance, measure the open termination branches, and sample reference copper beneath each trunk. Do not loosen ground-gap limits to hide a routing failure. Miter-corner spacing and connector fanouts need explicit, separate limits.

Evidence: after keepouts and rerouting, the two-port audit reported straight-trunk edge gap 0.2500 mm, no sampled trunk reference gaps, H/L imbalances 2.8379/2.6664 mm, and native DRC zero violations/unconnected/parity. Four-port routing remained under iteration at the time this incident was written; final reports bind the completed result to exact source hashes.

Reusable graph/path and paired-spacing functions live in cad-agent. Negative tests distinguish different-layer crossings, a termination branch from the main path, and separated versus paired traces. KiCad fabrication-rule validation uses an intentional temporary 0.8 mm minimum track-width violation to prove enforcement; KiCad may describe this as a board constraint rather than echo the custom rule name.

Limits: source-bound geometry checks cannot establish impedance, CAN data-rate limits, EMC or transient immunity. The flat ribbon and two-layer PCB are not a controlled 120-ohm channel. Physical system qualification remains mandatory.
