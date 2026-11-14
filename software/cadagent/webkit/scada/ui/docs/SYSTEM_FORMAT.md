# SCADA system definition, version 1

Use a **JSON document** to describe equipment, connections, layouts, visual-state bindings and operator controls. Keep the system model, clock, persistence and command implementation in an external adapter. One definition can contain several views of the same component IDs and the same adapter state.

This is the `@valpatel/scada-ui` presentation format. JSON, JSON Schema 2020-12 and RFC 6901 JSON Pointer provide standard syntax and tooling; the document is **not a universal SCADA interchange standard**, PLC program, plant simulator or industrial communication protocol.

- [Complete two-view utility-water example](../examples/minimal-system.json)
- [Runnable five-device utility demo](../examples/viewer/index.html) and its [system JSON](../examples/viewer/system.json)
- [Machine-readable schema](../schema/scada-system.schema.json), identified by `urn:valpatel:scada-system:1`
- [Runtime validator and binding resolver](../src/contracts/system-definition.mjs)
- [Component and viewer APIs](./API.md)

## Load one definition

To explore a complete working example, serve the package directory with `python -m http.server 8000` and open `http://localhost:8000/examples/viewer/`. Its model and adapter are separate files; its two layouts consume the same `system.json` and external session.

```js
import {ScadaViewer, validateSystemDefinition} from '@valpatel/scada-ui';

const authored = await fetch('./minimal-system.json').then(response => {
  if (!response.ok) throw new Error(`Definition request failed: ${response.status}`);
  return response.json();
});
const result = validateSystemDefinition(authored);
if (!result.ok) {
  throw new Error(result.errors.map(error =>
    `${error.path}: ${error.message}`).join('\n'));
}
const viewer = new ScadaViewer({definition:result.definition, adapter});
viewer.mount(document.querySelector('#system'));
viewer.setView('vertical'); // Same components and external state; another layout.

// When removing the presentation:
// viewer.destroy(); // Does not destroy the external adapter or its model.
```

The validator returns `{ok:true, definition}` or `{ok:false, errors}`. Each error has `{path, code, message}`; `path` is a JSON Pointer into the definition. Successful output is a normalized, deeply frozen copy. The authoring input is unchanged. JSON text parsing and fetching remain the host's responsibility.

The JSON Schema checks shape and scalar constraints. Runtime validation additionally checks registry-specific state fields and ports, duplicate IDs, references, canvas bounds, control ranges and safe pointers. Use both when authoring; use runtime validation before mounting imported definitions. Schema validation alone does not verify plant topology or adapter behavior.

## Document map

Required top-level fields are `format`, `version`, `system`, `components` and `views`. Unknown fields are rejected, preventing silent spelling mistakes.

| Field | Meaning |
| --- | --- |
| `format: "scada-system"` | Identifies this format. |
| `version: 1` | Explicit document version. |
| `$schema` | Optional schema-location hint for editors; the runtime does not fetch it. |
| `system: {id, label, description?}` | Stable system identity and readable description. |
| `components: [...]` | Canonical equipment instances, declared once. |
| `connections: [...]` | Canonical endpoint/port references and optional flow bindings. |
| `views: [...]` | Named canvases with placements and polyline routes. |
| `commands: [...]` | Data-only action descriptors passed to the adapter. |
| `controls: [...]` | Buttons, toggles and ranges referring to declared commands. |
| `units: {...}` | Human-readable quantity/unit labels; no automatic unit conversion. |
| `provenance: [...]` | Assumed, recorded, external or illustrative source descriptions. |
| `assumptions: [...]` | Editable, documented scalar guesses; not executable model equations. |

IDs begin with a letter and contain only letters, digits, underscores and dashes, up to 100 characters. Each ID must be unique within its registry. View placements refer to component IDs, never to a separately copied equipment state. Numeric coordinates are finite, nonnegative canvas units; widths and heights are positive. The runtime limits collection size and JSON depth to keep malformed imports bounded.

## Equipment and bindings

An equipment instance may include an optional `variant` string registered for its
`type`, for example `{"id":"standby","type":"generator","variant":"diesel-skid"}`.
The validator resolves the selected ports and state choices before checking
placements, endpoints and bindings. A diesel inlet cannot be connected through
the disabled gas-fuel port. Unknown, null or wrong-type variants are rejected.
Changing variant is a deliberate configuration change, not an automatic graph or
model migration. This backward-compatible field remains presentation version 1;
the headless model has its own independent versioned format.


