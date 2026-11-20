# Placeholder model API and equations

## Public API

```js
import {
  PlaceholderSystemModel, createPlaceholderAdapter,
  MODEL_DESCRIPTORS, MODEL_FAMILIES, getModelDescriptor, createModelDefinition,
  validatePlaceholderModelDefinition,
  PLACEHOLDER_MODEL_FORMAT, PLACEHOLDER_MODEL_VERSION,
  ComponentModel, COMPONENT_MODEL_CLASSES,
  CircuitSystemModel, CIRCUIT_MODEL_VERSION,
  V2_MODEL_DESCRIPTORS, V2_VARIANT_DESCRIPTORS, V2_MODEL_FAMILIES,
  createV2ModelDefinition, createV2Component, getV2ModelDescriptor,
  validateV2ModelDefinition,
} from '@valpatel/scada-sim';
```

Individual version 1 family classes are also exported: `SourceModel`, `StorageModel`, `PumpModel`, `ValveModel`, `PipeModel`, `ProcessorModel`, `HeaterModel`, `GeneratorModel`, `PowerLoadModel`, `EnergyStorageModel`, `SensorModel`, `ControllerModel`, `NetworkModel` and `SinkModel`. They are replaceable implementation building blocks. The session boundary is `PlaceholderSystemModel`, whose public snapshots are deeply frozen. It dispatches version 2 definitions to `CircuitSystemModel`; existing version 1 definitions retain their original solver and defaults.

The `/models`, `/engine`, `/adapter` and `/validation` package subpaths expose the corresponding modules. `/schema`, `/snapshot-schema`, `/model-registry.json` and `/scenarios` expose the configuration schema, snapshot schema, full model metadata and scenario manifest as JSON resources. The snapshot schema references `urn:valpatel:scada-placeholder-model:1`; an offline JSON Schema validator should register both shipped schemas.

Version 2 has explicit `/models-v2`, `/engine-v2`, `/validation-v2`, `/schema-v2`, `/snapshot-schema-v2` and `/model-registry-v2.json` subpaths. Register both v2 schemas for offline validation; the snapshot schema references `urn:valpatel:scada-placeholder-model:2`. The original schema aliases, `MODEL_DESCRIPTORS`, `MODEL_FAMILIES`, and `PLACEHOLDER_MODEL_VERSION = 1` remain unchanged. `CIRCUIT_MODEL_VERSION = 2` identifies the new format.

`new PlaceholderSystemModel(systemDefinition, modelDefinition, {clock, equationProviders} = {})` validates both data sets before creating state. A clock adapter supplies `setInterval(callback, milliseconds)` and `clearInterval(id)`; it is optional and is used only by an explicit `start()` call. `equationProviders` registers reviewed synchronous JavaScript laws selected by data-only model bindings; it does not execute source from JSON.

| Method | Behavior |
| --- | --- |
| `getSnapshot()` | Returns the current deeply frozen presentation snapshot. |
| `subscribe(listener)` | Calls `listener(snapshot, event)` after changes; returns an idempotent unsubscribe function. It does not immediately emit or create a timer. |
| `dispatch(command)` | Validates and applies a plain command, recomputes derived state and records an operator event. |
| `step(minutes = 1)` | Advances a positive duration up to 60 minutes, using substeps no greater than one minute. It advances even while paused and does not change the run flag. |
| `reset()` | Restores configured initial state, elapsed time, seed and history using the **current edited parameters**; retains the run/pause choice. |
| `exportModelDefinition()` | Returns a detached editable copy including current parameter edits. |
| `setEquationBindings(equations)` | Atomically selects registered laws/parameters, initializes selected provider state and retains core inventories, heat, controls and time. `null`/`undefined` removes bindings. |
| `exportSnapshot()` | Returns a detached snapshot of the same model version, containing configuration, dynamic state, random state and event history. |
| `importSnapshot(payload)` | Validates everything before committing. Preserves saved running state, starts no clock and never replays elapsed time. |
| `start({intervalMs = 1000, minutesPerTick = 1} = {})` | Starts at most one optional clock; advances only while running. Allowed interval: 50–60,000 ms. |
| `stop()` | Removes the optional clock without changing model state. |
| `destroy()` | Stops that clock and removes model subscribers. Does not perform IO. |

