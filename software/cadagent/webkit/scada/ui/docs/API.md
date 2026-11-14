# SCADA UI API

The component library provides 142 original SVG equipment types across 11 visual families, including power generation, substations, conceptual nuclear equipment, aquaculture, hydroponics and climate control. It uses the same glass, metal and teal visual language as the digester twin.

These are presentation components. They do not calculate process physics, execute PLC logic, communicate with hardware or implement equipment protection. The host supplies state. The isolated [component example](../examples/components/README.md) changes visual state without creating a plant simulation.

## Package and browser entry points

[The package README](../README.md) maps installation and the package-owned [image gallery](../img/README.md). Canonical files live in `src/`; `npm --prefix tools/webkit/scada run build:metadata` refreshes metadata. The site compiler publishes the package under `/kit/scada/ui/`. Consumers use the package directly without website tooling.

Use `@valpatel/scada-ui` for the public JavaScript entry, or `/components`, `/catalog`, `/workspace`, `/viewer` and `/system-definition` for focused entry points. `/metadata` exposes the registry without constructing a DOM or model session; `/metadata.json` exposes the generated JSON registry. `/thumbnails.json` and `/thumbnails/*` expose the JPEG preview manifest and images; the latter remains an alias for `img/thumbnails/`. `/img/*` exposes package-owned image files and `/gallery.json` exposes the generated animated SVG gallery manifest. `/schema` (or `/schema.json`) resolves the system JSON Schema. Styles are exported as `/styles` (or `/styles.css`), `/components.css`, `/workspace.css` and `/viewer.css`. The package's export map is authoritative.

For a browser without a bundler, serve the package directory and load relative URLs:

```html
<link rel="stylesheet" href="./src/styles.css">
<div id="equipment" style="width:260px;height:200px"></div>
<script type="module">
  import {renderScadaComponent} from './src/index.mjs';
  document.querySelector('#equipment').innerHTML =
    renderScadaComponent('plc-rack', {
      id: 'plc-rack-01',
      label: 'North process controller',
      state: {active: true, running: true, connected: true, load: 45},
    });
</script>
```

`src/styles.css` combines the component, workspace and viewer styles. Public exports point directly to implementation under `src/catalog`, `src/contracts`, `src/symbols`, `src/workspace` and `src/viewer`; preserve the complete `src/` tree when copying browser assets. Catalog, metadata and system validation load only data contracts, not SVG renderers. The component renderer imports the artwork it needs. No framework, external service or process engine is required. See [the source map](../src/README.md).

Npm tarballs retain examples under `examples/`. From the package directory run `python -m http.server 8000`, then open `http://localhost:8000/examples/components/` or `/examples/viewer/`. Serve ES modules over HTTP; `file:` loading is browser-dependent.

## Public API

```js
import {
  SCADA_COMPONENTS,
  SCADA_CATEGORIES,
  getScadaComponent,
  normalizeScadaState,
  renderScadaComponent,
} from '@valpatel/scada-ui/components';
```

`SCADA_COMPONENTS` is a deeply frozen array of descriptors. Each contains `type`, `id`, `name`, `label`, `category`, `description`, `ports`, `stateFields`, `defaultState`, `modelSupport`, `provenance` and `sharedKind`. `SCADA_CATEGORIES` is a frozen array of `{id, label}` records. `getScadaComponent(type, {variant} = {})` returns effective metadata for a validated type/variant and throws for an unknown selection. Optional `taxonomy`, `variants`, `circuits`, `powerDomains` and `evidence` describe discovery and explicit adapter boundaries; they contain no physics.

