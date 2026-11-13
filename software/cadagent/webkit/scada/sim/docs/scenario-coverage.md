# Scenario coverage

The canonical library contains **60 runnable scenarios, 142 symbol types, 911 equipment instances and 195 focused views**. The accepted 20 industry system/model pairs retain version 1 behavior. The 33 power, six agriculture and one electric batch-oven examples explicitly opt into version 2 circuits, finite stores, conversions and observations.

Every scenario contains editable `system.json` and `model.json` source. The [catalog](../scenarios/index.json) indexes every used `componentTypes` ID and a sorted, duplicate-free `componentVariants` array of `{type, variant}` objects. Facility and technology filters, the type/variant index and keyword search help humans and agents locate a relevant example. The [Explorer](../../explorer/index.html) also accepts `?scenario=power-nuclear-pwr` or `?componentType=fish-tank`.

| Group | Scenarios | Equipment | Views | Model |
| --- | ---: | ---: | ---: | --- |
| Original industry examples | 20 | 297 | 60 | Version 1 |
| Power and utilities | 33 | 515 | 115 | Version 2 |
| Agriculture and aquaculture | 6 | 96 | 18 | Version 2 |
| Electric batch heating | 1 | 3 | 2 | Version 2 |

## Shared state and editable assumptions

One canonical graph and one external adapter own each plant’s clock, equipment, commands, parameters and history. Focused views refer to the same equipment IDs; changing a view or opening an inspector cannot create a second model. Every component appears in at least one focused view, and views overlap around shared equipment. The original industry examples use process, utility and finishing views. Power and growing examples use two to four views tailored to actual circuits and functions.

Every physical quantity is an editable normalized teaching assumption. Example generator nameplates are explicitly labeled illustrative display presets, independent of fuel and enclosure. No copied source number silently becomes a parameter. The model files record assumptions per component; each system separates reference-derived structure from assumed values and authored geometry.

Version 2 material inventories belong to explicit circuits. Primary coolant, secondary steam, condenser cooling, intermediate sodium/salt and geothermal working fluids stay separate even inside one drawing. Thermal links exchange accounted heat without moving fluid. Fuel/air, shaft power, excitation, DC/AC conversion and external station supplies have distinct endpoints. Storage modes reverse declared paths; common AC buses keep charging paths separate from output breaker isolation. No unconnected inlet invents a supply.

Nuclear diagrams are conceptual heat-source and circulation examples: PWR and the selected integral-PWR SMR keep primary and steam circuits separate; BWR uses direct vessel steam; PHWR has separate heat-transport and moderator circuits; HTGR selects helium; sodium uses an intermediate loop; molten salt selects solid fuel with salt coolant. Neutron/radiation displays are fictional indices with explicit validity, not physical flux or dose predictions. Agriculture uses separate water, air, climate, light and tracer state; it predicts no crop yield or fish welfare.

## Scenario matrix

