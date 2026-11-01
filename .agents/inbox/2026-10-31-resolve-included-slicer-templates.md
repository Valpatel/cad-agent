# Resolve included slicer templates before trusting a named profile

On 2026-10-31, Gyropup's unpowered-coupon preparation exposed a successful Bambu
slice with a PA6-CF label but generic 205°C startup. Nothing was sent to a printer.
The source failure and diagnostic slice are recorded in
[cad-agent #92](https://github.com/Valpatel/cad-agent/issues/92) and
[Gyropup's project fix](https://github.com/Valpatel/gyropup/commit/574a8bc12215a8d6a5859b412e42a06e64426060).

Read-only installed-profile inspection (`json.loads` of the BBL machine JSONs)
found that `Bambu Lab P1S 0.4 nozzle` inherits `fdm_bbl_3dp_001_common` and includes
five G-code templates. The generic ancestor contains `M109 S205`; the start
template contains a wait using `nozzle_temperature_initial_layer`. The released
`cadagent.manufacturing.slicer.flatten` followed only `inherits` and discarded the include
semantics. A filament label, positive mass/time or successful slicer exit did not
establish the executed heater commands.

Corrective rule: resolve parent settings, then includes in their declared order,
then explicit child keys; reject missing, cyclic, ambiguous or malformed profile
dependencies. Parse and hash the same bytes. Preserve profile identity separately
from the resolved settings and record every consumed dependency. This order is
visible in Bambu's
[PresetBundle.cpp](https://github.com/bambulab/BambuStudio/blob/79df7ae309be398ed30c9f397c13c9911c2edc57/src/libslic3r/PresetBundle.cpp#L4858-L4916).

Regression coverage belongs in `tests/test_slicer.py`, including the actual P1S
template graph, ordered precedence and missing/cyclic/duplicate/mutated inputs.
Flattening correctness does not establish executable G-code thermal correctness,
printer compatibility, material conditioning or physical print acceptance. Inspect
the actual generated commands and their order before deposition separately.
