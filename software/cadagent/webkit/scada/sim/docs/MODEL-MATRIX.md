# Placeholder model matrix

Version 0.4.0 includes version 2 model descriptors for all 142 symbol types. The original 80-type version 1 registry and behavior remain available. The 60 scenarios contain 20 version 1 industrial examples and 40 version 2 power, agriculture and electric batch-oven examples.

Select the contract explicitly when creating a new model: `createModelDefinition(system)` retains version 1; `createModelDefinition(system, {version:2})` or `createV2ModelDefinition(system)` creates version 2. Existing files select their runtime by `model.version`. A dash in the version 1 column means the type requires version 2.

The table is derived from `MODEL_DESCRIPTORS` and `V2_MODEL_DESCRIPTORS`. It lists the base type's default circuit IDs and roles; each resource circuit owns its own inventory, heat, and tracer amounts. A passage can retain finite material while transferring it. Source/sink roles are explicit external boundaries. Energy roles are independent of the component family, and scenario authors can edit allowed roles and supply assumptions.

Explicit variants can change ports, energy domains, fluid compatibility, and default models. Inspect `V2_VARIANT_DESCRIPTORS` or `getV2ModelDescriptor(type, {variant})` for the selected contract; variant defaults are not combined in this base-type table. Parameters, units, bounds, inputs/outputs, visual-state fields, assumptions, and complete editable templates are available through `@valpatel/scada-sim/models-v2` and [model-registry-v2.json](../metadata/model-registry-v2.json). The unchanged version 1 metadata is [model-registry.json](../metadata/model-registry.json).