| Scenario | Facility / sector | Assets / views | Primary focus | References |
| --- | --- | ---: | --- | --- |
| [Winery](../scenarios/winery/system.json) | Food & beverage | 15 / 3 | Grape receiving belt → Grape crusher → Juice extraction separator → Must transfer pump → Fermentation vessel → Aging buffer → Cellar transfer valve → Polishing filter → Bottle filling → Bottle packing | Illustrative authored process |
| [Brewery](../scenarios/brewery/system.json) | Food & beverage | 16 / 3 | Grain receiving silo → Grain mill → Mash vessel → Lauter separation → Brew kettle → Wort heat exchanger → Fermentation vessel → Conditioning buffer → Container filling → Case packing | Illustrative authored process |
| [Fortune-cookie factory](../scenarios/fortune-cookies/system.json) | Food & beverage | 15 / 3 | Ingredient weighing hopper → Batter mixing vessel → Batter metering pump → Sheet depositing station → Baking tunnel → Warm product transfer → Cookie folding station → Cooling transfer belt → Cookie wrapping | Illustrative authored process |
| [Shampoo blending](../scenarios/shampoo/system.json) | Consumer products | 14 / 3 | Water feed store → Base feed store → Additive dosing unit → Blending vessel → Blend temperature loop → Circulation pump → Product filter → Bulk holding tank → Bottle filling → Carton packing | Illustrative authored process |
| [Carbonated beverages](../scenarios/carbonated-beverages/system.json) | Food & beverage | 19 / 3 | Water feed store → Water polishing → Water feed pump → Syrup feed store → Syrup metering → Beverage blend vessel → Beverage cooling exchanger → Carbonation contact vessel → Filling supply valve → Filler buffer → Beverage filling → Case packing | Illustrative authored process |
| [Dairy processing](../scenarios/dairy/system.json) | Food & beverage | 13 / 3 | Receiving tank → Receiving transfer pump → Intake strainer → Separation centrifuge → Thermal processing exchanger → Holding vessel → Filling buffer → Container filling → Case packing | Illustrative authored process |
| [Fruit-juice line](../scenarios/fruit-juice/system.json) | Food & beverage | 14 / 3 | Fruit receiving belt → Fruit extraction crusher → Juice clarification → Illustrative concentration stage → Juice blending vessel → Product thermal exchanger → Product holding vessel → Final polishing → Juice filling → Case packing | Illustrative authored process |
| [Oral-liquid manufacturing](../scenarios/pharma-oral-liquid/system.json) | Pharmaceuticals | 15 / 3 | Utility-water feed → Water preparation skid → Demonstration base feed → Metered addition → Blend vessel → Process holding vessel → Transfer check valve → Bulk transfer pump → Dedicated transfer section → Bulk holding tank → Liquid filling → Carton packing | Illustrative authored process |
| [Tablet manufacturing](../scenarios/tablets/system.json) | Pharmaceuticals | 15 / 3 | Powder receiving silo → Batch weighing hopper → Powder metering screw → Particle preparation mill → Granulation stage → Granule drying stage → Granule screening → Dry blending drum → Tablet compression station → Inspection transfer → Tablet packaging | Illustrative authored process |
| [Biopharma fermentation](../scenarios/biopharma-fermentation/system.json) | Biopharma | 14 / 3 | Demonstration media feed → Media preparation vessel → Media conditioning exchanger → Fermentation vessel → Harvest transfer pump → Harvest holding tank → Harvest separation → Membrane processing → Product bulk hold | Illustrative authored process |
| [Sterile-filling concept](../scenarios/sterile-filling/system.json) | Pharmaceuticals | 14 / 3 | Prepared solution feed → Illustrative final membrane stage → Filling supply buffer → Controlled transfer valve → Filling supply pump → Filling station → Container closing station → Inspection transfer → Secondary packaging | Illustrative authored process |
| [Paint blending](../scenarios/paint-blending/system.json) | Chemicals | 14 / 3 | Pigment feed hopper → Binder feed store → Dispersion vessel → Dispersion mill → Product filter → Tint blending vessel → Finished-product hold → Can filling → Pack-out | Illustrative authored process |
| [Industrial detergent](../scenarios/industrial-detergent/system.json) | Chemicals | 18 / 3 | Water feed store → Base feed store → Metered addition → Feed manifold → Blending vessel → Blend temperature loop → Bulk transfer valve → Product filter → Bulk product hold → Container filling → Pack-out | Illustrative authored process |
| [Polymer extrusion](../scenarios/polymer-extrusion/system.json) | Materials | 15 / 3 | Material receiving silo → Material drying stage → Blend weighing hopper → Metering feeder → Feed blending drum → Extrusion line → Product forming station → Cooling transfer section → Length-forming station → Product packaging | Illustrative authored process |
| [Concrete batching](../scenarios/concrete-batching/system.json) | Construction materials | 15 / 3 | Aggregate storage → Aggregate screening → Aggregate weighing → Binder storage → Binder metering screw → Water feed store → Water metering pump → Batch mixing drum → Mixed-product transfer → Discharge buffer | Illustrative authored process |
| [Cement processing](../scenarios/cement/system.json) | Construction materials | 14 / 3 | Raw-material receiving → Raw-material crusher → Raw preparation mill → Illustrative preheating stage → Rotary kiln → Cooling transfer section → Finish grinding → Finished-product silo → Dispatch packing | Illustrative authored process |
| [Mineral crushing & screening](../scenarios/mineral-crushing/system.json) | Mineral processing | 14 / 3 | Ore receiving hopper → Ore feed screw → Primary crusher → Primary screen → Secondary crusher → Product transfer belt → Final classification screen → Product surge bin → Product outfeed | Illustrative authored process |
| [Mineral flotation](../scenarios/mineral-flotation/system.json) | Mineral processing | 13 / 3 | Ore receiving hopper → Slurry preparation mill → Slurry conditioning vessel → Rougher separation cell → Cleaner separation cell → Concentrate thickener → Concentrate filtration → Concentrate holding buffer → Concentrate transfer | Illustrative authored process |
| [Metal-finishing line](../scenarios/metal-finishing/system.json) | Surface treatment | 14 / 3 | Work receiving conveyor → Cleaning bath → First rinse bath → Illustrative treatment bath → Second rinse bath → Final rinse bath → Drying station → Finished-work outfeed | Illustrative authored process |
| [Pulp & paper](../scenarios/pulp-paper/system.json) | Fiber processing | 16 / 3 | Pulp receiving store → Stock blending chest → Stock screening → Stock refining stage → Headbox supply chest → Sheet-forming machine → Sheet pressing section → Sheet drying section → Reel forming station → Reel packaging | Illustrative authored process |
| [Simple-cycle gas turbine](../scenarios/power-gas-simple-cycle/system.json) | Thermal power station | 13 / 3 | Explicit natural-gas supply → Fuel-gas pressure regulator → Explicit ambient-air supply → Combustion turbine / shaft output → Explicit exhaust boundary | P01 |
| [Combined-cycle gas plant](../scenarios/power-gas-combined-cycle/system.json) | Thermal power station | 21 / 4 | Explicit natural-gas supply → Fuel-gas pressure regulator → Explicit combustion-air source → Gas turbine / shaft output → Shaft-driven alternator → Independent excitation field | P01 |
| [Coal steam-cycle plant](../scenarios/power-coal-steam/system.json) | Thermal power station | 18 / 4 | Coal external solid-fuel supply → Solid-fuel feed conveyor → Coal preparation → Solid-fuel boiler with separate feedwater → Conceptual exhaust cleanup → Explicit exhaust boundary → Explicit combustion-air boundary | P03, P04 |
| [Biomass CHP](../scenarios/power-biomass-chp/system.json) | Thermal power station | 21 / 4 | Biomass external solid-fuel supply → Solid-fuel feed conveyor → Biomass preparation → Solid-fuel boiler with separate feedwater → Conceptual exhaust cleanup → Explicit exhaust boundary → Explicit combustion-air boundary | P03, P04 |
| [Impoundment hydropower](../scenarios/power-hydro-impoundment/system.json) | Hydroelectric station | 14 / 3 | Explicit river inflow boundary → Upper reservoir → Intake gate → Water penstock → Water turbine / shaft output → Explicit downstream river boundary | P05, P06, P07 |
| [Diversion hydropower](../scenarios/power-hydro-diversion/system.json) | Hydroelectric station | 13 / 3 | Explicit river-source boundary → Intake gate → Water penstock → Water turbine / shaft output → Explicit downstream river boundary | P05, P06 |
| [Reversible pumped storage](../scenarios/power-pumped-storage/system.json) | Hydroelectric station | 12 / 3 | Finite upper reservoir → Reversible pump-turbine → Finite lower reservoir | P05, P19 |
| [Pressurized-water nuclear concept](../scenarios/power-nuclear-pwr/system.json) | Nuclear power station | 22 / 4 | PWR core · primary water → Primary-water circulator → Isolated nuclear steam generator → Primary-circuit pressurizer → Containment context · no safety claim | P11, P12, P15 |
| [Pressure-channel heavy-water concept](../scenarios/power-nuclear-phwr/system.json) | Nuclear power station | 21 / 4 | PHWR calandria · heavy water → Primary heavy-water circulator → Isolated nuclear steam generator → Primary-circuit pressurizer → Containment context · no safety claim | P12, P15 |
| [Helium-cooled reactor concept](../scenarios/power-nuclear-htgr/system.json) | Nuclear power station | 18 / 4 | Solid-fuel helium-cooled core → Primary helium circulator → Isolated nuclear steam generator → Containment context · no safety claim | P12, P14 |
| [Pool-type sodium fast-reactor concept](../scenarios/power-nuclear-sodium-fast/system.json) | Nuclear power station | 20 / 4 | Pool-type sodium fast-reactor concept → Primary sodium circulator → Isolated nuclear steam generator → Primary / intermediate sodium exchanger → Intermediate sodium circulator → Containment context · no safety claim | P12, P14 |
| [Solid-fuel salt-cooled nuclear concept](../scenarios/power-nuclear-molten-salt/system.json) | Nuclear power station | 20 / 4 | Solid-fuel salt-cooled concept → Primary salt circulator → Isolated nuclear steam generator → Primary / intermediate salt exchanger → Intermediate salt circulator → Containment context · no safety claim | P12, P14 |
| [Boiling-water nuclear concept](../scenarios/power-nuclear-bwr/system.json) | Nuclear power station | 17 / 4 | Direct-steam BWR vessel → Vessel recirculation pump → Rod position · fictional heat command → Containment context · no safety claim | P11, P12 |
| [Two-module integral-PWR concept](../scenarios/power-nuclear-lw-smr/system.json) | Nuclear power station | 31 / 4 | Integral-PWR module A → Module A primary circulation → Module A isolated steam generator → Module A pressurizer → Module A containment context → Module A fictional containment index → Module A rod command → Module A steam turbine-generator → Module A feedwater pump | P11, P13 |
| [Natural-gas engine CHP](../scenarios/power-ng-engine-chp/system.json) | Thermal power station | 19 / 4 | Explicit natural-gas supply → Fuel-gas pressure regulator → Industrial natural-gas CHP engine → Explicit engine-exhaust boundary → Explicit combustion-air boundary | P02, P03, P04 |
| [Diesel standby supply](../scenarios/power-diesel-standby/system.json) | Standby power installation | 11 / 3 | Explicit utility source boundary → Standby diesel enclosure → Utility / standby changeover → Isolated demonstration demand → Explicit combustion-air boundary | P02, P20 |
| [Portable gasoline generator](../scenarios/power-gasoline-portable/system.json) | Portable power set | 10 / 2 | Portable gasoline frame → Portable load breaker → Isolated demonstration demand → Explicit station-service boundary → Shared plant controller → Explicit combustion-air boundary → Spare DC rectifier · intentionally disabled | P02 |
| [Distribution substation](../scenarios/power-substation-distribution/system.json) | Substation | 18 / 4 | Explicit upstream AC boundary → Incoming disconnector → Incoming circuit breaker → Distribution step-down transformer → Surge-arrester branch | P08, P09, P10 |
| [Generator step-up substation](../scenarios/power-substation-gsu/system.json) | Substation | 15 / 3 | Explicit mechanical-drive boundary → Shaft-driven alternator → Independent excitation field → Export transformer | P08, P09, P10 |
| [Gas-insulated substation interface](../scenarios/power-substation-gis/system.json) | Substation | 12 / 3 | Explicit incoming AC boundary → Cable isolation → Enclosed gas-insulated bay → Interface transformer | P08, P09, P10 |
| [Back-to-back HVDC interface](../scenarios/power-hvdc-interface/system.json) | HVDC converter station | 10 / 3 | Explicit sending AC boundary → AC to DC rectifier → Explicit DC link isolator | P09, P10 |
| [Photovoltaic field](../scenarios/power-solar-pv/system.json) | Solar power station | 10 / 3 | PV string group A → PV string group B → DC array isolator → DC to AC inverter | P18 |
| [Wind collection network](../scenarios/power-wind-collection/system.json) | Wind farm | 10 / 3 | Onshore turbine concept → Offshore turbine concept → Electrical collection bus | P21 |
| [Tidal-current array](../scenarios/power-tidal-current/system.json) | Marine energy array | 10 / 3 | Tidal-current rotor A → Tidal-current rotor B → Electrical collection bus | P22 |
| [Wave point-absorber array](../scenarios/power-wave-point-absorber/system.json) | Marine energy array | 10 / 3 | Wave buoy / takeoff A → Wave buoy / takeoff B → Electrical collection bus | P22 |
| [Solar power tower](../scenarios/power-csp-tower/system.json) | Solar power station | 18 / 4 | Heliostat field group A → Heliostat field group B → Central optical receiver → Finite hot heat-transfer inventory → Explicit station-service boundary → Explicit station AC/DC service | P17, P19 |
| [Parabolic-trough solar plant](../scenarios/power-csp-trough/system.json) | Solar power station | 16 / 4 | Linear parabolic-trough field → Collector-loop circulation → Finite cold heat-transfer inventory → Finite hot heat-transfer inventory → Explicit station-service boundary → Explicit station AC/DC service | P17 |
| [Stationary fuel-cell system](../scenarios/power-fuel-cell/system.json) | Thermal power station | 15 / 3 | Explicit natural-gas supply → Fuel-gas pressure regulator → Explicit oxidant-air boundary → Fuel-cell stack · separate inputs and outputs → Explicit product-water discharge | P23 |
| [Flash geothermal](../scenarios/power-geothermal-flash/system.json) | Geothermal power station | 14 / 4 | Explicit hot-water production boundary → Water / steam flash separator → Explicit reinjection acceptance boundary | P16 |
| [Binary geothermal](../scenarios/power-geothermal-binary/system.json) | Geothermal power station | 14 / 4 | Explicit geothermal production boundary → Isolated geothermal / organic-fluid exchanger → Explicit geothermal reinjection boundary | P16 |
| [Dry-steam geothermal](../scenarios/power-geothermal-dry-steam/system.json) | Geothermal power station | 13 / 3 | Explicit dry-steam well boundary → Direct geothermal-steam turbine → Direct-steam condenser | P16 |
| [Battery energy-storage system](../scenarios/power-battery-storage/system.json) | Energy storage station | 12 / 3 | Finite stored DC energy → Bidirectional battery converter → Common AC bus · import / storage / export → Bidirectional AC collection bay | P18, P19 |
| [Hybrid islandable microgrid](../scenarios/power-hybrid-microgrid/system.json) | Microgrid | 17 / 4 | Local PV array → PV DC / AC inverter → Explicit natural-gas supply → Fuel-gas pressure regulator → Local natural-gas genset → Common AC bus · import / storage / export → Local AC connection bay → Explicit combustion-air boundary → Explicit combustion-exhaust boundary | P18, P20 |
| [Media-bed aquaponics](../scenarios/aquaponics-media-bed/system.json) | Greenhouse | 12 / 3 | Fish tank · water loop → Mechanical solids filter → Flood/drain media bed → Shared return sump → Return circulation pump | A2, A3, A4 |
| [Raft / DWC aquaponics](../scenarios/aquaponics-dwc/system.json) | Greenhouse | 17 / 3 | Fish tank → Solids capture filter → Dedicated biological media → Treatment / return sump → Shared circulation pump → Fish and raft distribution → Raft bed A → Raft bed B | A2, A4, A5 |
| [NFT hydroponics](../scenarios/hydroponics-nft/system.json) | Indoor growing room | 17 / 3 | Prepared nutrient reservoir → Solution circulation pump → Supply screen filter → Channel feed header → Channel A feed valve → Nutrient-film channel A → Channel B feed valve → Nutrient-film channel B | A1, A5, A6 |
| [Ebb-and-flow nursery](../scenarios/hydroponics-ebb-flow/system.json) | Greenhouse | 13 / 3 | Shared nursery reservoir → Nursery filling pump → Table feed manifold → Nursery table A → Table A return valve → Nursery table B → Table B return valve | A1, A3, A5, A7 |
| [Drip / substrate greenhouse](../scenarios/greenhouse-drip/system.json) | Greenhouse | 19 / 3 | Solution preparation reservoir → Drip supply pump → Emitter protection filter → Substrate row manifold → Substrate row A → Substrate row B → Collected substrate drainage → Declared recirculation pump | A1, A7, A8, A9, A10 |
| [Indoor vertical / aeroponic room](../scenarios/indoor-aeroponics/system.json) | Indoor vertical farm | 18 / 3 | Shared mist-solution reservoir → Mist distribution pump → Nozzle protection filter → Root-chamber mist manifold → Root chamber · tier A → Root chamber · tier B → Dissolved oxygen · illustrative index | A1, A5, A11, A12 |
| [Electric batch heating cell](../scenarios/electric-batch-oven/system.json) | Manufacturing / thermal processing | 3 / 2 | Explicit electrical supply, isolation and retained heat; visual-only door | I1 in system provenance |