| Family | Type IDs |
| --- | --- |
| `process` | `digester`, `tank`, `gas-holder`, `mixing-tank`, `reactor`, `clarifier`, `silo`, `heat-exchanger`, `filter`, `gas-treatment`, `boiler`, `flare`, `centrifuge`, `flotation-cell`, `membrane-filter`, `reverse-osmosis`, `distillation-column`, `separator`, `cyclone`, `scrubber`, `cooling-tower`, `chiller`, `evaporator`, `wellhead`, `aeration-basin` |
| `rotating` | `pump`, `submersible-pump`, `dosing-pump`, `blower`, `compressor`, `motor`, `fan` |
| `power` | `generator`, `transformer`, `breaker`, `busbar`, `battery`, `ups`, `solar-panel`, `electrical-meter`, `electrolyzer`, `fuel-cell`, `wind-turbine`, `steam-turbine`, `gas-turbine`, `heat-recovery-steam-generator`, `surface-condenser`, `deaerator`, `cooling-radiator`, `fuel-pressure-regulator`, `reservoir`, `intake-gate`, `hydro-turbine`, `reversible-pump-turbine`, `power-inverter`, `heliostat`, `solar-receiver`, `parabolic-trough`, `tidal-turbine`, `wave-energy-converter`, `alternator`, `hv-circuit-breaker`, `disconnect-switch`, `earthing-switch`, `current-transformer`, `voltage-transformer`, `surge-arrester`, `capacitor-bank`, `shunt-reactor`, `protection-relay`, `switchgear-panel`, `gis-bay`, `automatic-transfer-switch`, `excitation-system`, `power-rectifier` |
| `valves` | `gate-valve`, `control-valve`, `check-valve`, `relief-valve`, `butterfly-valve` |
| `instruments` | `pressure-transmitter`, `flow-meter`, `temperature-sensor`, `level-sensor`, `gas-analyzer`, `water-quality-probe`, `humidity-sensor`, `light-sensor` |
| `automation` | `plc-rack`, `plc-cpu`, `remote-io`, `hmi`, `scada-server`, `network-switch`, `radio` |
| `connections` | `pipe`, `junction` |
| `manufacturing` | `conveyor`, `crusher`, `vibrating-screen`, `grinding-mill`, `rotary-kiln`, `oven`, `rack-oven`, `dryer`, `extruder`, `tablet-press`, `filling-line`, `packaging-line`, `granulator`, `forming-machine`, `drum-mixer`, `paper-machine`, `weigh-hopper`, `screw-feeder` |
| `nuclear` | `pwr-reactor-vessel`, `bwr-reactor-vessel`, `phwr-calandria`, `gas-cooled-reactor`, `sodium-reactor-vessel`, `molten-salt-reactor`, `nuclear-steam-generator`, `pressurizer`, `containment-structure`, `used-fuel-pool`, `control-rod-drive`, `neutron-monitor`, `radiation-monitor` |
| `agriculture` | `fish-tank`, `biofilter`, `media-grow-bed`, `dwc-raft-bed`, `nft-channel`, `ebb-flow-table`, `drip-zone`, `aeroponic-chamber`, `grow-light`, `air-diffuser` |
| `climate` | `greenhouse-vent`, `shade-screen`, `evaporative-pad`, `dehumidifier` |

The stable `oven` type is the continuous **Conveyor oven**. `rack-oven` is a separate front-loading **Rack / batch oven** with stationary trays and an opening door. Its illustrative heat reading is a 0–100 index, not degrees Celsius; the example model documents retained heat and the visual-only door command.

### Discovery and variants

See the [generated variant preview map](./VARIANTS.md) for every explicit option.

```js
import {findScadaComponents, getScadaFacets, getScadaVariants,
  getScadaComponent, CAPACITY_PRESETS} from '@valpatel/scada-ui/catalog';

const choices = findScadaComponents({industry: 'power', query: 'generator'});
const diesels = findScadaComponents({fuel: 'diesel'});
const facets = getScadaFacets();
const options = getScadaVariants('generator');
const selected = getScadaComponent('generator', {variant: 'diesel-skid'});
```

Exact filters are `type`, `category`, `industry`, `system`, `function`, `medium`, `technology`, `fuel`, `variant` and `modelSupport`. A string or nonempty string array is accepted: OR within a field, AND across fields. `query` is a case-insensitive token search over names, descriptions, taxonomy and variants. Results are immutable and sorted by stable type ID. Unknown keys, inherited properties and accessors are rejected without execution. `getScadaFacets()` supplies sorted filter values.