`clockStarted` reports whether the optional model-owned clock exists. A host that supplies its own timer should call `step()` only when `snapshot.running` is true and should define its own hidden-tab policy. Viewer destruction never calls model destruction.

## Registered equation and component-model providers

Both versions support per-component, per-type and engine-family equation
selection through optional `modelDefinition.equations`. Precedence is component
→ type → family → built-in; a `null` selector explicitly chooses built-in behavior.
Register trusted provider objects through constructor `equationProviders`, then
select `{id, version, parameters}` data. The public entry exports
`EQUATION_UNITS`, `EQUATION_CONTRACT_VERSION`, `EQUATION_PHASE_CONTRACTS`,
`EquationRuntime`, `createEquationRuntime`, binding helpers and the bounded schema
helpers. Most hosts use the session method rather than the internal runtime.
The `/equations` package subpath exposes that core contract; `/equation-examples`
exposes the provided physical calculations and registered example laws.

The [adaptation guide](./REAL_MODEL_ADAPTATION.md) is the primary contract for
provider declarations, physical units, phase context, owned state and acceptance.
Providers override actual allocation/state equations. Pure `evaluate` can run
many times; optional `advance` updates provider-owned JSON once per accepted
substep. Engine transactions roll back state, seed, events and visible snapshot
when a provider throws or returns invalid data. Trusted callback purity and lack
of external side effects remain the provider author's responsibility.

The exported phase table distinguishes effective requests, kernel gates and
engine unit bases. V1 flow changes inventory by rate × minutes/10; v2 transfer
changes amount by rate × minutes. V1 pressure returns a response target; v2
returns the next pressure index. Physical providers explicitly bridge SI values
into those bases; built-in bounds and conservation do not establish a custom
law's engineering accuracy.

Saved sessions add `equationState` only for selected providers. Each component
records ID/version/state version, unit contract, resolved parameters, canonical
parameter/state schema signature and owned state. Import restores the saved
selection if its registered implementations match, without initialization or
time replay. Mismatches reject before commit. This is a declared compatibility
identity, not a cryptographic hash of the JavaScript implementation. The original
no-binding snapshot shape and default equations remain unchanged.

Use [physical equation examples](../examples/equation-models/README.md) and the
[model-switching bench](../examples/model-switching/README.md) for complete
consumers. A whole external solver can still use the separate viewer adapter
without adopting this kernel or snapshot format.

## Commands

Commands are data. The engine never evaluates expressions or loads code from JSON.

```js
model.dispatch({action:'setLoad', arguments:{equipment:'deliveryPump', value:65}});
model.dispatch({action:'setFault', arguments:{equipment:'deliveryPump', value:'cavitating'}});
model.dispatch({action:'repair', arguments:{equipment:'deliveryPump'}});
```

| Action | Arguments |
| --- | --- |
| `setEnabled` | `equipment`, boolean `value` |
| `setLoad` | `equipment`, numeric `value` from 0 to 100; operating or valve-opening setpoint |
| `setOpen` | `equipment`, boolean `value`; an open breaker disconnects, while an open process valve conducts |
| `setLevel` | `equipment`, `value` from 0 to 100; direct illustrative stock edit |
| `setDamage` | `equipment`, `value` from 0 to 100; 100 latches a failure |
| `setFault` | `equipment`, a descriptor failure-mode ID or `true`; `false` / `"none"` repairs |
| `repair` | Optional `equipment`; omitted or `"all"` repairs every component, retaining its switch settings |
| `setParameter` | `equipment`, descriptor parameter `key`, bounded numeric `value` |
| `setRunning` | Boolean `value` |
| `step` | Optional `minutes` or `value`, default 1; this command pauses before stepping |
| `reset` | No arguments |
| `import` | Snapshot under `payload` or `value` |

The standard UI command fields `id`, `label` and `component` are accepted; `component` can supply the equipment ID when `arguments.equipment` is absent. All other command/argument keys are rejected.

## Version 2 circuits and domains

Use `createModelDefinition(system, {version:2})` or `createV2ModelDefinition(system)` to create v2 templates. `getModelDescriptor(type, {version:2, variant})` and `getV2ModelDescriptor(type, {variant})` return the same versioned descriptor. `V2_MODEL_DESCRIPTORS` covers all 142 types; `V2_VARIANT_DESCRIPTORS` separately covers every explicit configuration variant, including bidirectional common buses. A variant is selected in the system/model definition; changing its ports requires a new session.

