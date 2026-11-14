# Valpatel SCADA UI

[SCADA owner map](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/README.md) · [Documentation map](./docs/README.md) · [Examples map](./examples/README.md)

Reusable animated equipment, accessible workspace primitives and a system viewer for browser applications. The package contains **142 equipment types across 11 families**, typed visual state and a versioned system-definition contract. It has no framework dependency and no process, electrical, PLC or network simulation inside it.

The [state coverage review](./docs/STATE_COVERAGE.md) separates equipment-specific
responses, shared effects, actual browser evidence and remaining lifecycle gaps
for every type and variant. Catalog membership does not mean every state is complete.

This is cad-agent’s canonical equipment and diagram library. The SCADA Explorer consumes it directly; another host can use a local file dependency, an npm tarball or the source browser modules. The package is `private: true` and `UNLICENSED`; it has not been published to the public npm registry, and packaging does not grant new license rights.

[API reference](./docs/API.md) · [System format](./docs/SYSTEM_FORMAT.md) · [Style guide](./STYLE_GUIDE.md) · [Contributing](./CONTRIBUTING.md) · [Agent prompts](./AGENT_PROMPTS.md) · [Animated image gallery](./img/README.md) · [Thumbnail manifest](./metadata/thumbnails.json) · [Variant previews](./docs/VARIANTS.md) · [Power references](./docs/POWER_REFERENCES.md) · [Agriculture references](./docs/AGRICULTURE_REFERENCES.md)

## Folder map