## Symbol coverage

Every registered family has a runnable location below. Version 1 descriptors remain available for all 80 original symbol types; version 2 descriptors cover all 142. A scenario can declare an external source, sink or other documented role rather than using the family default. Variant identity is validated against the selected UI and model contracts, including fuel ports and circuit media.

| Symbol type | Default version 2 family | Runnable example / equipment |
| --- | --- | --- |
| `digester` | `processor` | [winery / `effluent`](../scenarios/winery/system.json) |
| `tank` | `storage` | [winery / `aging`](../scenarios/winery/system.json) |
| `gas-holder` | `storage` | [carbonated-beverages / `gasStore`](../scenarios/carbonated-beverages/system.json) |
| `mixing-tank` | `processor` | [brewery / `mash`](../scenarios/brewery/system.json) |
| `reactor` | `processor` | [winery / `fermenter`](../scenarios/winery/system.json) |
| `clarifier` | `processor` | [mineral-flotation / `thickener`](../scenarios/mineral-flotation/system.json) |
| `silo` | `storage` | [brewery / `grainSilo`](../scenarios/brewery/system.json) |
| `heat-exchanger` | `heater` | [brewery / `cooler`](../scenarios/brewery/system.json) |
| `filter` | `processor` | [winery / `polishing`](../scenarios/winery/system.json) |
| `gas-treatment` | `processor` | [carbonated-beverages / `gasQuality`](../scenarios/carbonated-beverages/system.json) |
| `boiler` | `heater` | [brewery / `heatService`](../scenarios/brewery/system.json) |
| `flare` | `heater` | [winery / `biogasFlare`](../scenarios/winery/system.json) |
| `pump` | `pump` | [winery / `mustTransfer`](../scenarios/winery/system.json) |
| `submersible-pump` | `pump` | [dairy / `pitPump`](../scenarios/dairy/system.json) |
| `dosing-pump` | `pump` | [fortune-cookies / `metering`](../scenarios/fortune-cookies/system.json) |
| `blower` | `pump` | [fortune-cookies / `coolingAir`](../scenarios/fortune-cookies/system.json) |
| `compressor` | `pump` | [carbonated-beverages / `gasCompressor`](../scenarios/carbonated-beverages/system.json) |
| `motor` | `load` | [fortune-cookies / `motor`](../scenarios/fortune-cookies/system.json) |
| `generator` | `generator` | [winery / `power`](../scenarios/winery/system.json) |
| `transformer` | `processor` | [shampoo / `transformer`](../scenarios/shampoo/system.json) |
| `breaker` | `valve` | [concrete-batching / `breaker`](../scenarios/concrete-batching/system.json) |
| `busbar` | `processor` | [polymer-extrusion / `distribution`](../scenarios/polymer-extrusion/system.json) |
| `battery` | `energy-storage` | [fruit-juice / `battery`](../scenarios/fruit-juice/system.json) |
| `ups` | `energy-storage` | [sterile-filling / `ups`](../scenarios/sterile-filling/system.json) |
| `solar-panel` | `generator` | [fruit-juice / `power`](../scenarios/fruit-juice/system.json) |
| `electrical-meter` | `sensor` | [pulp-paper / `meter`](../scenarios/pulp-paper/system.json) |
| `gate-valve` | `valve` | [winery / `transferValve`](../scenarios/winery/system.json) |
| `control-valve` | `valve` | [carbonated-beverages / `controlValve`](../scenarios/carbonated-beverages/system.json) |
| `check-valve` | `valve` | [pharma-oral-liquid / `checkValve`](../scenarios/pharma-oral-liquid/system.json) |
| `relief-valve` | `valve` | [paint-blending / `relief`](../scenarios/paint-blending/system.json) |
| `butterfly-valve` | `valve` | [industrial-detergent / `valve`](../scenarios/industrial-detergent/system.json) |
| `pressure-transmitter` | `sensor` | [winery / `pressure`](../scenarios/winery/system.json) |
| `flow-meter` | `sensor` | [carbonated-beverages / `flow`](../scenarios/carbonated-beverages/system.json) |
| `temperature-sensor` | `sensor` | [brewery / `temperature`](../scenarios/brewery/system.json) |
| `level-sensor` | `sensor` | [shampoo / `level`](../scenarios/shampoo/system.json) |
| `gas-analyzer` | `sensor` | [biopharma-fermentation / `offgas`](../scenarios/biopharma-fermentation/system.json) |
| `plc-rack` | `controller` | [winery / `controller`](../scenarios/winery/system.json) |
| `plc-cpu` | `controller` | [shampoo / `controller`](../scenarios/shampoo/system.json) |
| `remote-io` | `controller` | [dairy / `controller`](../scenarios/dairy/system.json) |
| `hmi` | `network` | [fortune-cookies / `controller`](../scenarios/fortune-cookies/system.json) |
| `scada-server` | `network` | [pulp-paper / `controller`](../scenarios/pulp-paper/system.json) |
| `network-switch` | `network` | [brewery / `network`](../scenarios/brewery/system.json) |
| `radio` | `network` | [concrete-batching / `radio`](../scenarios/concrete-batching/system.json) |
| `pipe` | `pipe` | [pharma-oral-liquid / `transferPipe`](../scenarios/pharma-oral-liquid/system.json) |
| `junction` | `pipe` | [industrial-detergent / `junction`](../scenarios/industrial-detergent/system.json) |
| `conveyor` | `processor` | [winery / `grapeIntake`](../scenarios/winery/system.json) |
| `crusher` | `processor` | [winery / `crusher`](../scenarios/winery/system.json) |
| `vibrating-screen` | `processor` | [tablets / `screen`](../scenarios/tablets/system.json) |
| `grinding-mill` | `processor` | [brewery / `mill`](../scenarios/brewery/system.json) |
| `rotary-kiln` | `heater` | [cement / `kiln`](../scenarios/cement/system.json) |
| `oven` | `heater` | [fortune-cookies / `oven`](../scenarios/fortune-cookies/system.json) |
| `dryer` | `heater` | [tablets / `dryer`](../scenarios/tablets/system.json) |
| `extruder` | `processor` | [polymer-extrusion / `extruder`](../scenarios/polymer-extrusion/system.json) |
| `tablet-press` | `processor` | [tablets / `press`](../scenarios/tablets/system.json) |
| `filling-line` | `processor` | [winery / `bottler`](../scenarios/winery/system.json) |
| `packaging-line` | `processor` | [winery / `packer`](../scenarios/winery/system.json) |
| `granulator` | `processor` | [tablets / `granulator`](../scenarios/tablets/system.json) |
| `forming-machine` | `processor` | [fortune-cookies / `depositor`](../scenarios/fortune-cookies/system.json) |
| `drum-mixer` | `processor` | [tablets / `blender`](../scenarios/tablets/system.json) |
| `paper-machine` | `processor` | [pulp-paper / `machine`](../scenarios/pulp-paper/system.json) |
| `weigh-hopper` | `storage` | [fortune-cookies / `flour`](../scenarios/fortune-cookies/system.json) |
| `screw-feeder` | `processor` | [tablets / `feeder`](../scenarios/tablets/system.json) |
| `centrifuge` | `processor` | [dairy / `separator`](../scenarios/dairy/system.json) |
| `flotation-cell` | `processor` | [mineral-flotation / `rougher`](../scenarios/mineral-flotation/system.json) |
| `membrane-filter` | `processor` | [biopharma-fermentation / `membranes`](../scenarios/biopharma-fermentation/system.json) |
| `reverse-osmosis` | `processor` | [pharma-oral-liquid / `purification`](../scenarios/pharma-oral-liquid/system.json) |
| `distillation-column` | `heater` | [paint-blending / `recovery`](../scenarios/paint-blending/system.json) |
| `separator` | `processor` | [winery / `extraction`](../scenarios/winery/system.json) |
| `cyclone` | `processor` | [cement / `dust`](../scenarios/cement/system.json) |
| `scrubber` | `processor` | [metal-finishing / `scrubber`](../scenarios/metal-finishing/system.json) |
| `cooling-tower` | `heater` | [polymer-extrusion / `tower`](../scenarios/polymer-extrusion/system.json) |
| `chiller` | `heater` | [carbonated-beverages / `chiller`](../scenarios/carbonated-beverages/system.json) |
| `evaporator` | `heater` | [fruit-juice / `concentrator`](../scenarios/fruit-juice/system.json) |
| `electrolyzer` | `processor` | [industrial-detergent / `electrolyzer`](../scenarios/industrial-detergent/system.json) |
| `fuel-cell` | `generator` | [industrial-detergent / `fuelCell`](../scenarios/industrial-detergent/system.json) |
| `wellhead` | `source` | [industrial-detergent / `well`](../scenarios/industrial-detergent/system.json) |
| `wind-turbine` | `generator` | [cement / `power`](../scenarios/cement/system.json) |
| `aeration-basin` | `processor` | [brewery / `effluent`](../scenarios/brewery/system.json) |
| `steam-turbine` | `generator` | [pulp-paper / `power`](../scenarios/pulp-paper/system.json) |
| `fan` | `load` | [fortune-cookies / `ovenAir`](../scenarios/fortune-cookies/system.json) |
| `gas-turbine` | `prime-mover` | [power-gas-simple-cycle / `turbine`](../scenarios/power-gas-simple-cycle/system.json) |
| `heat-recovery-steam-generator` | `heat-exchanger` | [power-gas-combined-cycle / `hrsg`](../scenarios/power-gas-combined-cycle/system.json) |
| `surface-condenser` | `heat-exchanger` | [power-gas-combined-cycle / `condenser`](../scenarios/power-gas-combined-cycle/system.json) |
| `deaerator` | `thermal-storage` | [power-gas-combined-cycle / `deaerator`](../scenarios/power-gas-combined-cycle/system.json) |
| `cooling-radiator` | `heat-rejection` | [power-ng-engine-chp / `radiator`](../scenarios/power-ng-engine-chp/system.json) |
| `fuel-pressure-regulator` | `valve` | [power-gas-simple-cycle / `regulator`](../scenarios/power-gas-simple-cycle/system.json) |
| `pwr-reactor-vessel` | `conceptual-heat-source` | [power-nuclear-pwr / `core`](../scenarios/power-nuclear-pwr/system.json) |
| `bwr-reactor-vessel` | `conceptual-heat-source` | [power-nuclear-bwr / `core`](../scenarios/power-nuclear-bwr/system.json) |
| `phwr-calandria` | `conceptual-heat-source` | [power-nuclear-phwr / `core`](../scenarios/power-nuclear-phwr/system.json) |
| `gas-cooled-reactor` | `conceptual-heat-source` | [power-nuclear-htgr / `core`](../scenarios/power-nuclear-htgr/system.json) |
| `sodium-reactor-vessel` | `conceptual-heat-source` | [power-nuclear-sodium-fast / `core`](../scenarios/power-nuclear-sodium-fast/system.json) |
| `molten-salt-reactor` | `conceptual-heat-source` | [power-nuclear-molten-salt / `core`](../scenarios/power-nuclear-molten-salt/system.json) |
| `nuclear-steam-generator` | `heat-exchanger` | [power-nuclear-pwr / `steamGenerator`](../scenarios/power-nuclear-pwr/system.json) |
| `pressurizer` | `thermal-storage` | [power-nuclear-pwr / `pressurizer`](../scenarios/power-nuclear-pwr/system.json) |
| `containment-structure` | `enclosure` | [power-nuclear-pwr / `containment`](../scenarios/power-nuclear-pwr/system.json) |
| `used-fuel-pool` | `thermal-storage` | [power-nuclear-pwr / `fuelPool`](../scenarios/power-nuclear-pwr/system.json) |
| `control-rod-drive` | `actuator` | [power-nuclear-pwr / `rods`](../scenarios/power-nuclear-pwr/system.json) |
| `neutron-monitor` | `sensor` | [power-nuclear-pwr / `neutron`](../scenarios/power-nuclear-pwr/system.json) |
| `radiation-monitor` | `sensor` | [power-nuclear-pwr / `radiation`](../scenarios/power-nuclear-pwr/system.json) |
| `reservoir` | `storage` | [power-hydro-impoundment / `upstream`](../scenarios/power-hydro-impoundment/system.json) |
| `intake-gate` | `valve` | [power-hydro-impoundment / `gate`](../scenarios/power-hydro-impoundment/system.json) |
| `hydro-turbine` | `prime-mover` | [power-hydro-impoundment / `runner`](../scenarios/power-hydro-impoundment/system.json) |
| `reversible-pump-turbine` | `reversible-prime-mover` | [power-pumped-storage / `unit`](../scenarios/power-pumped-storage/system.json) |
| `power-inverter` | `power-converter` | [power-hvdc-interface / `inverter`](../scenarios/power-hvdc-interface/system.json) |
| `heliostat` | `solar-collector` | [power-csp-tower / `mirrorA`](../scenarios/power-csp-tower/system.json) |
| `solar-receiver` | `heat-source` | [power-csp-tower / `collector`](../scenarios/power-csp-tower/system.json) |
| `parabolic-trough` | `solar-collector` | [power-csp-trough / `collector`](../scenarios/power-csp-trough/system.json) |
| `tidal-turbine` | `environment-generator` | [power-tidal-current / `deviceA`](../scenarios/power-tidal-current/system.json) |
| `wave-energy-converter` | `environment-generator` | [power-wave-point-absorber / `deviceA`](../scenarios/power-wave-point-absorber/system.json) |
| `alternator` | `shaft-converter` | [power-gas-simple-cycle / `alternator`](../scenarios/power-gas-simple-cycle/system.json) |
| `hv-circuit-breaker` | `switch` | [power-gas-simple-cycle / `exportBreaker`](../scenarios/power-gas-simple-cycle/system.json) |
| `disconnect-switch` | `switch` | [power-substation-distribution / `isolator`](../scenarios/power-substation-distribution/system.json) |
| `earthing-switch` | `ground-switch` | [power-substation-distribution / `ground`](../scenarios/power-substation-distribution/system.json) |
| `current-transformer` | `sensor` | [power-substation-distribution / `ct`](../scenarios/power-substation-distribution/system.json) |
| `voltage-transformer` | `sensor` | [power-substation-distribution / `vt`](../scenarios/power-substation-distribution/system.json) |
| `surge-arrester` | `surge-protection` | [power-substation-distribution / `arrester`](../scenarios/power-substation-distribution/system.json) |
| `capacitor-bank` | `reactive-support` | [power-substation-distribution / `capacitors`](../scenarios/power-substation-distribution/system.json) |
| `shunt-reactor` | `reactive-support` | [power-substation-gsu / `reactor`](../scenarios/power-substation-gsu/system.json) |
| `protection-relay` | `controller` | [power-substation-distribution / `relay`](../scenarios/power-substation-distribution/system.json) |
| `switchgear-panel` | `switch` | [power-substation-distribution / `feederA`](../scenarios/power-substation-distribution/system.json) |
| `gis-bay` | `switch` | [power-substation-gis / `gis`](../scenarios/power-substation-gis/system.json) |
| `automatic-transfer-switch` | `transfer-switch` | [power-diesel-standby / `transfer`](../scenarios/power-diesel-standby/system.json) |
| `excitation-system` | `power-controller` | [power-gas-simple-cycle / `alternatorField`](../scenarios/power-gas-simple-cycle/system.json) |
| `power-rectifier` | `power-converter` | [power-gas-simple-cycle / `dcService`](../scenarios/power-gas-simple-cycle/system.json) |
| `fish-tank` | `storage` | [aquaponics-media-bed / `fish`](../scenarios/aquaponics-media-bed/system.json) |
| `biofilter` | `processor` | [aquaponics-dwc / `biofilter`](../scenarios/aquaponics-dwc/system.json) |
| `media-grow-bed` | `storage` | [aquaponics-media-bed / `bed`](../scenarios/aquaponics-media-bed/system.json) |
| `dwc-raft-bed` | `storage` | [aquaponics-dwc / `raftA`](../scenarios/aquaponics-dwc/system.json) |
| `nft-channel` | `processor` | [hydroponics-nft / `channelA`](../scenarios/hydroponics-nft/system.json) |
| `ebb-flow-table` | `storage` | [hydroponics-ebb-flow / `tableA`](../scenarios/hydroponics-ebb-flow/system.json) |
| `drip-zone` | `processor` | [greenhouse-drip / `rowA`](../scenarios/greenhouse-drip/system.json) |
| `aeroponic-chamber` | `storage` | [indoor-aeroponics / `chamberA`](../scenarios/indoor-aeroponics/system.json) |
| `grow-light` | `load` | [aquaponics-media-bed / `bedLight`](../scenarios/aquaponics-media-bed/system.json) |
| `greenhouse-vent` | `valve` | [greenhouse-drip / `vent`](../scenarios/greenhouse-drip/system.json) |
| `shade-screen` | `valve` | [greenhouse-drip / `shade`](../scenarios/greenhouse-drip/system.json) |
| `evaporative-pad` | `processor` | [greenhouse-drip / `pad`](../scenarios/greenhouse-drip/system.json) |
| `dehumidifier` | `processor` | [indoor-aeroponics / `dehumidifier`](../scenarios/indoor-aeroponics/system.json) |
| `water-quality-probe` | `sensor` | [aquaponics-media-bed / `oxygenProbe`](../scenarios/aquaponics-media-bed/system.json) |
| `humidity-sensor` | `sensor` | [hydroponics-ebb-flow / `humidityProbe`](../scenarios/hydroponics-ebb-flow/system.json) |
| `light-sensor` | `sensor` | [aquaponics-media-bed / `lightProbe`](../scenarios/aquaponics-media-bed/system.json) |
| `air-diffuser` | `processor` | [aquaponics-media-bed / `diffuser`](../scenarios/aquaponics-media-bed/system.json) |
| `rack-oven` | `heatSource` | [electric-batch-oven / `oven`](../scenarios/electric-batch-oven/system.json) |