Discovery returns equipment families; a medium or fuel facet can match an explicitly offered variant. Resolve the actual selection before building connections. `getScadaComponent(type,{variant})` applies only declared port/carrier/domain/circuit changes and restricts mode/direction choices. For example, diesel and gasoline gensets expose `liquid-fuel` and disable the gas `fuel` inlet; a helium steam-generator primary uses gas ports while its isolated secondary remains water/steam. Selecting a variant does not migrate an existing graph automatically. `getScadaVariants(type)` is immutable. A plain getter preserves the baseline descriptor; `defaultVariant` is an advisory preset and is applied only when explicitly selected.

`renderScadaComponent(type,{variant,state,...})` and `normalizeScadaState(type,state,{variant})` use the same selection. An explicit generator variant chooses cabinet, skid or portable-frame artwork. Omitting the generator variant preserves the original twin drawing. `hostState:true` is the legacy twin-art contract and rejects explicit variants. Capacity is independent of enclosure and fuel: `CAPACITY_PRESETS` contains editable demonstration values, not equipment ratings.

Generic utility variants declare illustrative carrier compatibility and separate circuit groups. They do not certify pumps or pipe materials for helium, sodium, salt, heavy water or organic fluids. The external model authors exact fluid identities and any permitted heat transfer or phase conversion. The UI never merges circuits, infers transformer ratios or calculates nuclear behavior.

### Declared state

`normalizeScadaState(type, input = {}, {variant} = {})` merges the type's defaults and returns a new plain object. It rejects unknown keys, symbol keys, arrays, unsupported object prototypes, accessor properties, incorrect types, unsupported select options and non-finite numbers. Getters are rejected without being executed. Finite numeric values are clamped to the descriptor's range. It does not infer units, convert telemetry or change any physical model.

Every type declares:

| Field | Type | Meaning |
| --- | --- | --- |
| `active` | Boolean | Whether the equipment is visually active. |
| `running` | Boolean | Whether its animation runs; this is a presentation choice. |
| `fault` | Boolean | Explicit fault presentation. It does not inject model damage. |
| `status` | Select | `normal`, `warning` or `offline`. |
| `damage` | Select | Type-specific physical visual conditions; defaults to `none`. |

Additional fields are declared only where relevant. Power/nuclear fields include normalized `heat`, `flow`, `primaryFlow`, `secondaryFlow`, `rodPosition`, `pressure`, `integrity`, `field`, `irradiance`, `current`, `wave` and device-specific switches/modes. Agriculture adds `oxygen`, `moisture`, `light`, `humidity`, `airflow` and irrigation phase. These new readings are percentages or fictional indices, not calibrated radiation, chemistry or operating values. Legacy fields include: `level`, `load`, `speed` and `opening` (0–100), `temperature` (type-specific illustrative °C bounds), `value` (an illustrative instrument reading), `open` and `connected`. An invalid/offline/broken/disconnected instrument displays an em dash and an unavailable accessible description rather than an unqualified numeric gauge. Drift may retain a clearly marked reading. Every numeric field has a visible keyed reading: `[data-scada-reading="field"]`; its companion gauge uses the declared bounds. An open process valve permits its flow animation; an open circuit breaker interrupts its electrical flow. Speed zero stops driven motion, while powered status indicators may remain visible. Offline, disconnected or fault states suppress production activity. Separately supplied coolant circulation, environmental wave/current motion and retained heat may continue after a production stop or fault; `running:false`, offline and reduced motion govern their animation too. The host remains responsible for deciding which state is appropriate.

Gate, control and butterfly valves support continuous `opening`: their stem or disc position and flow highlight interpolate across 0–100%. Its default is 100, preserving boolean-only callers. `open: false` overrides the rendered position and reading to 0 regardless of the supplied opening; `normalizeScadaState()` retains the supplied input position so the host can keep a separate setpoint. At opening 0, indicated flow stops. This is an illustrative aperture, not a valve flow coefficient or hydraulic calculation.