| Folder | Contents |
| --- | --- |
| [src/](./src/README.md) | Canonical data contracts, equipment art, workspace primitives and viewer/controller implementations. |
| [docs/](./docs/README.md) | Public APIs, system format, references and candid state-coverage review. |
| [schema/](./schema/README.md) | Portable presentation schema and its catalog-derived sections. |
| [metadata/](./metadata/README.md) | Generated discovery snapshots and image provenance receipts. |
| [examples/](./examples/README.md) | Authored single-component and shared-model viewer examples. |
| [img/](./img/README.md) | This package's animated symbol gallery, state images and JPEG thumbnails. |
| [Source tools](https://github.com/Valpatel/cad-agent/blob/dev/tools/webkit/scada/ui/README.md) | Development-only generation, capture and QA, outside this runtime package. |
| [Source tests](https://github.com/Valpatel/cad-agent/blob/dev/tests/webkit/scada/ui/README.md) | Contract, rendering and export checks, outside this runtime package. |

```mermaid
flowchart LR
  host[Host application and model adapter] --> viewer[Viewer and workspace]
  document[Versioned system document] --> viewer
  viewer --> symbols[Equipment symbols]
  symbols --> catalog[Pure typed catalog]
  catalog --> metadata[Portable metadata]
  symbols --> gallery[Package-owned image gallery]
```

The arrows show ownership/use, not a second simulation engine. The host owns one canonical model/session; the package supplies reusable views and controls for that session. Gallery and metadata outputs are generated from those same source owners.

## Find the right layer

| You need to… | Start here |
| --- | --- |
| Filter by industry, technology, medium or fuel | [Discovery API](./docs/API.md#discovery-and-variants), `src/catalog/discovery.mjs` |
| Pick a symbol or family | [Animated family gallery](./img/README.md), [equipment catalog](#equipment-catalog), [contact sheet](./img/thumbnails/contact-sheet.jpg) |
| Render one device from visual state | [Component API](./docs/API.md), `src/symbols/index.mjs` |
| Add dialogs, toolbars or status surfaces | [Workspace primitives](#workspace-primitives), `src/workspace/workspace.mjs` / `.css` |
| Display and control another application's system | [Viewer and model adapter](#viewer-and-model-adapter), public `ScadaViewer` |
| Define equipment, layouts, bindings and controls as data | [System format](./docs/SYSTEM_FORMAT.md), [JSON Schema](./schema/scada-system.schema.json), [minimal definition](./examples/minimal-system.json) |
| Match the appearance or add a type/state | [STYLE_GUIDE.md](./STYLE_GUIDE.md), [CONTRIBUTING.md](./CONTRIBUTING.md) |
| Give a future agent a concrete task | [AGENT_PROMPTS.md](./AGENT_PROMPTS.md) |

```text
software/cadagent/webkit/scada/ui/
├── package.json                 local package and explicit public exports
├── README.md                    this map and thumbnail catalog
├── STYLE_GUIDE.md                appearance, geometry, states and accessibility
├── CONTRIBUTING.md              canonical-source and verification workflow
├── AGENT_PROMPTS.md / AGENTS.md  future-agent tasks and scoped rules
├── src/
│   ├── index.mjs / styles.css   stable public package entries
│   ├── metadata.mjs             data-only registry/discovery entry
│   ├── catalog/                pure descriptors, state normalization, discovery
│   │   └── definitions/        industrial, power and agriculture metadata
│   ├── contracts/              system-definition validation and bindings
│   ├── symbols/                equipment renderer and component skin
│   │   ├── art/                process, industrial, controls, agriculture, twin art
│   │   └── power/              energy, electrical, nuclear and genset art
│   ├── workspace/              native dialogs, focus and toolbar lifecycle
│   └── viewer/                 diagram rendering and adapter-driven controller
├── docs/                        API and versioned system-format documentation
├── schema/                      machine-readable system definition contract
├── examples/                    browser examples and a minimal system definition
├── metadata/                    generated registry and thumbnail manifests
└── img/                         symbols/, states/ and thumbnails/ with Markdown indexes
```

[The source map](./src/README.md) explains ownership and dependency direction. Import package exports or the actual domain files. Catalog, metadata and system validation do not import SVG renderers. Development tools and tests have separate owners under `tools/webkit/scada/` and `tests/webkit/scada/`.

`src/` is canonical. Run `npm --prefix tools/webkit/scada run build:metadata` from the repository root to regenerate discovery metadata. The cad-agent site compiler publishes the same package at `/kit/scada/ui/`; never repair an output copy. The package does not own the host application's model, clock, persistence or plant connection.

## Package-owned image gallery

[Browse animated symbols by family](./img/README.md), [visual state examples](./img/states/README.md), and [viewer/workspace snapshots](./img/thumbnails/README.md). Every equipment type and declared variant has a source-derived preview. The SVG files contain the canonical artwork and inline decorative CSS animation; they require no JavaScript, external styles, fonts or live model. Static renderers retain the silhouette and readouts. Image animation support is renderer-dependent; use the interactive examples to change state.

The gallery travels with this library under `img/`. [Scenario diagrams](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/sim/img/README.md) belong to the model library's own `img/`, and future electrical-panel or harness libraries should own their galleries in the same way. Root documentation links to owners; it does not become a shared asset bucket. Machine-readable [gallery metadata](./metadata/gallery.json) records the exact supplied state, source hashes and output hashes. Use `@valpatel/scada-ui/img/*` for package-owned assets.

## Use it

For a bundler or Node-based project, install the local package or a packed tarball:

```sh
# From the repository containing this package:
npm pack ./software/cadagent/webkit/scada/ui --pack-destination /tmp

# From the consuming application (substitute the actual absolute path):
npm install /absolute/path/valpatel-scada-ui-1.4.1.tgz
# Or: npm install /absolute/path/cad-agent/software/cadagent/webkit/scada/ui
```

```js
import {renderScadaComponent} from '@valpatel/scada-ui';
import '@valpatel/scada-ui/styles'; // For bundlers that load CSS imports.

container.innerHTML = renderScadaComponent('plc-rack', {
  id: 'north-plc',
  label: 'North process controller',
  state: {active: true, running: true, connected: true, load: 45},
});
```

For a browser without a bundler, serve the package directory and use relative URLs:

```html
<link rel="stylesheet" href="./src/styles.css">
<div id="equipment" style="width:260px;height:200px"></div>
<script type="module">
  import {renderScadaComponent} from './src/index.mjs';
  document.querySelector('#equipment').innerHTML =
    renderScadaComponent('tank', {
      id: 'reuse-water-tank',
      label: 'Reuse water tank',
      state: {level: 38, running: true},
    });
</script>
```

Use `python -m http.server 8000` from the package directory, then open `http://localhost:8000/examples/components/` for the [equipment example](./examples/components/index.html) or `/examples/viewer/` for the system viewer. ES-module loading from `file:` URLs is browser-dependent. The package is already browser-ready; consumers need no repository build script. Individual component/workspace entry points and styles are available through the explicit `package.json` export map. [The API reference](./docs/API.md) explains all fields, dependencies and lifecycle details.

## Viewer and model adapter

The reusable viewer follows a model/view/controller boundary:

- **Model:** your application owns one canonical state, clock, persistence and command implementation. The package has no independent plant session.
- **Definition:** a validated, versioned JSON document describes equipment, layouts, bindings and controls. Bindings read explicit snapshot paths; JSON is never evaluated as code.
- **View:** equipment renderers and workspace primitives display the supplied state.
- **Controller:** `ScadaViewer` manages active layout, selection, zoom, the inspector and dispatch through the supplied adapter.

An adapter provides `getSnapshot()` and `subscribe(listener)`. `dispatch(command)` is optional; omitting it creates a read-only viewer. Share the same adapter/model between views so a valve change, fault, clock or reading is consistent everywhere. Switching layout or destroying a presentation must not reset that external model.

```js
import {ScadaViewer, validateSystemDefinition} from '@valpatel/scada-ui';

export function mountSystem(root, definition, adapter) {
  const result = validateSystemDefinition(definition);
  if (!result.ok) {
    throw new Error(result.errors.map(error =>
      `${error.path}: ${error.message}`).join('\n'));
  }
  const viewer = new ScadaViewer({definition: result.definition, adapter});
  viewer.mount(root);
  return () => viewer.destroy(); // The external model/clock stays owned by you.
}
```

Use the [minimal definition](./examples/minimal-system.json) and [system-format guide](./docs/SYSTEM_FORMAT.md) rather than inventing a JSON structure. [API.md](./docs/API.md) records the actual viewer methods and adapter contract. The [independent viewer demo](./examples/viewer/index.html) keeps its [utility model](./examples/viewer/utility-model.mjs) separate from the package UI.

[![Reusable system viewer](img/thumbnails/workspace/generic-viewer.jpg)](./examples/viewer/index.html)

## Equipment catalog

The registry is authoritative for exact fields and ports. Each preview is rendered from its canonical source with a fixed visual pose. Variant choices preserve the type ID; use discovery filters and resolved metadata before connecting a system. All capacities and model values remain external, editable assumptions.

### Process vessels

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/process/digester/default.jpg"><img src="img/thumbnails/equipment/process/digester/default.jpg" alt="Anaerobic digester preview" width="112"></a> | **Anaerobic digester**<br>`digester`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs) | `level`, `damage` | 4 | Twin artwork |
| <a href="img/thumbnails/equipment/process/tank/default.jpg"><img src="img/thumbnails/equipment/process/tank/default.jpg" alt="Storage tank preview" width="112"></a> | **Storage tank**<br>`tank`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/process/gas-holder/default.jpg"><img src="img/thumbnails/equipment/process/gas-holder/default.jpg" alt="Gas holder preview" width="112"></a> | **Gas holder**<br>`gas-holder`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs) | `level`, `damage` | 2 | Twin artwork |
| <a href="img/thumbnails/equipment/process/mixing-tank/default.jpg"><img src="img/thumbnails/equipment/process/mixing-tank/default.jpg" alt="Mixing tank preview" width="112"></a> | **Mixing tank**<br>`mixing-tank`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/process/reactor/default.jpg"><img src="img/thumbnails/equipment/process/reactor/default.jpg" alt="Pressure reactor preview" width="112"></a> | **Pressure reactor**<br>`reactor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/clarifier/default.jpg"><img src="img/thumbnails/equipment/process/clarifier/default.jpg" alt="Circular clarifier preview" width="112"></a> | **Circular clarifier**<br>`clarifier`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/process/silo/default.jpg"><img src="img/thumbnails/equipment/process/silo/default.jpg" alt="Bulk solids silo preview" width="112"></a> | **Bulk solids silo**<br>`silo`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/process/heat-exchanger/default.jpg"><img src="img/thumbnails/equipment/process/heat-exchanger/default.jpg" alt="Heat exchanger preview" width="112"></a> | **Heat exchanger**<br>`heat-exchanger`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `load`, `temperature`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/filter/default.jpg"><img src="img/thumbnails/equipment/process/filter/default.jpg" alt="Media filter preview" width="112"></a> | **Media filter**<br>`filter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/process/gas-treatment/default.jpg"><img src="img/thumbnails/equipment/process/gas-treatment/default.jpg" alt="Gas treatment train preview" width="112"></a> | **Gas treatment train**<br>`gas-treatment`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs) | `load`, `damage` | 3 | Twin artwork |
| <a href="img/thumbnails/equipment/process/boiler/default.jpg"><img src="img/thumbnails/equipment/process/boiler/default.jpg" alt="Gas-fired boiler preview" width="112"></a> | **Gas-fired boiler**<br>`boiler`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs)<br>3 explicit variants | `load`, `temperature`, `damage` | 6 | Twin artwork |
| <a href="img/thumbnails/equipment/process/flare/default.jpg"><img src="img/thumbnails/equipment/process/flare/default.jpg" alt="Flare stack preview" width="112"></a> | **Flare stack**<br>`flare`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs) | `load`, `damage` | 2 | Twin artwork |
| <a href="img/thumbnails/equipment/process/centrifuge/default.jpg"><img src="img/thumbnails/equipment/process/centrifuge/default.jpg" alt="Industrial centrifuge preview" width="112"></a> | **Industrial centrifuge**<br>`centrifuge`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `speed`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/flotation-cell/default.jpg"><img src="img/thumbnails/equipment/process/flotation-cell/default.jpg" alt="Flotation cell preview" width="112"></a> | **Flotation cell**<br>`flotation-cell`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `level`, `load`, `speed`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/membrane-filter/default.jpg"><img src="img/thumbnails/equipment/process/membrane-filter/default.jpg" alt="Membrane filter preview" width="112"></a> | **Membrane filter**<br>`membrane-filter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/reverse-osmosis/default.jpg"><img src="img/thumbnails/equipment/process/reverse-osmosis/default.jpg" alt="Reverse osmosis skid preview" width="112"></a> | **Reverse osmosis skid**<br>`reverse-osmosis`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/distillation-column/default.jpg"><img src="img/thumbnails/equipment/process/distillation-column/default.jpg" alt="Distillation column preview" width="112"></a> | **Distillation column**<br>`distillation-column`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `level`, `load`, `temperature`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/separator/default.jpg"><img src="img/thumbnails/equipment/process/separator/default.jpg" alt="Three-phase separator preview" width="112"></a> | **Three-phase separator**<br>`separator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs)<br>1 explicit variants | `level`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/cyclone/default.jpg"><img src="img/thumbnails/equipment/process/cyclone/default.jpg" alt="Cyclone separator preview" width="112"></a> | **Cyclone separator**<br>`cyclone`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/scrubber/default.jpg"><img src="img/thumbnails/equipment/process/scrubber/default.jpg" alt="Wet scrubber preview" width="112"></a> | **Wet scrubber**<br>`scrubber`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `level`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/cooling-tower/default.jpg"><img src="img/thumbnails/equipment/process/cooling-tower/default.jpg" alt="Cooling tower preview" width="112"></a> | **Cooling tower**<br>`cooling-tower`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `speed`, `temperature`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/chiller/default.jpg"><img src="img/thumbnails/equipment/process/chiller/default.jpg" alt="Industrial chiller preview" width="112"></a> | **Industrial chiller**<br>`chiller`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `temperature`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/process/evaporator/default.jpg"><img src="img/thumbnails/equipment/process/evaporator/default.jpg" alt="Falling-film evaporator preview" width="112"></a> | **Falling-film evaporator**<br>`evaporator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `level`, `load`, `temperature`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/process/wellhead/default.jpg"><img src="img/thumbnails/equipment/process/wellhead/default.jpg" alt="Production wellhead preview" width="112"></a> | **Production wellhead**<br>`wellhead`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs)<br>2 explicit variants | `load`, `open`, `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/process/aeration-basin/default.jpg"><img src="img/thumbnails/equipment/process/aeration-basin/default.jpg" alt="Aeration basin preview" width="112"></a> | **Aeration basin**<br>`aeration-basin`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `level`, `load`, `damage` | 5 | Visual only |

### Pumps & machinery

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/rotating/pump/default.jpg"><img src="img/thumbnails/equipment/rotating/pump/default.jpg" alt="Centrifugal pump preview" width="112"></a> | **Centrifugal pump**<br>`pump`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs)<br>8 explicit variants | `load`, `speed`, `damage` | 3 | Twin artwork |
| <a href="img/thumbnails/equipment/rotating/submersible-pump/default.jpg"><img src="img/thumbnails/equipment/rotating/submersible-pump/default.jpg" alt="Submersible pump preview" width="112"></a> | **Submersible pump**<br>`submersible-pump`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/rotating/dosing-pump/default.jpg"><img src="img/thumbnails/equipment/rotating/dosing-pump/default.jpg" alt="Metering pump preview" width="112"></a> | **Metering pump**<br>`dosing-pump`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/rotating/blower/default.jpg"><img src="img/thumbnails/equipment/rotating/blower/default.jpg" alt="Centrifugal blower preview" width="112"></a> | **Centrifugal blower**<br>`blower`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>1 explicit variants | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/rotating/compressor/default.jpg"><img src="img/thumbnails/equipment/rotating/compressor/default.jpg" alt="Reciprocating compressor preview" width="112"></a> | **Reciprocating compressor**<br>`compressor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/rotating/motor/default.jpg"><img src="img/thumbnails/equipment/rotating/motor/default.jpg" alt="Electric motor preview" width="112"></a> | **Electric motor**<br>`motor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `speed`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/rotating/fan/default.jpg"><img src="img/thumbnails/equipment/rotating/fan/default.jpg" alt="Axial ventilation fan preview" width="112"></a> | **Axial ventilation fan**<br>`fan`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `speed`, `damage` | 4 | Visual only |

