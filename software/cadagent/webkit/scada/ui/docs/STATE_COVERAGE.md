# SCADA state coverage

The library has broad animated coverage, but **not every component yet has a fully designed operating, failure and recovery lifecycle**. Shared controls, equipment-specific SVG states and placeholder-model behavior are separate layers. This reviewed inventory makes that difference visible before integration.

[Machine-readable review](./state-coverage.json) records every type and variant, declared state fields, observed geometry/CSS responses, actual motion checks, model availability, known gaps and exact source hashes. It is a reviewed source snapshot, not build-generated certification. Re-run the relevant checks and update the review when those sources change.

## What was verified

- 142 equipment types and 97 variants: 239 specimens, 4,153 isolated field samples.
- All 738 declared non-normal damage selections changed SVG appearance from normal; some share the same physical picture and depend on readable labels to distinguish the cause.
- 238 specimens showed active movement. The earthing switch intentionally has no continuous motion in its settled state.
- All 239 stopped animation for pause, offline and reduced motion. All 17 specimens declaring `connected` stopped activity when disconnected.
- 245 of 273 base numeric fields affected sampled SVG geometry, paint or cadence. The other 28 remained in the generic readout; this can be appropriate for telemetry or commands, but is not a custom equipment animation.
- All 239 have version 2 placeholder descriptors. Version 1 covers 80 base types and does not interpret variants. Descriptor availability does not prove complete model-to-view mapping.
- A targeted browser regression checks 55 healthy/failure/repaired states, including preserved leak effects while stopped and retained heat after a production fault.

These checks measure actual renders and animation clocks. They do not establish physical accuracy, complete state combinations, visual polish for every possible layout or a full accident/repair lifecycle. Low/high probes vary numeric fields for coverage; they are not validated plant operating points.

## Reading the matrix

**Equipment response** means at least one declared non-common field changes equipment geometry or CSS appearance. **Shared controls + animation** means the observed behavior relies on the common enable/pause/fault controls and family animation/damage machinery; it is not a claim of missing art. Both need domain review before being called complete. The numeric column counts fields coupled to the equipment SVG, excluding generic gauges. Readout-only fields are listed explicitly.

Warning/fault badges and accessible descriptions are shared infrastructure. Damage uses reusable profiles plus equipment anchors/details. Off does not mean cold, empty or isolated: supplied circulation, retained heat and environmental movement may remain. Pause/offline/reduced motion stop the drawing's clocks without erasing those conditions. Idle, zero speed, disconnected and repaired are distinct states; only use the fields actually declared for that component.

91 of97 variants reuse base geometry intentionally, mostly to declare circuit/medium compatibility. Five generator variants and the flash-water separator use different geometry. Variant reuse is not evidence of97 independent mechanical designs.

## Per-type inventory