```js
const definition = createV2ModelDefinition(systemDefinition, {
  seed:12345,
  environment:{ambient:20, light:60},
  zones:{room:{
    initial:{temperature:20, humidity:50, light:60, oxygen:70},
    parameters:{response:0.1},
  }},
});
const checked = validatePlaceholderModelDefinition(systemDefinition, definition);
if (!checked.ok) throw new Error(JSON.stringify(checked.errors));
const model = new PlaceholderSystemModel(systemDefinition, checked.definition);
```

Every v2 component declares `model`, `circuits`, parameters and initial controls. Component `parameters` and `initial` may omit fields to use registered defaults. Each resource circuit owns a nonempty set of registered ports, a `medium`, a compatible `fluid`, a role (`passage`, `storage`, `source`, `sink`), complete circuit parameters and initial inventory/temperature/pressure. Omitted tracer indices receive defaults. Registered circuit groups cannot be split or merged: exchanger hot/cold streams and nuclear primary/secondary circuits retain their declared separation. Other groups follow the selected type/variant contract; for example, boiler and gas-turbine templates intentionally place air and exhaust ports in one `air-exhaust` teaching circuit.

`source` and `sink` are declared external boundaries. Other circuit inventories are finite. A filled closed loop requires an available circulation driver, and powered equipment requires its accepted energy input. Missing supply never creates material or power. `ground` is a reference channel; CT/VT observation ports never create resource inventory.

| Circuit parameter | Bounds | Meaning |
| --- | --- | --- |
| `capacity` | 0–100 | Summed circuit transfer ceiling in toy units per minute |
| `stockScale` | 0.01–1,000 | Toy amount per inventory index point |
| `thermalCapacity` | 0.01–100 | Toy heat capacity per unit of resource |
| `loss` | 0–1 | Declared fraction removed during outgoing transfer |
| `pressureGain` | 0–100 | Illustrative pressure response index |

`energy` declares a role (`boundary`, `source`, `load`, `relay`, `converter`, `store`, `prime-mover`), input/output port IDs, capacity, demand and efficiency. `capacity` and `demand` range from 0 to 100; efficiency is 0.001–1. Sources require an explicit boundary, environmental, fuel-resource or stored-heat supply. Stores additionally declare a finite capacity (0.01–1,000) and initial charge index (0–100). Electrical AC/DC, mechanical and optical domains connect only to matching domains; an explicit converter crosses them. Modes map named commands to `forward`, `reverse`, `charge`, `discharge` or `idle`. Mode-controlled connections select `1`, `-1` or `0` for forward, reversed or disabled transport. Intentional idle/stopped modes report normal inactive equipment; unexpected lost supply reports offline.

`thermalStore`, `heatSource` and `thermalLinks` exchange retained heat independently of material. A thermal link names exact `{component, circuit}` endpoints; `body` refers to a declared thermal store. Turning off a heat source stops new heat but retains stored heat. Electrical-to-heat receivers debit accepted energy; fuel/thermal generators debit their declared supply and record efficiency losses. Phase changes and physical fluid properties are not calculated.

V2 tracer indices are `oxygen`, `nutrient`, `solids`, `ph` and `ec`, each 0–100. Transfer carries tracer amounts with the donor resource; agricultural uptake, oxygenation and solids conversion are explicit teaching rules. The pH and EC fields are illustrative indices, not chemically valid mixtures or operating targets. Shared zones hold temperature, humidity, light and oxygen indices. Aquaculture, grow beds, timed flood/drain cycles, misting, ventilation, evaporation and condensation use the descriptor's editable coefficients. Observations select a component/circuit or zone and a quantity; unavailable telemetry retains its last value with `valid:false`. Losing an observation does not disable healthy controller IO or invent a protective interlock. Failed controllers and communication infrastructure still gate explicitly connected control inputs.

Drift and fouling retain available observations with warning status and the supplied
damage identity. This placeholder does not add a synthetic measurement bias or
claim calibrated accuracy. Broken, disconnected, unpowered or unavailable
communication paths still suppress valid telemetry; repair resumes observation of
the current source rather than displaying an invented zero.

## Additional version 2 commands

Each command is validated atomically. Rejected parameter edits, imports, and steps preserve both canonical state and the prior immutable snapshot. A live capacity edit that would put current stock or heat above the new bound is rejected. Existing switch, load, fault, repair, run, step, reset and import commands also work in v2.