### Power & energy

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/power/generator/default.jpg"><img src="img/thumbnails/equipment/power/generator/default.jpg" alt="Microturbine generator preview" width="112"></a> | **Microturbine generator**<br>`generator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs)<br>5 explicit variants | `load`, `speed`, `damage` | 5 | Twin artwork |
| <a href="img/thumbnails/equipment/power/transformer/default.jpg"><img src="img/thumbnails/equipment/power/transformer/default.jpg" alt="Power transformer preview" width="112"></a> | **Power transformer**<br>`transformer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/power/breaker/default.jpg"><img src="img/thumbnails/equipment/power/breaker/default.jpg" alt="Circuit breaker preview" width="112"></a> | **Circuit breaker**<br>`breaker`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `open`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/power/busbar/default.jpg"><img src="img/thumbnails/equipment/power/busbar/default.jpg" alt="Distribution bus preview" width="112"></a> | **Distribution bus**<br>`busbar`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/battery/default.jpg"><img src="img/thumbnails/equipment/power/battery/default.jpg" alt="Battery bank preview" width="112"></a> | **Battery bank**<br>`battery`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `damage` | 1 | Visual only |
| <a href="img/thumbnails/equipment/power/ups/default.jpg"><img src="img/thumbnails/equipment/power/ups/default.jpg" alt="Uninterruptible supply preview" width="112"></a> | **Uninterruptible supply**<br>`ups`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/solar-panel/default.jpg"><img src="img/thumbnails/equipment/power/solar-panel/default.jpg" alt="Solar array preview" width="112"></a> | **Solar array**<br>`solar-panel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `load`, `damage` | 1 | Visual only |
| <a href="img/thumbnails/equipment/power/electrical-meter/default.jpg"><img src="img/thumbnails/equipment/power/electrical-meter/default.jpg" alt="Net power indicator preview" width="112"></a> | **Net power indicator**<br>`electrical-meter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/twin.mjs) | `load`, `damage` | 2 | Twin artwork |
| <a href="img/thumbnails/equipment/power/electrolyzer/default.jpg"><img src="img/thumbnails/equipment/power/electrolyzer/default.jpg" alt="Water electrolyzer preview" width="112"></a> | **Water electrolyzer**<br>`electrolyzer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `temperature`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/fuel-cell/default.jpg"><img src="img/thumbnails/equipment/power/fuel-cell/default.jpg" alt="Fuel-cell generator preview" width="112"></a> | **Fuel-cell generator**<br>`fuel-cell`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `temperature`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/wind-turbine/default.jpg"><img src="img/thumbnails/equipment/power/wind-turbine/default.jpg" alt="Wind turbine preview" width="112"></a> | **Wind turbine**<br>`wind-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `speed`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/power/steam-turbine/default.jpg"><img src="img/thumbnails/equipment/power/steam-turbine/default.jpg" alt="Steam turbine preview" width="112"></a> | **Steam turbine**<br>`steam-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/process.mjs) | `load`, `speed`, `temperature`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/gas-turbine/default.jpg"><img src="img/thumbnails/equipment/power/gas-turbine/default.jpg" alt="Combustion gas turbine preview" width="112"></a> | **Combustion gas turbine**<br>`gas-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `load`, `speed`, `flow`, `heat`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/power/heat-recovery-steam-generator/default.jpg"><img src="img/thumbnails/equipment/power/heat-recovery-steam-generator/default.jpg" alt="Heat recovery steam generator preview" width="112"></a> | **Heat recovery steam generator**<br>`heat-recovery-steam-generator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `primaryFlow`, `secondaryFlow`, `level`, `heat`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/power/surface-condenser/default.jpg"><img src="img/thumbnails/equipment/power/surface-condenser/default.jpg" alt="Surface condenser preview" width="112"></a> | **Surface condenser**<br>`surface-condenser`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `primaryFlow`, `secondaryFlow`, `level`, `heat`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/deaerator/default.jpg"><img src="img/thumbnails/equipment/power/deaerator/default.jpg" alt="Feedwater deaerator preview" width="112"></a> | **Feedwater deaerator**<br>`deaerator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `level`, `flow`, `heat`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/cooling-radiator/default.jpg"><img src="img/thumbnails/equipment/power/cooling-radiator/default.jpg" alt="Cooling radiator preview" width="112"></a> | **Cooling radiator**<br>`cooling-radiator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `speed`, `flow`, `heat`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/power/fuel-pressure-regulator/default.jpg"><img src="img/thumbnails/equipment/power/fuel-pressure-regulator/default.jpg" alt="Fuel pressure regulator preview" width="112"></a> | **Fuel pressure regulator**<br>`fuel-pressure-regulator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `open`, `opening`, `pressure`, `flow`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/reservoir/default.jpg"><img src="img/thumbnails/equipment/power/reservoir/default.jpg" alt="Water reservoir preview" width="112"></a> | **Water reservoir**<br>`reservoir`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `level`, `flow`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/intake-gate/default.jpg"><img src="img/thumbnails/equipment/power/intake-gate/default.jpg" alt="Hydraulic intake gate preview" width="112"></a> | **Hydraulic intake gate**<br>`intake-gate`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `open`, `opening`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/hydro-turbine/default.jpg"><img src="img/thumbnails/equipment/power/hydro-turbine/default.jpg" alt="Hydraulic turbine preview" width="112"></a> | **Hydraulic turbine**<br>`hydro-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `speed`, `load`, `flow`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/reversible-pump-turbine/default.jpg"><img src="img/thumbnails/equipment/power/reversible-pump-turbine/default.jpg" alt="Reversible pump-turbine preview" width="112"></a> | **Reversible pump-turbine**<br>`reversible-pump-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `speed`, `load`, `flow`, `mode`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/power-inverter/default.jpg"><img src="img/thumbnails/equipment/power/power-inverter/default.jpg" alt="DC/AC power inverter preview" width="112"></a> | **DC/AC power inverter**<br>`power-inverter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs)<br>2 explicit variants | `load`, `direction`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/heliostat/default.jpg"><img src="img/thumbnails/equipment/power/heliostat/default.jpg" alt="Heliostat mirror preview" width="112"></a> | **Heliostat mirror**<br>`heliostat`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `position`, `irradiance`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/solar-receiver/default.jpg"><img src="img/thumbnails/equipment/power/solar-receiver/default.jpg" alt="Solar tower receiver preview" width="112"></a> | **Solar tower receiver**<br>`solar-receiver`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `flow`, `heat`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/parabolic-trough/default.jpg"><img src="img/thumbnails/equipment/power/parabolic-trough/default.jpg" alt="Parabolic-trough collector preview" width="112"></a> | **Parabolic-trough collector**<br>`parabolic-trough`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `position`, `irradiance`, `flow`, `heat`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/tidal-turbine/default.jpg"><img src="img/thumbnails/equipment/power/tidal-turbine/default.jpg" alt="Tidal-current turbine preview" width="112"></a> | **Tidal-current turbine**<br>`tidal-turbine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `speed`, `load`, `current`, `direction`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/wave-energy-converter/default.jpg"><img src="img/thumbnails/equipment/power/wave-energy-converter/default.jpg" alt="Wave point absorber preview" width="112"></a> | **Wave point absorber**<br>`wave-energy-converter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs) | `load`, `wave`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/alternator/default.jpg"><img src="img/thumbnails/equipment/power/alternator/default.jpg" alt="Synchronous alternator preview" width="112"></a> | **Synchronous alternator**<br>`alternator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/energy.mjs)<br>2 explicit variants | `load`, `speed`, `heat`, `field`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/hv-circuit-breaker/default.jpg"><img src="img/thumbnails/equipment/power/hv-circuit-breaker/default.jpg" alt="High-voltage circuit breaker preview" width="112"></a> | **High-voltage circuit breaker**<br>`hv-circuit-breaker`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/disconnect-switch/default.jpg"><img src="img/thumbnails/equipment/power/disconnect-switch/default.jpg" alt="Air-break disconnect switch preview" width="112"></a> | **Air-break disconnect switch**<br>`disconnect-switch`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs)<br>2 explicit variants | `open`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/earthing-switch/default.jpg"><img src="img/thumbnails/equipment/power/earthing-switch/default.jpg" alt="Earthing switch preview" width="112"></a> | **Earthing switch**<br>`earthing-switch`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/current-transformer/default.jpg"><img src="img/thumbnails/equipment/power/current-transformer/default.jpg" alt="Current transformer preview" width="112"></a> | **Current transformer**<br>`current-transformer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `value`, `connected`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/voltage-transformer/default.jpg"><img src="img/thumbnails/equipment/power/voltage-transformer/default.jpg" alt="Voltage transformer preview" width="112"></a> | **Voltage transformer**<br>`voltage-transformer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `value`, `connected`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/surge-arrester/default.jpg"><img src="img/thumbnails/equipment/power/surge-arrester/default.jpg" alt="Surge arrester preview" width="112"></a> | **Surge arrester**<br>`surge-arrester`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `stress`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/capacitor-bank/default.jpg"><img src="img/thumbnails/equipment/power/capacitor-bank/default.jpg" alt="Switched capacitor bank preview" width="112"></a> | **Switched capacitor bank**<br>`capacitor-bank`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `load`, `steps`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/shunt-reactor/default.jpg"><img src="img/thumbnails/equipment/power/shunt-reactor/default.jpg" alt="Shunt reactor preview" width="112"></a> | **Shunt reactor**<br>`shunt-reactor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `load`, `heat`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/power/protection-relay/default.jpg"><img src="img/thumbnails/equipment/power/protection-relay/default.jpg" alt="Protection relay preview" width="112"></a> | **Protection relay**<br>`protection-relay`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `value`, `connected`, `tripped`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/switchgear-panel/default.jpg"><img src="img/thumbnails/equipment/power/switchgear-panel/default.jpg" alt="Metal-clad switchgear panel preview" width="112"></a> | **Metal-clad switchgear panel**<br>`switchgear-panel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `load`, `connected`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/gis-bay/default.jpg"><img src="img/thumbnails/equipment/power/gis-bay/default.jpg" alt="Gas-insulated switchgear bay preview" width="112"></a> | **Gas-insulated switchgear bay**<br>`gis-bay`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `open`, `load`, `pressure`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/automatic-transfer-switch/default.jpg"><img src="img/thumbnails/equipment/power/automatic-transfer-switch/default.jpg" alt="Automatic transfer switch preview" width="112"></a> | **Automatic transfer switch**<br>`automatic-transfer-switch`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `source`, `load`, `automatic`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/power/excitation-system/default.jpg"><img src="img/thumbnails/equipment/power/excitation-system/default.jpg" alt="Generator excitation system preview" width="112"></a> | **Generator excitation system**<br>`excitation-system`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `load`, `field`, `connected`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/power/power-rectifier/default.jpg"><img src="img/thumbnails/equipment/power/power-rectifier/default.jpg" alt="AC/DC rectifier preview" width="112"></a> | **AC/DC rectifier**<br>`power-rectifier`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/electrical.mjs) | `load`, `direction`, `damage` | 4 | Visual only |