| Type | Review classification | Numeric SVG / declared | Readout-only fields | Damage choices | Variants |
| --- | --- | ---: | --- | ---: | ---: |
| `digester` | Equipment response | 1/1 | — | 3 | 0 |
| `tank` | Equipment response | 1/1 | — | 3 | 0 |
| `gas-holder` | Equipment response | 1/1 | — | 3 | 0 |
| `mixing-tank` | Equipment response | 1/1 | — | 3 | 0 |
| `reactor` | Equipment response | 1/1 | — | 3 | 0 |
| `clarifier` | Equipment response | 1/1 | — | 3 | 0 |
| `silo` | Equipment response | 1/1 | — | 3 | 0 |
| `heat-exchanger` | Shared controls + animation | 0/2 | `load`, `temperature` | 3 | 8 |
| `filter` | Shared controls + animation | 0/1 | `load` | 3 | 0 |
| `gas-treatment` | Equipment response | 1/1 | — | 3 | 0 |
| `boiler` | Equipment response | 1/2 | `temperature` | 3 | 3 |
| `flare` | Equipment response | 1/1 | — | 3 | 0 |
| `pump` | Equipment response | 2/2 | — | 4 | 8 |
| `submersible-pump` | Equipment response | 1/2 | `load` | 4 | 8 |
| `dosing-pump` | Equipment response | 1/2 | `load` | 4 | 0 |
| `blower` | Equipment response | 1/2 | `load` | 3 | 1 |
| `compressor` | Equipment response | 1/2 | `load` | 4 | 0 |
| `motor` | Equipment response | 1/2 | `load` | 3 | 0 |
| `generator` | Equipment response | 2/2 | — | 3 | 5 |
| `transformer` | Shared controls + animation | 0/1 | `load` | 3 | 0 |
| `breaker` | Equipment response | 0/0 | — | 3 | 0 |
| `busbar` | Shared controls + animation | 0/1 | `load` | 3 | 1 |
| `battery` | Equipment response | 1/1 | — | 3 | 0 |
| `ups` | Equipment response | 2/2 | — | 3 | 0 |
| `solar-panel` | Equipment response | 1/1 | — | 3 | 0 |
| `electrical-meter` | Equipment response | 1/1 | — | 3 | 0 |
| `gate-valve` | Equipment response | 1/1 | — | 3 | 8 |
| `control-valve` | Equipment response | 1/1 | — | 3 | 8 |
| `check-valve` | Equipment response | 0/0 | — | 3 | 8 |
| `relief-valve` | Equipment response | 0/0 | — | 3 | 8 |
| `butterfly-valve` | Equipment response | 1/1 | — | 3 | 8 |
| `pressure-transmitter` | Equipment response | 1/1 | — | 3 | 0 |
| `flow-meter` | Equipment response | 1/1 | — | 3 | 0 |
| `temperature-sensor` | Equipment response | 1/1 | — | 3 | 0 |
| `level-sensor` | Equipment response | 2/2 | — | 3 | 0 |
| `gas-analyzer` | Equipment response | 1/1 | — | 3 | 0 |
| `plc-rack` | Equipment response | 1/1 | — | 3 | 0 |
| `plc-cpu` | Equipment response | 1/1 | — | 3 | 0 |
| `remote-io` | Equipment response | 0/1 | `load` | 3 | 0 |
| `hmi` | Equipment response | 0/0 | — | 3 | 0 |
| `scada-server` | Equipment response | 1/1 | — | 3 | 0 |
| `network-switch` | Equipment response | 1/1 | — | 3 | 0 |
| `radio` | Equipment response | 0/0 | — | 3 | 0 |
| `pipe` | Equipment response | 0/0 | — | 3 | 8 |
| `junction` | Equipment response | 0/0 | — | 3 | 0 |
| `conveyor` | Equipment response | 2/2 | — | 3 | 0 |
| `crusher` | Equipment response | 2/2 | — | 3 | 0 |
| `vibrating-screen` | Equipment response | 2/2 | — | 3 | 0 |
| `grinding-mill` | Equipment response | 1/2 | `load` | 3 | 0 |
| `rotary-kiln` | Equipment response | 2/3 | `load` | 3 | 0 |
| `oven` | Equipment response | 2/2 | — | 3 | 0 |
| `rack-oven` | Equipment response | 1/2 | `load` | 3 | 0 |
| `dryer` | Equipment response | 2/3 | `load` | 3 | 0 |
| `extruder` | Equipment response | 2/2 | — | 3 | 0 |
| `tablet-press` | Equipment response | 2/2 | — | 3 | 0 |
| `filling-line` | Equipment response | 2/2 | — | 3 | 0 |
| `packaging-line` | Equipment response | 2/2 | — | 3 | 0 |
| `granulator` | Equipment response | 2/2 | — | 3 | 0 |
| `forming-machine` | Equipment response | 2/2 | — | 3 | 0 |
| `drum-mixer` | Equipment response | 2/2 | — | 3 | 0 |
| `paper-machine` | Equipment response | 1/2 | `load` | 3 | 0 |
| `weigh-hopper` | Equipment response | 1/2 | `load` | 3 | 0 |
| `screw-feeder` | Equipment response | 1/2 | `load` | 3 | 0 |
| `centrifuge` | Equipment response | 2/2 | — | 3 | 0 |
| `flotation-cell` | Equipment response | 3/3 | — | 3 | 0 |
| `membrane-filter` | Equipment response | 1/1 | — | 3 | 0 |
| `reverse-osmosis` | Equipment response | 1/1 | — | 3 | 0 |
| `distillation-column` | Equipment response | 3/3 | — | 3 | 0 |
| `separator` | Equipment response | 2/2 | — | 3 | 1 |
| `cyclone` | Equipment response | 1/1 | — | 3 | 0 |
| `scrubber` | Equipment response | 2/2 | — | 3 | 0 |
| `cooling-tower` | Equipment response | 2/3 | `temperature` | 3 | 0 |
| `chiller` | Equipment response | 1/2 | `temperature` | 3 | 0 |
| `evaporator` | Equipment response | 3/3 | — | 3 | 0 |
| `electrolyzer` | Equipment response | 1/2 | `temperature` | 3 | 0 |
| `fuel-cell` | Equipment response | 1/2 | `temperature` | 3 | 0 |
| `wellhead` | Equipment response | 2/2 | — | 3 | 2 |
| `wind-turbine` | Equipment response | 2/2 | — | 3 | 0 |
| `aeration-basin` | Equipment response | 2/2 | — | 3 | 0 |
| `steam-turbine` | Equipment response | 2/3 | `temperature` | 3 | 0 |
| `fan` | Equipment response | 2/2 | — | 3 | 0 |
| `gas-turbine` | Equipment response | 4/4 | — | 4 | 0 |
| `heat-recovery-steam-generator` | Equipment response | 4/4 | — | 3 | 0 |
| `surface-condenser` | Equipment response | 4/4 | — | 3 | 0 |
| `deaerator` | Equipment response | 3/3 | — | 3 | 0 |
| `cooling-radiator` | Equipment response | 3/3 | — | 3 | 0 |
| `fuel-pressure-regulator` | Equipment response | 3/3 | — | 3 | 0 |
| `pwr-reactor-vessel` | Equipment response | 5/5 | — | 3 | 0 |
| `bwr-reactor-vessel` | Equipment response | 5/5 | — | 3 | 0 |
| `phwr-calandria` | Equipment response | 5/5 | — | 3 | 0 |
| `gas-cooled-reactor` | Equipment response | 4/4 | — | 3 | 0 |
| `sodium-reactor-vessel` | Equipment response | 5/5 | — | 3 | 0 |
| `molten-salt-reactor` | Equipment response | 5/5 | — | 3 | 1 |
| `nuclear-steam-generator` | Equipment response | 4/4 | — | 3 | 5 |
| `pressurizer` | Equipment response | 3/3 | — | 3 | 0 |
| `containment-structure` | Equipment response | 4/4 | — | 3 | 0 |
| `used-fuel-pool` | Equipment response | 3/3 | — | 3 | 0 |
| `control-rod-drive` | Equipment response | 2/2 | — | 3 | 0 |
| `neutron-monitor` | Equipment response | 1/1 | — | 3 | 0 |
| `radiation-monitor` | Equipment response | 1/1 | — | 3 | 0 |
| `reservoir` | Equipment response | 2/2 | — | 3 | 0 |
| `intake-gate` | Equipment response | 1/1 | — | 3 | 0 |
| `hydro-turbine` | Equipment response | 3/3 | — | 3 | 0 |
| `reversible-pump-turbine` | Equipment response | 3/3 | — | 3 | 0 |
| `power-inverter` | Equipment response | 1/1 | — | 3 | 2 |
| `heliostat` | Equipment response | 2/2 | — | 3 | 0 |
| `solar-receiver` | Equipment response | 2/2 | — | 3 | 0 |
| `parabolic-trough` | Equipment response | 4/4 | — | 3 | 0 |
| `tidal-turbine` | Equipment response | 3/3 | — | 3 | 0 |
| `wave-energy-converter` | Equipment response | 2/2 | — | 3 | 0 |
| `alternator` | Equipment response | 4/4 | — | 3 | 2 |
| `hv-circuit-breaker` | Equipment response | 1/1 | — | 3 | 0 |
| `disconnect-switch` | Equipment response | 1/1 | — | 3 | 2 |
| `earthing-switch` | Equipment response | 0/0 | — | 3 | 0 |
| `current-transformer` | Equipment response | 1/1 | — | 3 | 0 |
| `voltage-transformer` | Equipment response | 1/1 | — | 3 | 0 |
| `surge-arrester` | Equipment response | 1/1 | — | 3 | 0 |
| `capacitor-bank` | Equipment response | 2/2 | — | 3 | 0 |
| `shunt-reactor` | Equipment response | 2/2 | — | 3 | 0 |
| `protection-relay` | Equipment response | 1/1 | — | 3 | 0 |
| `switchgear-panel` | Equipment response | 1/1 | — | 3 | 0 |
| `gis-bay` | Equipment response | 2/2 | — | 3 | 0 |
| `automatic-transfer-switch` | Equipment response | 1/1 | — | 3 | 0 |
| `excitation-system` | Equipment response | 2/2 | — | 3 | 0 |
| `power-rectifier` | Equipment response | 1/1 | — | 3 | 0 |
| `fish-tank` | Equipment response | 3/3 | — | 3 | 0 |
| `biofilter` | Equipment response | 3/3 | — | 3 | 0 |
| `media-grow-bed` | Equipment response | 2/2 | — | 3 | 0 |
| `dwc-raft-bed` | Equipment response | 3/3 | — | 3 | 0 |
| `nft-channel` | Equipment response | 2/2 | — | 3 | 0 |
| `ebb-flow-table` | Equipment response | 2/2 | — | 3 | 0 |
| `drip-zone` | Equipment response | 1/2 | `moisture` | 3 | 0 |
| `aeroponic-chamber` | Equipment response | 2/2 | — | 3 | 0 |
| `grow-light` | Equipment response | 2/2 | — | 3 | 0 |
| `greenhouse-vent` | Equipment response | 2/2 | — | 3 | 0 |
| `shade-screen` | Equipment response | 2/2 | — | 3 | 0 |
| `evaporative-pad` | Equipment response | 2/3 | `humidity` | 3 | 0 |
| `dehumidifier` | Equipment response | 2/3 | `humidity` | 3 | 0 |
| `water-quality-probe` | Equipment response | 1/1 | — | 3 | 0 |
| `humidity-sensor` | Equipment response | 1/1 | — | 3 | 0 |
| `light-sensor` | Equipment response | 1/1 | — | 3 | 0 |
| `air-diffuser` | Equipment response | 1/2 | `oxygen` | 3 | 0 |