| Action | Arguments |
| --- | --- |
| `setLevel` | `equipment`, optional `circuit`, index `value`; material and carried heat edits enter the boundary ledger |
| `setCircuitParameter` | `equipment`, `circuit`, parameter `key`, bounded `value` |
| `setEnergyParameter` | `equipment`, `key` (`capacity`, `demand`, `efficiency`), bounded `value` |
| `setTracer` | `equipment`, populated `circuit`, tracer `key`, index `value`; empty circuits reject composition edits |
| `setEnvironment` | Existing environmental boundary `key`, index `value` |
| `setZoneValue` | Existing `zone`, zone-field `key`, index `value` |
| `setMode` | `equipment`, declared mode name under `value` |
| `setMeasurement` | Water-quality probe `equipment`, `value` (`ph`, `ec`, `do`); updates its observed quantity together |
| `setRodPosition` | `equipment`, illustrative index `value` from 0 to 100 |

Descriptor `circuitParameters`, `energyParameters`, `tracers` and `zoneFields` provide editor labels, units and bounds. The explorer's extended inspector uses only these public descriptors and commands. Both `createPlaceholderAdapter(model, {readOnly:true})` and `createV2Adapter(model, {readOnly:true})` omit `dispatch`, so the viewer disables command controls while continuing to observe the shared model. Removing a view unsubscribes that view; it does not stop or reset the host's session.

## Version 2 state, conservation and replay

The public presentation snapshot adds `circuits`, `portReadings`, `environment`, `zones`, `energyStores`, `ledger` and signed `flowRates`. Circuit readings expose inventory, amount, pressure, temperature, input/output and tracer indices. Port readings aggregate every incident edge: `incoming`, `outgoing`, signed `net = outgoing - incoming`, `rate = abs(net)`, direction and domain. `flowRates[connection]` is negative for reversed transport; `directions` is `-1`, `0` or `1`.

The transfer-switch visual `source` follows its selected energy mode: `source-a`
shows `a`, `source-b` shows `b`, and idle/off shows `off`. Equipment faults do not
imply a protection decision: the v2 protection-relay placeholder reports
`tripped:false` until a replacement model supplies explicit trip behavior. Its
damage and availability still appear separately. The renderer can display a
host-supplied trip state, but this toy model has no protection curve, breaker
interlock or certified contact logic.

`setRodPosition` assigns the illustrative position immediately. The placeholder
has no actuator travel or position-target lag, so its control-rod drive reports
`moving:false`; changing operating load cannot create a fictitious movement
command. A replacement adapter can supply position and motion independently.

V2 damage stress is the maximum of available operating load and retained circuit
pressure. The operating term includes enable, health, accepted power and idle-mode
gates; a high saved command alone cannot damage disabled or unpowered equipment.
Pressure can remain stressful after disable or repair. Stored heat is preserved
and exchanged by the thermal model, but v2 currently has no thermal-stress damage
law. Repair clears damage and the fault latch without resetting switch settings,
pressure, heat or inventories.

Resource allocation caps total outgoing transfer by the donor's available amount and circuit capacity, and incoming transfer by receiving space. Heat and tracers travel with the donor fraction. Rejected excess heat is recorded as a boundary output; clipping never silently discards it. For finite stores, the change in total amount equals `resourceBoundaryIn - resourceBoundaryOut - resourceLeak`. The change in stored heat plus stored energy equals `heatBoundaryIn + energyBoundaryIn - heatBoundaryOut - energyBoundaryOut - energyLoss`, within floating-point tolerance. Tracer reactions and zone indices are separate illustrative state, not conserved chemical quantities.

The instantaneous energy solver iterates until both demand and accepted flow converge. It rejects a cycle that cannot converge within its bounded solve budget and requests a simpler connection graph or explicit storage boundary. It does not turn solver truncation into artificial conversion loss. The full coupled material/energy update uses three resource/energy passes per substep; it is a bounded teaching approximation, not a nonlinear electrical or hydraulic network solver.