```json
{
  "id": "storageTank",
  "type": "tank",
  "label": "Utility tank",
  "state": {"active": false, "level": 40},
  "bindings": {
    "active": "/components/storageTank/active",
    "level": "/components/storageTank/level"
  },
  "ports": [{"id": "inlet", "side": "left", "offset": 0.5}],
  "units": {"level": "%"},
  "provenance": ["demo"]
}
```

`type` must exist in the component registry. `state` supplies explicitly authored visual constants or fallback values. `bindings` maps declared visual fields to JSON Pointers in the adapter's snapshot. Field types are strict: a boolean must be a boolean, and a numeric reading must be finite and within the visual field's declared bounds. The adapter performs any necessary physical-to-display conversion. A guessed fallback should have provenance and remain editable in the host application.

`ports` optionally supplies diagram attachment geometry for existing registry port IDs. `side` is `top`, `right`, `bottom` or `left`; `offset` is a fraction from 0 to 1 along that side and defaults to 0.5. An optional `label` can explain the attachment. It cannot invent a physical port or verify a plant connection. Without attachment geometry, the viewer uses the component center when it needs an automatic endpoint.

The exported `resolveBinding(snapshot, pointer)` returns `{found:true, value}` or `{found:false, error:{code,message}}`. Examples:

| Pointer | Reads |
| --- | --- |
| `/components/storageTank/level` | Nested own data properties. |
| `/samples/0/value` | An array element's own value. |
| `/a~1b/~0level` | Keys `a/b` and `~level`; `~1` escapes `/`, `~0` escapes `~`. |
| `""` | The complete snapshot; normally not suitable for a scalar visual field. |

Pointers are paths, not expressions. There is no arithmetic, interpolation, function call, JavaScript, JSONPath, URI-fragment decoding or automatic type coercion. Prototype keys (`__proto__`, `prototype`, `constructor`), inherited properties and accessor/getter traversal are rejected. An undefined or absent value is missing; a present `null` is a value but does not satisfy a boolean/numeric visual field.

### Missing and partial state

`resolveComponentState(instance, snapshot)` returns `{ok, state, errors}`. It applies bindings to authored `state`, validates each value and returns frozen normalized visual state.

- Missing, undefined or invalid bindings retain any explicitly authored fallback for that field, but return diagnostics and force `active:false` and `status:"offline"`. A guessed fallback never silently appears as a live reading.
- With no bindings, the resolver can use explicit visual state from `snapshot.components[instance.id]`. This convenient shape is used by the examples; the format does not require every adapter to use it.
- Without bindings or adapter state, an explicitly authored `state` is static illustrative presentation. With neither, the component is offline and reports missing state.
- A level or instrument reading alone never implies operation. `active` defaults to false unless explicitly supplied by a valid binding, adapter value or authoring state.
- Other omitted visual fields use the registry's presentation defaults. These defaults are drawing choices, not inferred telemetry. See the component API for their bounds and meanings.

## Connections and views

```json
{
  "id": "fillLine",
  "from": {"component": "supplyPump", "port": "outlet"},
  "to": {"component": "storageTank", "port": "inlet"},
  "medium": "liquid",
  "flowBinding": "/flows/fillLine",
  "label": "Assumed fill pipe"
}
```

Each endpoint must reference an existing component and registered port. `medium` and `label` are descriptive metadata. This format does not prove port-direction compatibility, hydraulic continuity, electrical connectivity, capacity, protection or process physics. For example, a diagram may intentionally depict an illustrative coupling to a measurement port; its adapter/model must supply the actual semantics.

`flowBinding` reads a boolean flow indication from the adapter. Missing or invalid flow data must remain inactive. A positive physical flow rate should be converted to an explicit indication in the adapter rather than embedded as an expression. Connections own no simulation timer.

```json
{
  "id": "overview",
  "label": "Utility overview",
  "canvas": {"width": 800, "height": 400},
  "placements": [
    {"component": "supplyPump", "x": 60, "y": 100, "width": 200, "height": 180},
    {"component": "storageTank", "x": 520, "y": 100, "width": 200, "height": 180}
  ],
  "routes": [
    {"connection": "fillLine", "points": [{"x": 260, "y": 190}, {"x": 520, "y": 190}]}
  ]
}
```

A view draws its declared placements and routes. Equipment is placed at most once in a view; a connection is routed at most once there. All boxes and route points must lie within the canvas. Routes need at least two points and are data-only polylines, not arbitrary SVG or HTML. Different views can arrange the same equipment differently.

Partial views may route toward canonical equipment that is not placed on that view, such as an off-screen subsystem represented by a host-owned portal. The route's points still remain inside the current canvas. This does not create another component or another model. Host-specific labels, portals and richer controls can use trusted viewer hooks; they are application code outside the portable JSON format.