Every type also declares a `damage` select field. Read its descriptor options: vessels can leak, rupture or corrode; machines can jam, wear or overheat; electrical equipment can short, burn or overheat; instruments can drift, break or foul; automation hardware can lose communication, IO or power. New equipment adds specific membrane, blade, gearbox, refractory, diffuser and stack conditions. These produce physical visual details rather than only a label or generic warning badge. The common `fault` flag remains separate: wear or a leak may be shown while a drive is still active, whereas a jam stops the affected mechanism. Heat, spill or leak effects can continue after a drive fault. `running: false`, offline state and reduced motion freeze incident animation while retaining static evidence. These are presentation rules, not protection-system behavior.

Each `stateFields` descriptor supplies `{key, label, type, default}` plus numeric `min`, `max`, `step`, `unit`, or select `options: [{value, label}]`. Build editors from this metadata instead of assuming every component accepts every field. The catalog does this automatically. Default states are active, animated illustrations for browsing; they are not plant startup settings.

```js
const descriptor = getScadaComponent('tank');
const state = normalizeScadaState('tank', {level: 38, running: false});
// state includes the remaining declared defaults.

const markup = renderScadaComponent(descriptor.type, {
  id: 'reuse-water-tank',
  label: 'Reuse water tank',
  state,
});
```

### Rendering and accessibility

`renderScadaComponent(type, {id, label, state = {}, decorative = false, hostState = false} = {})` returns an HTML string and owns no timer or event handlers. State passes through the same strict normalization before rendering.

- `id` is an instance namespace for SVG definitions and references, not an assigned DOM `id` on the outer wrapper. Supply a unique value beginning with a letter and containing only letters, numbers, underscores or dashes, up to 100 characters. Omitting it uses a module-local generated namespace; explicit unique IDs are preferable for reusable screens or server rendering. Do not reuse an instance ID twice in one document.
- `label` supplies an accessible equipment name. The renderer escapes it and appends a current-state description. By default the wrapper has `role="img"` and `aria-label`; the internal SVG is hidden from duplicate screen-reader announcements.
- `decorative: true` hides the whole illustration from assistive technology. Use this when a surrounding native button or card already provides the equipment name and purpose. The catalog uses decorative card art and a labeled large preview.
- Put interaction in native buttons, inputs or the shared workspace component. The illustration itself is not a keyboard control. Use touch targets of at least 44 px and visible focus states.

The standalone CSS honors reduced-motion preferences and the app's `.motion-paused` class. The `running` field can pause an individual preview. Stopped decoration does not hide fault, status or level information. Animation speed, waves, glows and scan indicators are illustrative rather than measured physical rates.

## Ports, provenance and model support

Ports are data records of `{id, label, medium, direction}`. Direction is `in`, `out` or `bidirectional`. They describe useful connection roles for a diagram editor; they are not a complete hydraulic/electrical graph, fixed pixel anchors, a verified plant wiring map or a control protocol. Your layout owns routing and connection geometry.

`provenance` identifies original project SVG artwork with illustrative geometry. It is not a vendor drawing or a verified plant asset representation.

`modelSupport.kind` is either `shared-model` or `visual-only`. **Neither embeds a physics model.** `shared-model` identifies artwork reused by the documented digester twin; its description explains that the host may connect the approximate plant model. The catalog labels this **Twin artwork**. Other types, including PLC and network hardware, are visual components with no PLC execution, IO or communication model. Inspect the full descriptor rather than treating a picture as an implementation of that device.

A consuming application owns its model session, equations, clock and persistence. A live viewer reads snapshots and dispatches commands through the injected adapter described below. The reference app uses its existing twin runtime; catalog preview state is never sent to that model.

### Existing twin bridge

`hostState: true` is for the existing live twin adapter. It uses a transparent wrapper and lets the parent equipment node's state and the established twin CSS govern activity, buffer fill and incident effects. It does not install standalone inline state variables that would override the live parent. Keep the host's existing data attributes, classes and animation updates when using this mode.