V2 exports preserve all circuit amounts, heat, tracers and pressure; energy and thermal stores; zone state; component controls, operating lag, faults, cycle phase, moisture and observations; seed state, time, events and ledger. Import checks exact state shape, nonnegative finite values, current candidate storage capacities, valid modes/phases/faults, monotonic event IDs/times, and matching topology. The signature includes circuit ownership/fluids/roles, conversion endpoints and domains, thermal references and mode-controlled connections. Reusing a signature string cannot authorize a changed candidate model topology. Restoring never advances elapsed time or starts a clock. Reset restores initial inventories and selected initial modes with the current edited model parameters; initial damage 100 immediately latches a fault.

## Version 1 configuration parameters

Every type declares defaults for the same bounded parameter keys; the defaults vary by model family and are all marked `assumed: true` in metadata.

| Key | Bounds | Meaning |
| --- | --- | --- |
| `capacity` | 0–100 | Normalized transfer/supply capacity, toy units per minute |
| `response` | 0–1 | First-order response rate per toy minute |
| `demand` | 0–100 | Nominal demand in toy power units |
| `loss` | 0–1 | Normalized discarded/conversion-loss fraction |
| `pressureGain` | 0–100 | Pressure-index response gain |
| `heatGain` | 0–100 | Heating/cooling-index response gain |
| `warningAt` | 0–100 | Stress-index warning threshold |
| `damageRate` | 0–10 | Damage points per toy minute before the stress and seeded multipliers |

Each component's optional `initial` object accepts `enabled`, `open`, `failed` booleans and `load`, `level`, `inventory`, `temperature`, `pressure`, `damage` indices from 0 to 100. `level` and `inventory` are aliases for initial stock: either can be supplied; if both appear they must agree. An initial failed condition selects the first declared failure mode and its starting damage. Initial damage 100 latches failure. Initial temperature/pressure values are indices even when the corresponding symbol displays °C or kPa.

The optional `kind` selects a registered model family; omitted fields use the type's `defaultModel`. Explicit source/sink roles override finite-stock behavior. To clear parameter edits, construct a new model with the original configuration; `reset()` intentionally keeps them.

Every latched fault is exposed as `controls[id].fault`. A stopped, disconnected or failed telemetry device also has visual `components[id].fault = true`. Degraded and leaking equipment may retain reduced throughput: it shows warning status plus its damage enum and reduced load/speed, while the repair latch stays set. Repair clears the damage and latch; pressure and temperature can take time to settle.

## Version 1 snapshots

The live snapshot contains:

```text
scenarioId, minutes, running
components[id]  typed symbol state: active/running/fault/status plus declared fields
controls[id]    enabled, load, open, fault, level
readings[id]    flow, resourceIn/out, stock, pressure, temperature, load,
                damage, power/powerIn/powerOut/powerRequested, powerFactor,
                signal, quality, connected, blocked, heatIn, overload,
                missingSignal, leak, overflow
parameters[id]  current normalized model parameters
flows[id]       boolean connection activity
flowRates[id]   normalized rate or signal magnitude, interpreted with channels[id]
channels[id]    resource / power / data / measurement / thermal
events[]       id, minutes, type, severity, equipment, message
assumptions[]   model-wide authored assumptions
```

`flowRates` is **not a plant production total**: it includes separate media, electrical supply, signal transfer and measurement activity. Do not sum it across unrelated channels. Signal values are indices; connected measurement channels can be active while the measured process value is zero.

The saved envelope is `scada-placeholder-snapshot` version 1:

```text
format, version
system: {id, signature}
model: <complete model definition>
state: {minutes, running, randomState, nextEventId, components, events}
```

Each saved component contains `enabled`, `open`, `load`, `operating`, `inventory`, `pressure`, `temperature`, `damage`, `failed`, `mode`, `signal`, `warning` and `connected`. The topology signature includes sorted component types and directed connection identities/ports/media. A snapshot from a different topology is rejected even when scenario labels match. Derived display values are recomputed, not trusted from imported markup or summaries.

Import bounds are explicit: elapsed time 0–1,000,000,000 minutes; seed/random state unsigned nonzero 32-bit integers; all dynamic indices 0–100; at most 100 ordered event entries; all IDs, failure modes and component records must match the configured system. Event times cannot lie in the future. Unknown fields, accessors, cycles, prototype traversal, non-finite numbers and oversized structures are rejected before mutation. A failed import leaves the previous model untouched. No import loop advances from zero to the saved time.

## Version 1 equations and topology assumptions

All equations below are normalized teaching rules. They do not establish fluid properties, mass equivalence between media, electrical compatibility, biological yields, gas composition, safe pressure or real thermal duty.