## Experiments and verification

Catalog experiments dispatch the same public adapter commands as the operator controls. Stop a source, isolate a feeder, inject or repair a declared fault, edit a parameter, reverse finite storage, reduce fictional core heat demand, or change a growing/climate condition. Reset restores initial dynamics while retaining edited parameters; reload restores source defaults. Experiment descriptions state both the expected change and the limits of the teaching model.

Automated source checks validate every system/model pair, port identity, variant, circuit membership, view placement, orthogonal route and catalog record. Nominal tests resolve every visual binding at 0, 10, 60 and 300 toy minutes, require normal status without injected damage, and check declared load supply. Version 2 tests reconcile mass/energy ledgers and deterministic save/import continuation. Regression experiments check actual signed storage flows and changing finite inventories, downstream electrical delivery, retained core heat, isolated cooling response and non-consuming monitor failure. Browser acceptance separately checks real controls, view continuity, responsive layouts and page errors.

These are engineering-inspired teaching systems, not recipes, plant designs, equipment curves, protection settings, licensed operating procedures or calibrated digital twins. The headless adapter boundary is the replacement point for a validated external model.

## References and previews

Each power/agriculture system carries full source citations, reviewed sections and the supported structural claim. The [power reference register](./power-sector-references.md) and [agriculture reference register](./agriculture-references.md) retain access limits and distinguish read material from attempted sources. Unread sources are not treated as evidence. The [scenario gallery](./scenario-gallery.md) links actual viewer captures and editable definitions; thumbnail freshness is checked against source hashes.