## Remaining design work

- **Model mapping:** tracking/position, arrester stress, capacitor steps and transfer-switch automatic behavior still need explicit dynamic models or documented display-only treatment. Control-rod position is currently instantaneous; there is no travel trajectory.
- **Relay observation binding:** the distribution substation currently has a CT data connection but no explicit relay observation binding, so VALUE remains its initial zero. A connected line does not implement sampled data or protection decisions.
- **Failure and recovery depth:** common injection and repair are implemented, but per-equipment deterioration, consequences, interlocks, repair prerequisites and recovery sequences are not complete. Do not infer these from a fault icon or a successful reset.
- **Distinct damage states:** blower/fan blade damage and seizure, and shade-screen stuck/actuator faults, share frozen geometry. They are labeled separately; not every mode has its own physical depiction.
- **Numeric-only values:** review the 28 listed fields by equipment role. Extra movement is useful only if it conveys a real declared variable; humidity, oxygen or command-load telemetry may remain a readable gauge.
- **Combination testing:** single-field coverage does not prove every simultaneous fault, connection, motion, inventory and mode combination. Add scenario-backed expectations as equipment is refined.

The recent semantic pass fixed healthy scan/traffic on lost automation power, invalid meter/transformer readings, broken sensor scans, blocked cyclone motion, starved fuel-cell output and failed aeroponic mist. The follow-up numeric pass bound the wellhead pressure pointer to its declared range, added retained UPS battery fill, suppressed/clipped biofilter wet bubbles at empty/low inventory and stopped/reversed flow-meter markers for zero/negative readings. The corresponding model pass aligned transfer-switch source selection, kept relay faults separate from trip commands, preserved degraded-but-available telemetry and removed damage caused only by a disabled load command. Those fixes do not close the remaining design work above.

