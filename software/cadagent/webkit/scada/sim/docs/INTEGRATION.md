# Integrating the SCADA simulation kit

The kit separates reusable UI, a system description and a replaceable model. Start with [the industry explorer](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/explorer/index.html) to operate 60 example systems, or with [the scenario catalog](../scenarios/index.json) to select a system as data. The 20 original industry examples retain version 1 behavior; 33 power, six agriculture and one electric batch-oven example explicitly select version 2. All placeholder behavior and numeric values are illustrative. The examples prove connections, state changes, commands and UI lifecycle; they are not validated engineering models or manufacturing recipes.

Both engines also accept trusted registered equation providers for replacing
constitutive laws and per-component dynamic state within the existing kernel.
Use the [model adaptation guide](./REAL_MODEL_ADAPTATION.md),
[physical equation examples](../examples/equation-models/README.md) and
[model-switching bench](../examples/model-switching/README.md). Pass providers
through constructor `equationProviders`, select them with data-only
`definition.equations`, and use `setEquationBindings()` for an atomic selection or
parameter change. The existing adapter/viewer lifecycle remains the same. A
complete external network solver can instead implement the adapter directly.

## Package map

| Layer | Source | Owns |
| --- | --- | --- |
| Symbols and workspace | [`@valpatel/scada-ui`](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/README.md) | Original SVG artwork, typed visual states, animation, accessible controls and native dialogs |
| System description | [`scada-system` v1 JSON](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/docs/SYSTEM_FORMAT.md) | Component identities, ports, connections, layouts, snapshot bindings and declared controls |
| Viewer/controller | [`ScadaViewer`](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/docs/API.md#viewer-api) | Selection, layout, zoom, inspector and command dispatch through an injected adapter |
| Placeholder model | [`@valpatel/scada-sim`](../README.md) | Deterministic equipment behavior, shared readings, parameters, failures and snapshots |
| Example application | [sibling Explorer](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/explorer/README.md) | Scenario loading, one clock, browser file downloads/imports and the surrounding control room |
| Your CAD or operations host | Your application | Document/session identity, persistence, authorization, real model or historian/PLC integration, if any |

Neither package has to know your application framework. Importing either package creates no process clock or hardware connection. The UI never creates its own model per diagram view.

For a local integration, copy or install the `ui/` and `sim/` source packages. Their manifests are private and `UNLICENSED`; a tarball is a distribution format and grants no additional license rights. Runtime module graphs are package-owned. Development tools and tests are repository-owned outside the runtime packages.

The [Explorer](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/explorer/README.md) is a separate source owner beside both libraries. Serve `software/cadagent/webkit/` to use `/scada/explorer/`, or use the compiled site's `/kit/scada/explorer/`. The application owns the clock, navigation, browser file IO and audio. There is no generated Explorer copy inside `sim/examples/`.

## Mount one model into a viewer

Use real JSON files from a scenario rather than constructing an undocumented format:

```js
import {ScadaViewer, validateSystemDefinition} from '@valpatel/scada-ui';
import {PlaceholderSystemModel, createPlaceholderAdapter} from '@valpatel/scada-sim';
import '@valpatel/scada-ui/styles'; // Bundler stylesheet import.

export function mountControlRoom(container, system, modelConfig) {
  const checked = validateSystemDefinition(system);
  if (!checked.ok) {
    throw new Error(checked.errors.map(item => `${item.path}: ${item.message}`).join('\n'));
  }
  const model = new PlaceholderSystemModel(checked.definition, modelConfig);
  const adapter = createPlaceholderAdapter(model);
  const viewer = new ScadaViewer({definition: checked.definition, adapter});
  viewer.mount(container);

  // The host owns exactly one clock for this model. Rendering is independent.
  const timer = setInterval(() => {
    if (!document.hidden && model.getSnapshot().running) model.step(1);
  }, 1000);

  return {
    model,
    viewer,
    destroy() {
      clearInterval(timer);
      viewer.destroy();
      model.destroy();
    },
  };
}
```

`step(1)` advances one illustrative model minute, regardless of wall-clock time. The example intentionally does not accumulate hidden-tab time. A CAD host can call `step()` explicitly from its own timeline instead of starting a timer. Use one clock policy per session; do not combine an external timer with another scheduler.

The viewer's `setView(id)` changes only presentation. It does not reset inventory, equipment commands, faults, parameters or elapsed time. To mount a second monitor on the same session, reuse the same model:

```js
const monitor = new ScadaViewer({
  definition: system,
  adapter: createPlaceholderAdapter(model, {readOnly: true}),
  initialView: system.views[1].id,
  scope: 'cad-inspection-monitor',
});
monitor.mount(monitorContainer);

// The monitor omits dispatch. It still subscribes to the same model.
monitor.destroy(); // Does not stop or destroy the shared model.
```

A host can retain a session while a route closes. Destroy the viewer for that route, retain the model and adapter in the host session store, then mount a new viewer on return. Destroy the model only when the host deliberately closes or replaces that session.

## Replace placeholder behavior without replacing the UI

The adapter has three members:

```js
const adapter = {
  getSnapshot: () => canonicalModelSnapshot,
  subscribe(listener) {
    // Register the listener, then return its matching cleanup function.
    return unsubscribe;
  },
  dispatch(command) {
    // Validate and execute a declared command in the host controller.
    // Return a result or Promise; errors are shown by the viewer.
  },
};
```

Omit `dispatch` for a read-only view. Do not implement a fake dispatch that silently ignores controls. A real host must validate commands and enforce authorization independently of the display.

Each component's system JSON bindings are explicit JSON Pointers into the adapter snapshot. Keep those pointers stable when replacing the placeholder model, or migrate the bindings deliberately. The viewer does not evaluate expressions, scripts or arbitrary property paths. Missing or invalid bindings display unavailable/offline data; they should not be replaced with a fabricated normal reading.

The placeholder adapter accepts operations such as `setEnabled`, `setOpen`, `setLoad`, `setFault`, `repair` and `setParameter`. A declared command uses an action identifier and plain arguments:

```js
adapter.dispatch({
  action: 'setLoad',
  arguments: {equipment: 'a-component-id-from-system-json', value: 65},
});
```

When using another engine, map these commands to its controller API, or update the versioned system's command definitions. Never place executable model code in a system JSON document. A real process model may run in a worker, on a server or in a separate solver; the UI boundary stays the same.

## Use equipment models as placeholders

Every registered symbol has a corresponding version 2 model descriptor; the unchanged version 1 registry covers the original 80 types. Select the version that matches the model definition. Version 1 uses shared family classes, while version 2 declares circuits, energy domains and stores. Each descriptor records ports, inputs/outputs, units, assumptions, editable parameters and available failure modes. Inspect that metadata before building controls:

```js
import {getModelDescriptor} from '@valpatel/scada-sim';

const pump = getModelDescriptor('pump', {version:2, variant:'water'});
// Existing version 1 callers retain getModelDescriptor('pump').
console.log(pump.parameters);   // label, unit, bounds, default, assumed flag
console.log(pump.circuitParameters); // version 2 circuit-editor fields
console.log(pump.failureModes); // id, label and description
console.log(pump.assumptions);
```

The explorer's parameter editor is generated from those descriptors. Parameter edits affect the one canonical model and are reflected in every view. The display remains visually useful with the model paused or reduced motion enabled; damage and warning information does not depend on animation.

Normalized pressure, flow, quality and process indices are not physical design predictions. A visual temperature scale, animation speed or nominal electrical load is also not a validated equipment rating. Replace equations, units, thresholds and control policy together when connecting a real model. Preserve clear provenance for measured, assumed and derived values.

## JSON, YAML and industry exchange formats

`scada-system` version 1 is this kit's portable JSON contract. Its [JSON Schema](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/schema/scada-system.schema.json) validates document shape, while runtime validation also checks references and bindings. This is not a claim that there is one universal SCADA diagram standard.

YAML can be an authoring convenience in a host application, provided a safe parser converts it to the same plain JSON structure and the result passes the same validators. The kit does not bundle a YAML parser or support executable YAML tags.

Formats such as AutomationML, OPC UA information models and domain-specific CAD/process exchange formats have different scopes. A future import/export bridge should map their identities, connectivity, units and provenance into this contract explicitly. Do not infer verified engineering semantics from a diagram symbol or approximate port name.

## CAD-agent integration points

Use stable component IDs as the bridge between a CAD document and a running simulation session. Keep placement coordinates and route points in the view definition; keep process parameters in the separate model configuration. The same equipment can appear in a detailed process view, a utilities view and a CAD selection overlay without creating three assets.

A useful host workflow is:

1. Select a component in the CAD document and call `viewer.select(componentId, {open: true})`.
2. Use a `selectionChange` viewer hook to highlight the corresponding CAD entity.
3. Edit ports, placement or routing in the CAD document, then validate and remount the presentation against the retained adapter.
4. Send operating commands through the adapter; let the model publish updated snapshots.
5. Save document/layout data and model session data as separate artifacts with explicit version identifiers.

Avoid using the model's evolving inventory, fault or elapsed time as CAD document geometry. Avoid storing a viewer object or timer in serialized JSON. If a document edit removes or renames equipment, reconcile its model identity explicitly before restoring an old session.

## Sessions and validation

The explorer downloads three distinct artifacts: the system definition, the model configuration with current parameter edits, and a model session snapshot. The session snapshot is restored through the model's strict import API into the matching system. Invalid imports must leave the existing session intact. The explorer applies a 2 MiB import limit for this small example application; production hosts can set limits appropriate to their data model.

Treat imported JSON as untrusted data even when an agent generated it. Validate definitions and model configuration, check component references and value bounds, and preserve the model/controller boundary. A read-only review surface should use an adapter without dispatch.

## Extending the kit

Use the [UI style guide](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/STYLE_GUIDE.md), [contribution workflow](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/CONTRIBUTING.md) and [agent prompts](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/ui/AGENT_PROMPTS.md) for visual additions. Add a corresponding descriptor/model and a runnable scenario placement for each new equipment type. Verify off/on, low/high activity, warning, fault, offline and relevant damage states. Render the symbol at card size, inspector size and its actual system layout, and regenerate its thumbnail from source.

The explorer intentionally uses `ScadaViewer` and `ScadaWorkspace` as a consumer. Keep app-specific scenario browsing, file import/export and clock policy here rather than expanding the model-free UI package with application behavior.

## Optional sound in the host

The explorer’s [`sound.mjs`](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/explorer/sound.mjs) is a separate, optional browser example. It reads aggregate model snapshots and generates a quiet machinery mix and warning/fault tones with Web Audio. The simulation engine and UI renderer do not create audio. Sound starts off on each reload, creates its AudioContext only after the user enables it, and goes silent while the model is paused or the tab is hidden. Acknowledgment silences current alarms; clearing and reintroducing a condition makes it eligible again. Audio does not replace visible warning or fault states.