## Commands and controls

```json
{
  "commands": [{
    "id": "pumpEnabled",
    "label": "Set supply pump",
    "component": "supplyPump",
    "action": "setPump",
    "arguments": {"equipment": "supplyPump"}
  }],
  "controls": [{
    "id": "pumpSwitch",
    "label": "Supply pump",
    "component": "supplyPump",
    "kind": "toggle",
    "command": "pumpEnabled",
    "binding": "/controls/supplyPump/enabled",
    "diagram": {"whenTrue": "Stop", "whenFalse": "Start"}
  }]
}
```

A command has `id`, `label`, `action`, optional `component`, and optional JSON-object `arguments`. The action is an adapter-defined identifier, not executable source. A control has `id`, `label`, `kind`, `command`, optional `component` and optional `binding`. Toggles and ranges require a binding for their current value. Ranges also require finite `min < max`; positive `step` defaults to 1. Buttons cannot have numeric bounds.

A component-specific toggle can opt into a direct diagram button with
`diagram: {whenTrue, whenFalse}`. Each label names the **next action** for the
current boolean reading: a valve uses `{"whenTrue":"Close","whenFalse":"Open"}`.
Only one direct action is allowed per component; detailed controls remain in its
inspector. Labels are plain text, at most 40 characters. The viewer forwards the
same declared command with the opposite boolean and never interprets equipment
types, action names or physical equations. Bind the operator's switch state,
such as `enabled` or `open`, rather than flow or visual activity: an enabled pump
may have no flow. Missing/wrong-type readings disable the action; read-only
adapters omit direct actions. Rejected commands display the adapter's error and
retain the last accepted state. Clicking the artwork still opens the inspector.

For a toggle or range, the viewer dispatches the referenced command with `arguments.value` set to the new boolean or numeric value. Buttons retain the command's arguments. For the example above:

```js
adapter.dispatch({
  id:'pumpEnabled', label:'Set supply pump', component:'supplyPump',
  action:'setPump', arguments:{equipment:'supplyPump', value:true},
});
```

The adapter implements an explicit action allowlist, validates the supplied value and enforces any authorization or model constraints. Neither JSON Schema nor the viewer turns a command into a hardware write. Credentials, access tokens, passwords, API keys and executable code do not belong in a definition. The runtime rejects common credential keys and non-JSON values; this is not a general-purpose secret scanner. Keep actual connections and secrets in the external application.

An adapter exposes `getSnapshot()`, `subscribe(listener)` returning an unsubscribe function, and optional `dispatch(command)`. Without `dispatch`, the viewer is read-only. Share one adapter across views. The viewer creates no process clock and never resets or destroys the adapter on layout changes or teardown.

## Units, sources and editable guesses

`units` is a map of quantity names to human-readable labels. Component-level units can explain individual visual fields. It does not rescale data. The adapter must supply values in the registry's display ranges, such as tank `level` from 0 to 100.

A provenance entry contains `{id, label, kind, description?, source?}`, where `kind` is `assumed`, `recorded`, `external` or `illustrative`. A component references entries by ID. `source` is descriptive text; the format does not fetch it or treat it as executable content.

An assumption contains `{id, label, value, unit?, description?, provenance?}`. Its value is a JSON scalar, and its optional provenance references an entry. Assumptions document authoring choices; changing one does not automatically change an external model. Provide a corresponding validated adapter command/control when an assumption should be editable in the UI. The example labels all quantities and routes as editable demonstration assumptions rather than measured plant data.

## Versioning, migration and YAML

Version 1 is the first supported version. Unknown or absent versions are rejected; there is no implicit migration and no legacy YAML loader. Keep `format` and `version` in saved files and exports.

For a future incompatible revision, add a new schema/URN and a separate explicit migration function. Preserve stable system/equipment IDs, convert fields into the new shape, validate the result and retain the original file for review. Changing a package version alone must not silently reinterpret an existing document.

YAML may be offered later as an authoring convenience, provided it converts to exactly the same JSON data model before validation. That would require a safe parser with duplicate-key detection and limits, no custom tags/functions or object construction, and explicit handling of aliases. No YAML parser is shipped today. Export canonical JSON for supported interchange; JSON and YAML are not competing layout formats.

From the source checkout, run `node --test tests/webkit/scada/ui/scada-system.test.mjs` for boundary cases and `npm --prefix tools/webkit/scada run build:metadata` to synchronize discovery metadata. A JSON Schema 2020-12 validator can validate the example against `schema/scada-system.schema.json`; no schema-validator runtime dependency is required by the browser package.