Use the default `hostState: false` for standalone components and the catalog. A new application can normalize its readings and render them directly; it does not need to imitate the existing twin's presentation classes. Do not create a second model or clock inside a component renderer.

## Reference-app catalog and reuse workflow

The `#components` page supports a family filter, text search and an independent preview-motion toggle. A component opens in the reusable native `ScadaWorkspace` dialog. Its controls come from the descriptor and update only local visual state. The preview, gallery card, copied API example and exported JSON spec stay consistent. Reset restores that component's declared defaults; closing the dialog preserves its preview choices until the route is left.

The **Ports & integration** disclosure shows connection metadata, actual `renderScadaComponent` code and a component-spec download. Copy uses the browser clipboard when available and selects the code for manual copying otherwise. The kit and API guide are also downloadable from the toolbar.

A spec uses `format: "scada-component-spec"`, version 1, with `type`, instance `id`, `label`, normalized `state`, `ports`, `modelSupport` and `provenance`. It is a reusable visual configuration, not executable code or a saved plant scenario. The host should validate it with the registry before rendering imported data. The full component kit is independent of the app's separate whole-project source download.

For another equipment type, add a descriptor, unique artwork, state-specific CSS and tests for its normalization, accessible labeling and multiple-instance IDs. For another SCADA application, reuse the [workspace shell](#workspace-api), keep domain commands outside the renderer, and connect a single application session to the active view.

## Validate component states

In the full source checkout, with Python Playwright and Chromium installed, run from the repository root:

```sh
python tools/webkit/scada/ui/qa/check-component-states.py --output /tmp/scada-component-states
```

This browser check loads only the component styles and rendering dependencies. It checks every declared type for active motion, stopped motion when off/paused/offline, fault behavior, visible and accessible warning/fault cues, disconnected and open/closed paths, numeric readouts and reduced motion. It also checks multiple-instance SVG references and confirms that standalone defaults do not override the live host's buffer fill. Results are written to `/tmp/scada-component-states/component-states.json`.

The check complements visual review of equipment shapes, contrast, spacing and responsiveness; computed styles alone do not establish visual quality or complete equipment-specific state coverage. Generic warning/fault cues and the gallery state examples do not prove that every physical failure or model-to-view mapping is represented. Use the [packed consumer tests](https://github.com/Valpatel/cad-agent/blob/dev/tests/webkit/scada/ui/README.md) to verify a separate runtime distribution.

## Workspace API

The component shell is available from the package entry or `@valpatel/scada-ui/workspace`:

```js
import {
  ScadaWorkspace, renderScadaDialog, renderScadaToolbar,
} from '@valpatel/scada-ui/workspace';

const root = document.querySelector('#workspace');
root.classList.add('scada-workspace');
root.innerHTML = renderScadaToolbar({
  label: 'Equipment tools',
  content: '<button class="scada-toolbutton" data-scada-open="equipment">Inspect pump</button>',
}) + renderScadaDialog({
  id: 'equipment', scope: 'north-line', title: 'Feed pump',
  subtitle: 'Equipment state supplied by your application',
  kind: 'equipment', body: '<p>Place your labeled readings and controls here.</p>',
});
const workspace = new ScadaWorkspace(root);
// Later, before removing the root:
// workspace.destroy();
```

The root may be a neutral container; no `#main` ID is required. `renderScadaToolbar({label, content})` wraps trusted control markup. `renderScadaDialog({id, title, subtitle='', body='', kind='panel', footer='', scope='scada'})` creates a native dialog with a fixed header, close control and scrolling body. `kind` accepts `panel`, `equipment` or `wide`.

`id` and `scope` form distinct dialog and heading IDs. Use a unique scope for simultaneous workspaces. Title/subtitle strings are escaped; `body`, `footer` and toolbar `content` are trusted application markup, not sanitized user HTML.

| Method / property | Contract |
| --- | --- |
| `new ScadaWorkspace(root, {onOpen, onClose})` | Attaches delegated dialog/focus handlers to an existing root. `onOpen` receives `{id, dialog}`; `onClose` receives `{id, dialog, reason}`. |
| `open(id, {opener, focus})` | Opens the named dialog in the native top layer. `focus` may be an element or selector inside the dialog. Returns whether opening succeeded. |
| `close({restoreFocus=true, reason='close'} = {})` | Closes the active dialog, releases document scroll locking and normally restores the opener's focus. |
| `activeId`, `activeDialog` | Read the current logical ID/dialog or `null`. |
| `destroy()` | Closes without returning focus to a removed view and removes all owned handlers. |

`data-scada-open="id"` triggers a panel and `data-scada-close` closes it. Escape and backdrop dismissal use the same cleanup. The shell synchronizes dialog ARIA state and contains keyboard focus. Native top-layer behavior is the browser acceptance target; the non-native fallback also permits DOM tests.

The stylesheet includes `.scada-toolbutton` variants, `.scada-toolbadge`, `.scada-panel-grid`, `.scada-panel-section`, `.scada-actions`, `.scada-metric-strip` and `.scada-statusbar`. These are CSS/markup primitives, not additional JavaScript factories. See their thumbnails in the [README](../README.md#workspace-primitives).

## Viewer API

`ScadaViewer` combines the renderer and workspace shell around an external model adapter. Import it from the public entry or `@valpatel/scada-ui/viewer`. A portable `definition` is validated with the [versioned system contract](./SYSTEM_FORMAT.md); trusted host code may instead supply `equipment`, `views`, `controls` and rendering hooks directly. Functions/hooks are never part of imported JSON.

```js
import {ScadaViewer, validateSystemDefinition} from '@valpatel/scada-ui';

export function mountSystem(root, definition, adapter) {
  const result = validateSystemDefinition(definition);
  if (!result.ok) throw new Error(result.errors.map(error => error.message).join('\n'));
  const viewer = new ScadaViewer({definition: result.definition, adapter});
  viewer.mount(root);
  return viewer;
}
```

### Adapter ownership

| Member | Required behavior |
| --- | --- |
| `getSnapshot()` | Returns the current application snapshot. The viewer reads it initially and again after notifications or refresh. Supply plain data for JSON Pointer bindings. |
| `subscribe(listener)` | Registers updates and returns an unsubscribe function. The viewer rereads `getSnapshot()`; it does not require the notification itself to contain the full state. |
| `dispatch(command)` | Optional external command implementation. May return a result or Promise. Without it, the viewer is read-only and command controls are disabled. The host validates and executes domain commands. |

The viewer does not own a timer, a physical model, persistence or network IO. Use the same adapter/session for multiple layouts or simultaneous viewers. Destroying or remounting a presentation must not destroy or reset that session.

For schema-defined controls, the viewer looks up the declared command object and passes it to `adapter.dispatch`. Value controls add `arguments.value` while preserving other declared arguments. Action strings are identifiers for the host, not executable expressions. The host decides what an action means, enforces domain constraints and emits an updated snapshot. Missing readings produce an unavailable/offline presentation and diagnostics instead of a fabricated normal measurement; see [SYSTEM_FORMAT.md](./SYSTEM_FORMAT.md) for exact binding behavior.

### Construction and lifecycle

`new ScadaViewer({definition, adapter, initialView, selected, zoom, scope, hooks, ...presentationOptions})` uses the first view/equipment and an automatically distinct scope. The managed viewer fits its layout on mount; an explicit constructor `zoom` or pre-mount `setZoom()` starts at that scale instead. Unmounted markup starts at zoom 1. Unknown view/equipment IDs and unsupported zoom values are rejected. Trusted host presentation options may provide `equipment`, `views`, `controls`, `system`, `renderNode`, `renderInspector`, `renderShell` and diagram callbacks instead of the portable definition.

| Method / property | Behavior |
| --- | --- |
| `mount(root, {render=true, bindEvents=true, workspace=true} = {})` | Mounts or attaches the viewer and subscribes to the adapter. The normal mode renders view tabs, picker, zoom, equipment and native inspector. |
| `setView(id)` | Changes the active layout, fits its geometry and closes its inspector. External state/time remain unchanged. |
| `select(id, {open=false, opener})` | Selects canonical equipment and optionally opens its inspector. |
| `setZoom(value)` | Sets a finite scale from 0.05 to 3 around the viewport center. |
| `fit()` | Fits the complete layout below the pinned recovery control; very large layouts may fit below 0.05. |
| `openInspector({opener})`, `closeInspector()` | Uses the shared modal lifecycle for the current selection. |
| `dispatch(command)` | Passes a command to the adapter, refreshes when needed and reports failures. Throws when read-only. |
| `refresh(reason='refresh', event=null)` | Reads the current snapshot and patches the presentation. |
| `render()` | Returns the current viewer markup for trusted host composition. |
| `destroy()` | Unsubscribes, removes owned DOM listeners, destroys the camera and destroys owned dialogs. Leaves the model/adapter/clock intact. |
| `snapshot`, `view`, `selected`, `zoom`, `root`, `workspace`, `camera`, `readOnly`, `equipment`, `views` | Read current presentation context. |

Snapshot updates preserve the camera transform, focused input drafts, screen-space recovery controls and open dialogs. View changes update selection/layout context without invoking a plant reset. A custom host rendering hook is responsible for retaining those same interaction guarantees.

### Integrating existing markup

`mount(root, {render:false, bindEvents:false, workspace:false})` attaches selection/subscription management to a host that already owns its DOM, handlers and workspace. Hooks receive these objects: `update({snapshot,event,viewer,reason})`, `selectionChange({id,viewer})`, `viewChange({id,viewer})`, `zoomChange({zoom,viewer})`, `openInspector({id,opener,viewer})` and `closeInspector({viewer})`. The host must forward its controls deliberately and clean up its own handlers/modal shell. This attachment mode creates no camera; the host can mount `ScadaCamera` around its own diagram world.

`renderScadaDiagram({view, equipment, snapshot, selected, zoom, scope, renderNode, ...callbacks})` is the lower-level geometry renderer. It requires `renderNode` and returns bounded viewport/stage/canvas markup (the historical `data-scada-scroll` attribute remains compatible) with equipment, routed edges, labels, junctions and ports. Other hooks include `renderEdge`, `renderEdges`, `renderBackground`, `renderLabel`, `renderJunction`, `renderPort` and `renderOverlay`, plus class/attribute overrides. Callback output is trusted HTML/SVG. The helper itself creates no event handlers, subscriptions or model state.

`normalizeViewerDefinition(input)` validates a portable definition and translates it into the viewer's equipment/view/control registry. Invalid definitions throw a `TypeError` with validation details. Use `validateSystemDefinition()` directly when an editor needs structured `{path, code, message}` errors instead.

### Reusable 2D camera

`ScadaCamera` is exported from the main entry and `/viewer`. Its implementation in `src/viewer/camera.mjs` depends only on DOM APIs; it does not read a system definition, subscribe to a model, run a simulation clock or control 3D engines. Import the viewer stylesheet for the viewport and pinned control appearance.

```js
import {ScadaCamera} from '@valpatel/scada-ui/viewer';
import '@valpatel/scada-ui/viewer.css';

const camera = new ScadaCamera({
  viewport: root.querySelector('[data-scada-scroll]'),
  canvas: root.querySelector('[data-scada-canvas]'),
  width: 1800,
  height: 1000,
  onChange(state, reason) { saveViewPreferences(state); },
});
// After a host patches existing world markup, reapply the same camera:
camera.refresh();
// When removing this view:
camera.destroy();
```

The viewport must have a bounded CSS width and height. `.scada-diagram-scroll` supplies a responsive height that hosts can override with `--scada-viewport-height`. The world keeps its fixed logical dimensions. `canvas` defaults to the viewport's `[data-scada-canvas]`; `width` and `height` may come from its `data-scada-width` / `data-scada-height` attributes emitted by `renderScadaDiagram`. A direct child world works without a stage. An optional `stage` must sit between viewport and canvas; the renderer's `[data-scada-stage]` is detected automatically and sized to the viewport.

| Camera member | Behavior |
| --- | --- |
| `new ScadaCamera({viewport, canvas, stage, width, height, fitOnMount=true, state, onChange})` | Owns camera events, a ResizeObserver when available, and a pinned **Zoom to fit** button outside the transformed world. Optional saved `state` takes precedence over `fitOnMount`. |
| `state` | Returns a copy of `{x, y, zoom, fitted}`. Offsets are CSS pixels in viewport coordinates; world transform is `translate(xpx, ypx) scale(zoom)`. |
| `fit()` | Fits the complete world at up to 100%, reserving a 64px top strip for the button and 12px other edge gaps. |
| `setZoom(zoom, {x,y}?)`, `zoomBy(factor, {x,y}?)` | Keeps the world point beneath the supplied viewport-local anchor fixed. The default anchor is the viewport center. Positive zoom is clamped to 3 and to the smaller of 0.05 or the fitted scale; huge layouts therefore zoom smoothly from their overview. |
| `panBy(dx,dy)` | Moves the world by CSS pixels; leaves fit mode. |
| `setState({x,y,zoom,fitted})` | Restores finite presentation offsets and a positive scale up to 3. Persist this per view in host preferences, separately from physical state. |
| `setSize(width,height,{fit=false})` | Changes logical world dimensions. Use `fit:true` when switching to different geometry. |
| `refresh()` | Reapplies camera-owned styles after a DOM patch. A resized fitted viewport refits; a manual viewport preserves the world point at its center. Zero-size hidden mounts wait for usable dimensions. |
| `viewport`, `canvas` | References to the owned viewport and world elements. |
| `destroy()` | Removes listeners, observer and pinned control, releases captures and restores owned inline styles/attributes. Repeated destruction is safe. Failed initial callbacks also roll back owned resources. |

Mouse drag and one-finger touch pan; the wheel and two-finger pinch zoom around their pointer/midpoint. Movement below the drag threshold preserves equipment activation. A completed drag suppresses its synthetic pointer click, while keyboard activation still works. Arrow keys pan, `+` / `-` zoom, and `Home` or `F` fit when focus is within the viewport. Editable fields retain their own key handling. Tab focus on offscreen equipment pans it into the visible area below the recovery control. The camera uses `overflow:clip` and no internal scrollbars; wheel events outside the viewport, ordinary document scrolling and inspector form scrolling remain normal.

`onChange(state, reason)` reports `resize`, `fit`, `zoom`, `pan` or `restore`; it is a presentation notification, not a model command. Hosts that replace a viewport must destroy its old camera before creating another, optionally passing the saved state. Hosts that patch children should preserve `[data-scada-camera-controls]` to retain focus on the pinned button. `refresh()` reattaches that control if a host removed it. Stable observation selectors are `[data-scada-camera]`, `data-camera-x`, `data-camera-y`, `data-camera-zoom` and `data-camera-fitted`; the pinned button uses `[data-scada-camera-fit]`. The existing toolbar keeps its separate `[data-scada-zoom="fit"]` selector.

## Versioned system data

The public system exports are `SYSTEM_DEFINITION_VERSION`, `validateSystemDefinition`, `resolveBinding` and `resolveComponentState`, available from the main entry or `/system-definition`. The JSON Schema is exported as `/schema`. The canonical details and examples are maintained in [SYSTEM_FORMAT.md](./SYSTEM_FORMAT.md); do not copy a competing schema into a consumer or invent an undocumented binding syntax.

The definition has `format: "scada-system"` and `version: 1`. Validation returns either `{ok:true, definition}` with normalized frozen data or `{ok:false, errors}`. Bindings use JSON Pointer paths, never JavaScript expressions. `resolveBinding(snapshot, pointer)` returns a found value or a structured error. `resolveComponentState(instance, snapshot)` applies declared state/bindings and returns normalized state plus diagnostics. This resolves presentation data only; it does not create equipment behavior or communicate with a controller.