| Symbol type | Version 1 family | Version 2 family | Version 2 resource circuits (role) | Version 2 energy role | Explicit damage modes |
| --- | --- | --- | --- | --- | --- |
| `digester` | processor | processor | water (storage), gas (storage) | load | leaking, ruptured, corroded |
| `tank` | storage | storage | water (storage) | — | leaking, ruptured, corroded |
| `gas-holder` | storage | storage | gas (storage) | — | leaking, ruptured, corroded |
| `mixing-tank` | processor | processor | water (storage) | load | leaking, ruptured, corroded |
| `reactor` | processor | processor | water (storage), gas (storage) | — | leaking, ruptured, corroded |
| `clarifier` | processor | processor | water (storage), sludge (storage) | — | leaking, ruptured, corroded |
| `silo` | storage | storage | solids (storage) | — | leaking, ruptured, corroded |
| `heat-exchanger` | heater | heater | hot (passage), cold (passage) | — | leaking, fouled, overheated |
| `filter` | processor | processor | water (passage) | — | fouled, leaking, ruptured |
| `gas-treatment` | processor | processor | gas (passage) | load | fouled, leaking, corroded |
| `boiler` | heater | heater | fuel (sink), air-exhaust (passage), water (passage) | — | overheated, refractory-damage, fuel-leak |
| `flare` | heater | heater | fuel (sink), exhaust (passage) | — | overheated, refractory-damage, fuel-leak |
| `pump` | pump | pump | process (passage) | load | cavitating, leaking, seized, overheated |
| `submersible-pump` | pump | pump | process (passage) | load | cavitating, leaking, seized, overheated |
| `dosing-pump` | pump | pump | chemical (passage) | load | cavitating, leaking, seized, overheated |
| `blower` | pump | pump | process (passage) | load | blade-damage, seized, overheated |
| `compressor` | pump | pump | gas (passage) | load | cavitating, leaking, seized, overheated |
| `motor` | load | load | — | converter | jammed, worn, overheated |
| `generator` | generator | generator | fuel (sink), air-exhaust (passage) | source | short-circuit, overheated, burnt |
| `transformer` | processor | processor | — | relay | short-circuit, overheated, burnt |
| `breaker` | valve | valve | — | relay | short-circuit, overheated, burnt |
| `busbar` | processor | processor | — | relay | short-circuit, overheated, burnt |
| `battery` | energy-storage | energy-storage | — | store | short-circuit, overheated, burnt |
| `ups` | energy-storage | energy-storage | — | store | short-circuit, overheated, burnt |
| `solar-panel` | generator | generator | — | source | short-circuit, overheated, burnt |
| `electrical-meter` | sensor | sensor | — | — | drift, broken, fouled |
| `gate-valve` | valve | valve | process (passage) | — | stuck, leaking, corroded |
| `control-valve` | valve | valve | process (passage) | — | stuck, leaking, corroded |
| `check-valve` | valve | valve | process (passage) | — | stuck, leaking, corroded |
| `relief-valve` | valve | valve | process (passage) | — | stuck, leaking, corroded |
| `butterfly-valve` | valve | valve | process (passage) | — | stuck, leaking, corroded |
| `pressure-transmitter` | sensor | sensor | — | load | drift, broken, fouled |
| `flow-meter` | sensor | sensor | — | load | drift, broken, fouled |
| `temperature-sensor` | sensor | sensor | — | load | drift, broken, fouled |
| `level-sensor` | sensor | sensor | — | load | drift, broken, fouled |
| `gas-analyzer` | sensor | sensor | — | load | drift, broken, fouled |
| `plc-rack` | controller | controller | — | load | comms-loss, io-fault, power-loss |
| `plc-cpu` | controller | controller | — | load | comms-loss, io-fault, power-loss |
| `remote-io` | controller | controller | — | load | comms-loss, io-fault, power-loss |
| `hmi` | network | network | — | load | comms-loss, io-fault, power-loss |
| `scada-server` | network | network | — | load | comms-loss, io-fault, power-loss |
| `network-switch` | network | network | — | load | comms-loss, io-fault, power-loss |
| `radio` | network | network | — | load | comms-loss, io-fault, power-loss |
| `pipe` | pipe | pipe | process (passage) | — | blocked, leaking, corroded |
| `junction` | pipe | pipe | fluid (passage) | — | blocked, leaking, corroded |
| `conveyor` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `crusher` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `vibrating-screen` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `grinding-mill` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `rotary-kiln` | heater | heater | material (passage), fuel (sink), air (passage), exhaust (passage) | load | overheated, refractory-damage, fuel-leak |
| `oven` | heater | heater | material (passage), fuel (sink), air (passage), exhaust (passage) | load | overheated, refractory-damage, fuel-leak |
| `rack-oven` | — | heater | material (passage), air (passage), exhaust (passage) | load | overheated, element-fault, door-seal-leak |
| `dryer` | heater | heater | material (passage), fuel (sink), air (passage), exhaust (passage) | load | overheated, refractory-damage, fuel-leak |
| `extruder` | processor | processor | solids (passage), product (passage), water (passage) | load | jammed, worn, overheated |
| `tablet-press` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `filling-line` | processor | processor | water (passage), product (passage) | load | jammed, worn, overheated |
| `packaging-line` | processor | processor | product (passage) | load | jammed, worn, overheated |
| `granulator` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `forming-machine` | processor | processor | product (passage) | load | jammed, worn, overheated |
| `drum-mixer` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `paper-machine` | processor | processor | slurry (passage), product (passage) | load | jammed, worn, overheated |
| `weigh-hopper` | storage | storage | solids (storage) | load | leaking, ruptured, corroded |
| `screw-feeder` | processor | processor | solids (passage) | load | jammed, worn, overheated |
| `centrifuge` | processor | processor | water (passage), solids (passage) | load | jammed, worn, overheated |
| `flotation-cell` | processor | processor | slurry (storage), air (storage) | load | jammed, worn, overheated |
| `membrane-filter` | processor | processor | water (passage) | load | fouled, leaking, ruptured |
| `reverse-osmosis` | processor | processor | water (passage) | load | fouled, leaking, ruptured |
| `distillation-column` | heater | heater | water (storage), gas (storage) | load | leaking, fouled, overheated |
| `separator` | processor | processor | fluid (storage), gas (storage), water (storage) | load | leaking, ruptured, corroded |
| `cyclone` | processor | processor | gas (passage), solids (passage) | load | blocked, worn, leaking |
| `scrubber` | processor | processor | gas (storage), water (storage) | load | fouled, leaking, corroded |
| `cooling-tower` | heater | heater | water (passage), air (passage) | load | fouled, fan-fault, leaking |
| `chiller` | heater | heater | water (passage) | load | refrigerant-leak, compressor-fault, overheated |
| `evaporator` | heater | heater | water (storage), gas (storage) | load | leaking, fouled, overheated |
| `electrolyzer` | processor | processor | water (passage), gas (passage) | load | membrane-damage, leaking, overheated |
| `fuel-cell` | generator | generator | gas (passage), water (passage), air (passage) | source | fuel-starved, stack-damage, overheated |
| `wellhead` | source | source | fluid (passage), gas (passage) | — | leaking, blocked, corroded |
| `wind-turbine` | generator | generator | — | source | blade-damage, gearbox-fault, overheated |
| `aeration-basin` | processor | processor | water (storage), air (storage), sludge (storage) | load | leaking, diffuser-fault, foaming |
| `steam-turbine` | generator | generator | water (passage) | source | bearing-fault, blade-damage, overheated |
| `fan` | load | load | air (passage) | load | blade-damage, seized, overheated |
| `gas-turbine` | — | prime-mover | fuel (sink), air-exhaust (passage) | prime-mover | blade-damage, bearing-fault, overheated, fuel-leak |
| `heat-recovery-steam-generator` | — | heat-exchanger | exhaust (storage), secondary (storage) | — | tube-leak, fouled, overheated |
| `surface-condenser` | — | heat-exchanger | condensing (storage), cooling (storage) | — | tube-leak, fouled, air-ingress |
| `deaerator` | — | thermal-storage | feedwater (storage) | — | leaking, corroded, vent-blocked |
| `cooling-radiator` | — | heat-rejection | coolant (passage), air (passage) | load | leaking, fan-fault, fouled |
| `fuel-pressure-regulator` | — | valve | fuel (passage) | — | stuck, leaking, blocked |
| `pwr-reactor-vessel` | — | conceptual-heat-source | primary (storage) | — | leaking, cooling-loss, overheated |
| `bwr-reactor-vessel` | — | conceptual-heat-source | reactor-water (storage) | — | leaking, cooling-loss, overheated |
| `phwr-calandria` | — | conceptual-heat-source | heat-transport (storage), moderator (storage) | — | leaking, cooling-loss, overheated |
| `gas-cooled-reactor` | — | conceptual-heat-source | primary (passage) | — | leaking, circulator-fault, overheated |
| `sodium-reactor-vessel` | — | conceptual-heat-source | primary (storage) | — | leaking, cooling-loss, overheated |
| `molten-salt-reactor` | — | conceptual-heat-source | primary (storage) | — | leaking, cooling-loss, overheated |
| `nuclear-steam-generator` | — | heat-exchanger | primary (storage), secondary (storage) | — | tube-leak, fouled, corroded |
| `pressurizer` | — | thermal-storage | primary (storage) | load | leaking, heater-fault, relief-stuck |
| `containment-structure` | — | enclosure | atmosphere (passage), collection (passage) | — | leaking, cracked, ventilation-fault |
| `used-fuel-pool` | — | thermal-storage | pool (storage) | — | leaking, fouled, cooling-loss |
| `control-rod-drive` | — | actuator | — | load | jammed, worn, power-loss |
| `neutron-monitor` | — | sensor | — | load | drift, broken, disconnected |
| `radiation-monitor` | — | sensor | — | load | drift, broken, disconnected |
| `reservoir` | — | storage | water (storage) | — | leaking, contaminated, embankment-damage |
| `intake-gate` | — | valve | water (passage) | load | stuck, corroded, obstructed |
| `hydro-turbine` | — | prime-mover | water (passage) | prime-mover | cavitating, bearing-fault, leaking |
| `reversible-pump-turbine` | — | reversible-prime-mover | water (passage) | store | cavitating, bearing-fault, leaking |
| `power-inverter` | — | power-converter | — | converter | semiconductor-fault, overheated, cooling-loss |
| `heliostat` | — | solar-collector | — | source | misaligned, soiled, drive-fault |
| `solar-receiver` | — | heat-source | transfer-fluid (passage) | load | leaking, fouled, overheated |
| `parabolic-trough` | — | solar-collector | transfer-fluid (passage) | source | soiled, leaking, drive-fault |
| `tidal-turbine` | — | environment-generator | — | source | blade-damage, fouled, bearing-fault |
| `wave-energy-converter` | — | environment-generator | — | source | mooring-damage, seal-leak, pto-fault |
| `alternator` | — | shaft-converter | — | converter | winding-fault, bearing-fault, overheated |
| `hv-circuit-breaker` | — | switch | — | relay | stuck, contact-wear, insulation-fault |
| `disconnect-switch` | — | switch | — | relay | stuck, corroded, contact-wear |
| `earthing-switch` | — | ground-switch | — | load | stuck, corroded, contact-wear |
| `current-transformer` | — | sensor | — | load | drift, broken, insulation-fault |
| `voltage-transformer` | — | sensor | — | load | drift, broken, insulation-fault |
| `surge-arrester` | — | surge-protection | — | load | degraded, insulation-fault, overheated |
| `capacitor-bank` | — | reactive-support | — | load | failed-cell, overheated, insulation-fault |
| `shunt-reactor` | — | reactive-support | — | load | winding-fault, overheated, insulation-fault |
| `protection-relay` | — | controller | — | load | drift, comms-loss, power-loss |
| `switchgear-panel` | — | switch | — | relay | contact-wear, insulation-fault, overheated |
| `gis-bay` | — | switch | — | relay | gas-leak, contact-wear, insulation-fault |
| `automatic-transfer-switch` | — | transfer-switch | — | relay | stuck, contact-wear, control-fault |
| `excitation-system` | — | power-controller | — | converter | field-loss, power-loss, overheated |
| `power-rectifier` | — | power-converter | — | converter | semiconductor-fault, overheated, cooling-loss |
| `fish-tank` | — | storage | water (storage), air (storage) | — | leaking, cracked, blocked |
| `biofilter` | — | processor | water (storage), air (storage), sludge (storage) | — | fouled, blocked, leaking |
| `media-grow-bed` | — | storage | water (storage) | load | blocked, leaking, fouled |
| `dwc-raft-bed` | — | storage | water (storage), air (storage) | load | blocked, leaking, air-loss |
| `nft-channel` | — | processor | water (passage) | load | blocked, leaking, fouled |
| `ebb-flow-table` | — | storage | water (storage) | load | blocked, leaking, timer-stall |
| `drip-zone` | — | processor | water (passage) | load | blocked, leaking, uneven-feed |
| `aeroponic-chamber` | — | storage | water (storage) | load | blocked, leaking, nozzle-fault |
| `grow-light` | — | load | — | converter | overheated, driver-fault, burnt |
| `greenhouse-vent` | — | valve | air (passage) | load | stuck, panel-damage, actuator-fault |
| `shade-screen` | — | valve | — | relay | stuck, torn, actuator-fault |
| `evaporative-pad` | — | processor | water (passage), air (passage) | — | dry-pad, fouled, leaking |
| `dehumidifier` | — | processor | air (storage), water (storage) | load | blocked-drain, iced-coil, compressor-fault |
| `water-quality-probe` | — | sensor | — | load | drift, fouled, disconnected |
| `humidity-sensor` | — | sensor | — | load | drift, condensation, disconnected |
| `light-sensor` | — | sensor | — | load | drift, occluded, disconnected |
| `air-diffuser` | — | processor | air (passage) | — | fouled, blocked, disconnected |

Every version 2 base type has a runnable template, but useful connected behavior depends on the declared supplies and topology. An unconnected powered device has no hidden bench supply. Finite stores, retained heat, and resource balances remain separate from display fields. Faults are fictional latched conditions; their availability effects and seeded damage rules are described in [MODEL-API.md](./MODEL-API.md).

All values and responses are normalized teaching assumptions. Family names, circuit labels, fault names, and visible engineering units do not imply physical recipes, calibrated equipment behavior, operating limits, or design suitability.