### Valves

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/valves/gate-valve/default.jpg"><img src="img/thumbnails/equipment/valves/gate-valve/default.jpg" alt="Gate valve preview" width="112"></a> | **Gate valve**<br>`gate-valve`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `opening`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/valves/control-valve/default.jpg"><img src="img/thumbnails/equipment/valves/control-valve/default.jpg" alt="Control valve preview" width="112"></a> | **Control valve**<br>`control-valve`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `opening`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/valves/check-valve/default.jpg"><img src="img/thumbnails/equipment/valves/check-valve/default.jpg" alt="Check valve preview" width="112"></a> | **Check valve**<br>`check-valve`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/valves/relief-valve/default.jpg"><img src="img/thumbnails/equipment/valves/relief-valve/default.jpg" alt="Pressure relief valve preview" width="112"></a> | **Pressure relief valve**<br>`relief-valve`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/valves/butterfly-valve/default.jpg"><img src="img/thumbnails/equipment/valves/butterfly-valve/default.jpg" alt="Butterfly valve preview" width="112"></a> | **Butterfly valve**<br>`butterfly-valve`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `opening`, `damage` | 2 | Visual only |

### Instruments

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/instruments/pressure-transmitter/default.jpg"><img src="img/thumbnails/equipment/instruments/pressure-transmitter/default.jpg" alt="Pressure transmitter preview" width="112"></a> | **Pressure transmitter**<br>`pressure-transmitter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/flow-meter/default.jpg"><img src="img/thumbnails/equipment/instruments/flow-meter/default.jpg" alt="Inline flow meter preview" width="112"></a> | **Inline flow meter**<br>`flow-meter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/temperature-sensor/default.jpg"><img src="img/thumbnails/equipment/instruments/temperature-sensor/default.jpg" alt="Temperature probe preview" width="112"></a> | **Temperature probe**<br>`temperature-sensor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/level-sensor/default.jpg"><img src="img/thumbnails/equipment/instruments/level-sensor/default.jpg" alt="Level transmitter preview" width="112"></a> | **Level transmitter**<br>`level-sensor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `level`, `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/gas-analyzer/default.jpg"><img src="img/thumbnails/equipment/instruments/gas-analyzer/default.jpg" alt="Gas analyzer preview" width="112"></a> | **Gas analyzer**<br>`gas-analyzer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/water-quality-probe/default.jpg"><img src="img/thumbnails/equipment/instruments/water-quality-probe/default.jpg" alt="Water-quality probe preview" width="112"></a> | **Water-quality probe**<br>`water-quality-probe`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `connected`, `measurement`, `value`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/humidity-sensor/default.jpg"><img src="img/thumbnails/equipment/instruments/humidity-sensor/default.jpg" alt="Humidity sensor preview" width="112"></a> | **Humidity sensor**<br>`humidity-sensor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `connected`, `humidity`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/instruments/light-sensor/default.jpg"><img src="img/thumbnails/equipment/instruments/light-sensor/default.jpg" alt="PAR light sensor preview" width="112"></a> | **PAR light sensor**<br>`light-sensor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `connected`, `light`, `damage` | 3 | Visual only |