1. **Operating lag:** `operating += (setpoint − operating) × (1 − exp(−response × dt))`. On/off commands gate output immediately; the internal setpoint lag is retained for restart.
2. **Capacity:** nominal capacity × operating/100 × health × available-power fraction × explicit control fraction. Closed process valves pass zero. Variable valve symbols display the resulting effective opening. Breaker `open` has the opposite conduction meaning.
3. **Directed flow:** downstream acceptance propagates backward, then available supply propagates forward through a bounded number of graph passes. Multiple inputs reserve equal acceptance shares; outputs divide available supply in proportion to downstream acceptance. Conversion losses are explicit discarded normalized flow, not chemistry. Closed outlets back up the upstream path; absent upstream supply cannot create downstream material.
4. **Stock:** `stock += (in − out − leak) × dt / 10`, bounded to 0–100. The arbitrary factor 1/10 keeps demonstrations readable. Storage cannot discharge more stock than it has. Empty vessels report zero actual leakage. Explicit source/sink roles exchange resource with an external bench boundary and do not retain finite stock.
5. **Power:** electrical and mechanical edges have their own capacity/acceptance solve. Explicit input power gates driven equipment. A leaf motor consumes its declared demand, while a relay with downstream loads uses transfer capacity. Generator output is limited by connected fuel supply when present. Energy-storage discharge is limited by stored charge and loss; charging and discharging losses have opposite balance directions. Empty stores supply no power.
6. **Pressure:** ordinary equipment blends upstream pressure with an editable load gain; pumps add a larger blocked-outlet term. Storage also responds to inventory. Values remain 0–100 and have no protection-system meaning.
7. **Temperature:** ordinary loads drift toward an ambient index plus load/connected-heat terms. Heater families use the editable heat gain; cooling types reverse its sign. No heat-capacity, phase-change or material recipe is implied.
8. **Sensors and controls:** measurement edges observe the connected component's flow, stock, pressure, thermal index, power or quality proxy. Sensors initialize from their targets and then use first-order lag. Temperature probes use the target symbol's illustrative temperature display range; other ordinary probe readings remain 0–100 indices. Failed telemetry freezes the last reading and removes usable communication. Controllers apply the bounded rule `50 + 1.5 × (setpoint − mean input)`; absent input uses an explicitly assumed bench signal. Missing required communication makes downstream commands unavailable.
9. **Stress and damage:** stress is the greatest of operating load, pressure, temperature and applicable supply/control stress. Above `warningAt`, damage grows by `damageRate × excess/100 × dt × (0.9 + 0.2 × seededRandom)`. Damage is bounded to 100; complete damage latches a type-specific failure. The xorshift32 state is saved for deterministic replay.

Resource/media connections cannot be relabeled to electrical/data ports. Measurement taps may observe a source port and must land on a measurement input. Thermal-only service can heat a thermal or resource receiver without adding material stock. `thermal-fluid` remains a material-like stream. These are topology-category checks, not validation of an engineering design.

## Per-type model templates

`MODEL_DESCRIPTORS` retains the original 80 version 1 contracts. Each descriptor includes family, typed ports, visual fields, inputs, outputs, eight parameter specifications with units/defaults/bounds, assumptions, failure modes and a complete `defaultModel`. `metadata/model-registry.json` is the same serializable data. `V2_MODEL_DESCRIPTORS` and `V2_VARIANT_DESCRIPTORS`, also shipped in `metadata/model-registry-v2.json`, describe the 142-type v2 circuit runtime. A component template cannot contain system-specific thermal reference IDs; `createV2ModelDefinition` adds those default links after equipment IDs are known. [MODEL-MATRIX.md](./MODEL-MATRIX.md) summarizes the mappings.

After changing public descriptors, run `npm --prefix tools/webkit/scada run build:metadata` from the repository root to regenerate both registry JSON files. Use `npm --prefix tools/webkit/scada run check:metadata` in validation; it reports missing or stale files without writing them. The generator preserves the separate v1 and v2 metadata contracts.

To replace built-in equations, register independently checked providers at the
core phase boundary. To replace the entire solver, retain the viewer adapter
contract and component identities. The UI imports neither implementation.
Document units, state meanings, assumptions and reference evidence before
treating the resulting values as validated measurements or predictions.