## Standard for future additions

For each component, write a small state-design record before adding animation:

1. Identify physical parts, working medium and ports; cite primary references and label invented values.
2. Define enabled/off, operating range and idle separately. State which inventory, heat, pressure or external motion persists after stop.
3. Map every numeric/control field to a visible feature or explicitly justify a readout-only representation.
4. Define failure location, affected operating feature and persistent damage. Separate warnings, missing telemetry, degradation, physical failure and protection trip. Do not add fire to inert equipment just to satisfy a checklist.
5. Define the model transition and repair ownership. If the model is only a placeholder, name the missing dynamics and retain editable parameters.
6. Verify healthy → fault → repaired, off/zero/paused/offline/disconnected combinations where applicable, small and large renders, unique SVG IDs, readable labels and reduced motion.
7. Record actual evidence and remaining gaps. A common wrapper, passing schema or nonzero animation count is insufficient for a “complete” label.

Use [the style guide](../STYLE_GUIDE.md), [rendering API](./API.md), and the separate [placeholder model API](../../sim/docs/MODEL-API.md). The renderer must remain free of model clocks, IO and accident logic.

## Reusable checks

From a repository checkout:

```sh
node --test packages/scada-ui/tests/scada-components.test.mjs packages/scada-ui/tests/scada-fault-semantics.test.mjs packages/scada-ui/tests/scada-general-art.test.mjs packages/scada-ui/tests/scada-protection-art.test.mjs
python packages/scada-ui/scripts/qa/check-fault-semantics.py
python packages/scada-ui/scripts/qa/check-component-states.py --expected-count 142 --expected-variants 97
```

The first two were run during this focused review: 22 Node tests and 55 browser state cases passed. The full existing component-state QA remains the integrated release check, not a substitute for semantic design review. Browser checks require Playwright and Chromium and write evidence to an ignored work directory.

Source-linked evidence: [fault/readout regression](../../../../../../tests/webkit/scada/ui/scada-fault-semantics.test.mjs), [actual motion regression](../../../../../../tools/webkit/scada/ui/qa/check-fault-semantics.py), [all-component state QA](../../../../../../tools/webkit/scada/ui/qa/check-component-states.py), [v2 model semantics regression](../../../../../../tests/webkit/scada/sim/v2-presentation-semantics.test.mjs). Full raw probes are development evidence; the portable JSON carries their measurements and hashed source identity without depending on ignored files.