### PLC & networks

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/automation/plc-rack/default.jpg"><img src="img/thumbnails/equipment/automation/plc-rack/default.jpg" alt="PLC rack preview" width="112"></a> | **PLC rack**<br>`plc-rack`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/automation/plc-cpu/default.jpg"><img src="img/thumbnails/equipment/automation/plc-cpu/default.jpg" alt="PLC CPU preview" width="112"></a> | **PLC CPU**<br>`plc-cpu`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/automation/remote-io/default.jpg"><img src="img/thumbnails/equipment/automation/remote-io/default.jpg" alt="Remote IO station preview" width="112"></a> | **Remote IO station**<br>`remote-io`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/automation/hmi/default.jpg"><img src="img/thumbnails/equipment/automation/hmi/default.jpg" alt="Operator HMI preview" width="112"></a> | **Operator HMI**<br>`hmi`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/automation/scada-server/default.jpg"><img src="img/thumbnails/equipment/automation/scada-server/default.jpg" alt="SCADA server preview" width="112"></a> | **SCADA server**<br>`scada-server`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `load`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/automation/network-switch/default.jpg"><img src="img/thumbnails/equipment/automation/network-switch/default.jpg" alt="Industrial network switch preview" width="112"></a> | **Industrial network switch**<br>`network-switch`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/automation/radio/default.jpg"><img src="img/thumbnails/equipment/automation/radio/default.jpg" alt="Telemetry radio preview" width="112"></a> | **Telemetry radio**<br>`radio`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/control.mjs) | `connected`, `damage` | 3 | Visual only |

### Connections

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/connections/pipe/default.jpg"><img src="img/thumbnails/equipment/connections/pipe/default.jpg" alt="Process pipe preview" width="112"></a> | **Process pipe**<br>`pipe`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs)<br>8 explicit variants | `open`, `damage` | 2 | Visual only |
| <a href="img/thumbnails/equipment/connections/junction/default.jpg"><img src="img/thumbnails/equipment/connections/junction/default.jpg" alt="Four-way junction preview" width="112"></a> | **Four-way junction**<br>`junction`<br>[API](./docs/API.md#public-api) · [source](src/symbols/index.mjs) | `open`, `damage` | 4 | Visual only |

### Manufacturing & solids

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/manufacturing/conveyor/default.jpg"><img src="img/thumbnails/equipment/manufacturing/conveyor/default.jpg" alt="Belt conveyor preview" width="112"></a> | **Belt conveyor**<br>`conveyor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/crusher/default.jpg"><img src="img/thumbnails/equipment/manufacturing/crusher/default.jpg" alt="Jaw crusher preview" width="112"></a> | **Jaw crusher**<br>`crusher`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/vibrating-screen/default.jpg"><img src="img/thumbnails/equipment/manufacturing/vibrating-screen/default.jpg" alt="Vibrating screen preview" width="112"></a> | **Vibrating screen**<br>`vibrating-screen`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/grinding-mill/default.jpg"><img src="img/thumbnails/equipment/manufacturing/grinding-mill/default.jpg" alt="Grinding mill preview" width="112"></a> | **Grinding mill**<br>`grinding-mill`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/rotary-kiln/default.jpg"><img src="img/thumbnails/equipment/manufacturing/rotary-kiln/default.jpg" alt="Rotary kiln preview" width="112"></a> | **Rotary kiln**<br>`rotary-kiln`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `temperature`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/oven/default.jpg"><img src="img/thumbnails/equipment/manufacturing/oven/default.jpg" alt="Conveyor oven preview" width="112"></a> | **Conveyor oven**<br>`oven`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `temperature`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/rack-oven/default.jpg"><img src="img/thumbnails/equipment/manufacturing/rack-oven/default.jpg" alt="Rack / batch oven preview" width="112"></a> | **Rack / batch oven**<br>`rack-oven`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `temperature`, `open`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/dryer/default.jpg"><img src="img/thumbnails/equipment/manufacturing/dryer/default.jpg" alt="Rotary dryer preview" width="112"></a> | **Rotary dryer**<br>`dryer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `temperature`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/extruder/default.jpg"><img src="img/thumbnails/equipment/manufacturing/extruder/default.jpg" alt="Screw extruder preview" width="112"></a> | **Screw extruder**<br>`extruder`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/tablet-press/default.jpg"><img src="img/thumbnails/equipment/manufacturing/tablet-press/default.jpg" alt="Tablet press preview" width="112"></a> | **Tablet press**<br>`tablet-press`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/filling-line/default.jpg"><img src="img/thumbnails/equipment/manufacturing/filling-line/default.jpg" alt="Filling line preview" width="112"></a> | **Filling line**<br>`filling-line`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/packaging-line/default.jpg"><img src="img/thumbnails/equipment/manufacturing/packaging-line/default.jpg" alt="Packaging line preview" width="112"></a> | **Packaging line**<br>`packaging-line`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/granulator/default.jpg"><img src="img/thumbnails/equipment/manufacturing/granulator/default.jpg" alt="Granulator preview" width="112"></a> | **Granulator**<br>`granulator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/forming-machine/default.jpg"><img src="img/thumbnails/equipment/manufacturing/forming-machine/default.jpg" alt="Forming machine preview" width="112"></a> | **Forming machine**<br>`forming-machine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/drum-mixer/default.jpg"><img src="img/thumbnails/equipment/manufacturing/drum-mixer/default.jpg" alt="Drum mixer preview" width="112"></a> | **Drum mixer**<br>`drum-mixer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/paper-machine/default.jpg"><img src="img/thumbnails/equipment/manufacturing/paper-machine/default.jpg" alt="Paper machine preview" width="112"></a> | **Paper machine**<br>`paper-machine`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/weigh-hopper/default.jpg"><img src="img/thumbnails/equipment/manufacturing/weigh-hopper/default.jpg" alt="Weigh hopper preview" width="112"></a> | **Weigh hopper**<br>`weigh-hopper`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `level`, `load`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/manufacturing/screw-feeder/default.jpg"><img src="img/thumbnails/equipment/manufacturing/screw-feeder/default.jpg" alt="Screw feeder preview" width="112"></a> | **Screw feeder**<br>`screw-feeder`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/industrial.mjs) | `load`, `speed`, `damage` | 3 | Visual only |

### Nuclear systems

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/nuclear/pwr-reactor-vessel/default.jpg"><img src="img/thumbnails/equipment/nuclear/pwr-reactor-vessel/default.jpg" alt="Pressurized-water reactor vessel preview" width="112"></a> | **Pressurized-water reactor vessel**<br>`pwr-reactor-vessel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `load`, `heat`, `flow`, `level`, `rodPosition`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/bwr-reactor-vessel/default.jpg"><img src="img/thumbnails/equipment/nuclear/bwr-reactor-vessel/default.jpg" alt="Boiling-water reactor vessel preview" width="112"></a> | **Boiling-water reactor vessel**<br>`bwr-reactor-vessel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `load`, `heat`, `flow`, `level`, `rodPosition`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/phwr-calandria/default.jpg"><img src="img/thumbnails/equipment/nuclear/phwr-calandria/default.jpg" alt="PHWR calandria and pressure channels preview" width="112"></a> | **PHWR calandria and pressure channels**<br>`phwr-calandria`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `load`, `heat`, `flow`, `level`, `rodPosition`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/gas-cooled-reactor/default.jpg"><img src="img/thumbnails/equipment/nuclear/gas-cooled-reactor/default.jpg" alt="Gas-cooled reactor concept preview" width="112"></a> | **Gas-cooled reactor concept**<br>`gas-cooled-reactor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `load`, `heat`, `flow`, `rodPosition`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/sodium-reactor-vessel/default.jpg"><img src="img/thumbnails/equipment/nuclear/sodium-reactor-vessel/default.jpg" alt="Sodium-cooled reactor concept preview" width="112"></a> | **Sodium-cooled reactor concept**<br>`sodium-reactor-vessel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `load`, `heat`, `flow`, `level`, `rodPosition`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/molten-salt-reactor/default.jpg"><img src="img/thumbnails/equipment/nuclear/molten-salt-reactor/default.jpg" alt="Molten-salt reactor concept preview" width="112"></a> | **Molten-salt reactor concept**<br>`molten-salt-reactor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs)<br>1 explicit variants | `load`, `heat`, `flow`, `level`, `rodPosition`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/nuclear-steam-generator/default.jpg"><img src="img/thumbnails/equipment/nuclear/nuclear-steam-generator/default.jpg" alt="Nuclear steam generator preview" width="112"></a> | **Nuclear steam generator**<br>`nuclear-steam-generator`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs)<br>5 explicit variants | `primaryFlow`, `secondaryFlow`, `level`, `heat`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/pressurizer/default.jpg"><img src="img/thumbnails/equipment/nuclear/pressurizer/default.jpg" alt="Pressurizer preview" width="112"></a> | **Pressurizer**<br>`pressurizer`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `level`, `heat`, `pressure`, `damage` | 6 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/containment-structure/default.jpg"><img src="img/thumbnails/equipment/nuclear/containment-structure/default.jpg" alt="Containment structure preview" width="112"></a> | **Containment structure**<br>`containment-structure`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `pressure`, `integrity`, `flow`, `heat`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/used-fuel-pool/default.jpg"><img src="img/thumbnails/equipment/nuclear/used-fuel-pool/default.jpg" alt="Used-fuel cooling pool preview" width="112"></a> | **Used-fuel cooling pool**<br>`used-fuel-pool`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `level`, `flow`, `heat`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/control-rod-drive/default.jpg"><img src="img/thumbnails/equipment/nuclear/control-rod-drive/default.jpg" alt="Control-rod drive indicator preview" width="112"></a> | **Control-rod drive indicator**<br>`control-rod-drive`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `rodPosition`, `speed`, `moving`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/neutron-monitor/default.jpg"><img src="img/thumbnails/equipment/nuclear/neutron-monitor/default.jpg" alt="Neutron monitor concept preview" width="112"></a> | **Neutron monitor concept**<br>`neutron-monitor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `value`, `connected`, `damage` | 3 | Visual only |
| <a href="img/thumbnails/equipment/nuclear/radiation-monitor/default.jpg"><img src="img/thumbnails/equipment/nuclear/radiation-monitor/default.jpg" alt="Radiation monitor concept preview" width="112"></a> | **Radiation monitor concept**<br>`radiation-monitor`<br>[API](./docs/API.md#public-api) · [source](src/symbols/power/nuclear.mjs) | `value`, `connected`, `damage` | 3 | Visual only |

### Growing & aquaculture

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/agriculture/fish-tank/default.jpg"><img src="img/thumbnails/equipment/agriculture/fish-tank/default.jpg" alt="Aquaculture fish tank preview" width="112"></a> | **Aquaculture fish tank**<br>`fish-tank`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `level`, `oxygen`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/biofilter/default.jpg"><img src="img/thumbnails/equipment/agriculture/biofilter/default.jpg" alt="Biological media filter preview" width="112"></a> | **Biological media filter**<br>`biofilter`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `level`, `oxygen`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/media-grow-bed/default.jpg"><img src="img/thumbnails/equipment/agriculture/media-grow-bed/default.jpg" alt="Media grow bed preview" width="112"></a> | **Media grow bed**<br>`media-grow-bed`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `level`, `moisture`, `phase`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/dwc-raft-bed/default.jpg"><img src="img/thumbnails/equipment/agriculture/dwc-raft-bed/default.jpg" alt="Deep-water raft bed preview" width="112"></a> | **Deep-water raft bed**<br>`dwc-raft-bed`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `level`, `oxygen`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/nft-channel/default.jpg"><img src="img/thumbnails/equipment/agriculture/nft-channel/default.jpg" alt="Nutrient-film channel preview" width="112"></a> | **Nutrient-film channel**<br>`nft-channel`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `moisture`, `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/ebb-flow-table/default.jpg"><img src="img/thumbnails/equipment/agriculture/ebb-flow-table/default.jpg" alt="Ebb-and-flow nursery table preview" width="112"></a> | **Ebb-and-flow nursery table**<br>`ebb-flow-table`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `level`, `moisture`, `phase`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/drip-zone/default.jpg"><img src="img/thumbnails/equipment/agriculture/drip-zone/default.jpg" alt="Drip irrigation zone preview" width="112"></a> | **Drip irrigation zone**<br>`drip-zone`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `moisture`, `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/aeroponic-chamber/default.jpg"><img src="img/thumbnails/equipment/agriculture/aeroponic-chamber/default.jpg" alt="Aeroponic root chamber preview" width="112"></a> | **Aeroponic root chamber**<br>`aeroponic-chamber`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `moisture`, `load`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/grow-light/default.jpg"><img src="img/thumbnails/equipment/agriculture/grow-light/default.jpg" alt="Horticultural light panel preview" width="112"></a> | **Horticultural light panel**<br>`grow-light`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `light`, `load`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/agriculture/air-diffuser/default.jpg"><img src="img/thumbnails/equipment/agriculture/air-diffuser/default.jpg" alt="Submerged air diffuser preview" width="112"></a> | **Submerged air diffuser**<br>`air-diffuser`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `airflow`, `oxygen`, `damage` | 2 | Visual only |

### Climate control

| Preview | Component | Extra states | Ports | Support |
| --- | --- | --- | --- | --- |
| <a href="img/thumbnails/equipment/climate/greenhouse-vent/default.jpg"><img src="img/thumbnails/equipment/climate/greenhouse-vent/default.jpg" alt="Greenhouse vent preview" width="112"></a> | **Greenhouse vent**<br>`greenhouse-vent`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `opening`, `airflow`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/climate/shade-screen/default.jpg"><img src="img/thumbnails/equipment/climate/shade-screen/default.jpg" alt="Retractable shade screen preview" width="112"></a> | **Retractable shade screen**<br>`shade-screen`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `opening`, `light`, `damage` | 4 | Visual only |
| <a href="img/thumbnails/equipment/climate/evaporative-pad/default.jpg"><img src="img/thumbnails/equipment/climate/evaporative-pad/default.jpg" alt="Evaporative cooling pad preview" width="112"></a> | **Evaporative cooling pad**<br>`evaporative-pad`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `moisture`, `airflow`, `humidity`, `damage` | 5 | Visual only |
| <a href="img/thumbnails/equipment/climate/dehumidifier/default.jpg"><img src="img/thumbnails/equipment/climate/dehumidifier/default.jpg" alt="Air dehumidifier preview" width="112"></a> | **Air dehumidifier**<br>`dehumidifier`<br>[API](./docs/API.md#public-api) · [source](src/symbols/art/agriculture.mjs) | `humidity`, `level`, `load`, `damage` | 5 | Visual only |

## Workspace primitives

These surfaces use the same standalone stylesheet and native controls. The workspace shell owns focus and dialog lifecycle, not system state.

| Preview | Primitive | API / source |
| --- | --- | --- |
| <a href="img/thumbnails/workspace/toolbar.jpg"><img src="img/thumbnails/workspace/toolbar.jpg" alt="Workspace toolbar" width="200"></a> | Toolbar and grouped actions | `renderScadaToolbar()` · [API](./docs/API.md#workspace-api) · [source](src/workspace/workspace.mjs) |
| <a href="img/thumbnails/workspace/dialog.jpg"><img src="img/thumbnails/workspace/dialog.jpg" alt="Native equipment dialog" width="200"></a> | Native modal with focus return | `renderScadaDialog()` + `ScadaWorkspace` · [API](./docs/API.md#workspace-api) |
| <a href="img/thumbnails/workspace/statusbar.jpg"><img src="img/thumbnails/workspace/statusbar.jpg" alt="Workspace status bar" width="200"></a> | Status bar | `.scada-statusbar` · [styles](src/workspace/workspace.css) |
| <a href="img/thumbnails/workspace/buttons.jpg"><img src="img/thumbnails/workspace/buttons.jpg" alt="Action buttons and status badges" width="200"></a> | Normal, primary, pressed, danger and disabled buttons; badges | `.scada-toolbutton`, `.scada-toolbadge` · [styles](src/workspace/workspace.css) |
| <a href="img/thumbnails/workspace/panels.jpg"><img src="img/thumbnails/workspace/panels.jpg" alt="Workspace panels and actions" width="200"></a> | Panel groups and actions | `.scada-panel-grid`, `.scada-panel-section`, `.scada-actions` · [styles](src/workspace/workspace.css) |
| <a href="img/thumbnails/workspace/metrics.jpg"><img src="img/thumbnails/workspace/metrics.jpg" alt="Workspace metric strip" width="200"></a> | Readable metric strip | `.scada-metric-strip` · [styles](src/workspace/workspace.css) |

Use a neutral `.scada-workspace` container; no application-specific `#main` wrapper is required. Keep user text escaped when composing trusted body/footer/control markup. All interactive targets should be native controls with visible focus and at least 44 px size. See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for behavior and [API.md](./docs/API.md) for lifecycle examples.

## Thumbnails and verification

[The contact sheet](./img/thumbnails/contact-sheet.jpg) compares equipment silhouettes. [metadata/thumbnails.json](./metadata/thumbnails.json) records generated files, render settings and state. [`img/thumbnails/states/`](./img/thumbnails/states/) contains representative non-default states. Static previews document appearance; they do not prove animation or command behavior.

From the repository root, run `npm --prefix tools/webkit/scada run build:metadata`, `npm --prefix tools/webkit/scada test` and `npm --prefix tools/webkit/scada run thumbnails` for visual changes. `npm --prefix tools/webkit/scada run thumbnails -- --check` verifies the manifest and source/image hashes without silently accepting stale previews. The [contribution guide](./CONTRIBUTING.md) distinguishes source sync, rendered checks, npm packaging, the standalone ZIP and live deployment. A generated artifact or a green test does not publish a release.

## Files

| File | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Scoped authoring and verification instructions. |
| [package.json](package.json) | Private package metadata and explicit public exports. |
| [LICENSE.txt](LICENSE.txt) | Retained package terms, included in runtime distributions. |

The notice’s source-identity and authorization record is the repository-owned
[source provenance](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/SOURCE.json);
the package includes the actual retained terms in `LICENSE.txt`.
