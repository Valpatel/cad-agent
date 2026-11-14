# Prompts for future agents

Use the [state coverage review](./docs/STATE_COVERAGE.md) to select real gaps. Each
addition needs an explicit state/transition table and failure→repair evidence;
shared badges, a default thumbnail or a registered placeholder model do not prove
complete behavior. Keep unsupported dynamics visible in the review.

Replace the bracketed fields before using a prompt. These prompts assume a checkout of this repository. Read [the API](./docs/API.md) and [system-format contract](./docs/SYSTEM_FORMAT.md) for actual exports, bindings and adapter behavior; do not infer contracts from a screenshot. For a copied package, adapt the host-specific build/test commands after reading `CONTRIBUTING.md`. They do not authorize a public package publication or Site deployment.

## Add an equipment component

```text
Add a reusable [equipment name] component with stable type ID [type-id] in
software/cadagent/webkit/scada/ui. Read software/cadagent/webkit/scada/ui/README.md, STYLE_GUIDE.md,
CONTRIBUTING.md and AGENTS.md first, plus the system-format contract if the
component will appear in a system definition.

Edit canonical src/ files, not generated dist copies. Study neighboring
components and create a recognizable original silhouette in the existing
glass/steel/teal style. Declare typed state fields, defaults, bounds, units,
ports and honest provenance/modelSupport metadata. Keep it visual-only unless
an actual external model adapter is part of this task. Renderers must not start
timers, model sessions or network/PLC IO. Preserve unique instance IDs and
accessible labels; make warning/fault/offline states meaningful without motion.

Add focused behavior/validation tests, run npm --prefix tools/webkit/scada run build:metadata and the relevant
scada Node suites, then inspect real Chromium renders at card, modal and system
sizes, including reduced motion and applicable inactive/fault/open states.
Regenerate thumbnails with npm --prefix tools/webkit/scada run thumbnails, update the
README family table and metadata, and verify package imports/build freshness.
Report the actual checks and images inspected. Do not publish or deploy.
```

## Add an equipment family

```text
Add the [family name] family to software/cadagent/webkit/scada/ui with these types: [type list].
First read README.md, STYLE_GUIDE.md, CONTRIBUTING.md, AGENTS.md and the existing
registry. Plan distinct silhouettes and declared state/port semantics for each
type; avoid reusing one generic box under several names.

Keep shared SVG helpers and styles reusable, scoped and compatible with existing
types. Do not imply process physics, PLC execution or verified plant assets.
Update category metadata and public documentation from the real registry.
Preserve type IDs, instance-ID isolation and the external model/clock boundary.

Test all new state behavior and invalid inputs, sync generated app copies, render
the new family in normal and exceptional states, and inspect desktop/phone sizes.
Regenerate every affected thumbnail/contact-sheet/manifest entry and add the
family's thumbnail table to README.md. Run package/export checks and report the
results without claiming unperformed visual checks or publication.
```

## Add or change a visual state

```text
Add [state field] to [component types] in software/cadagent/webkit/scada/ui. Read the package
README, style guide, contributing guide, current normalizer and public system
binding contract before editing. Define its exact visual semantics, type,
default, bounds/options and units. Explain how it combines with active, running,
fault, warning, offline, connected, open and type-specific damage states; do not turn visual state into
an independent equipment model.

Update declared metadata, normalization, accessible descriptions, geometry/CSS
and binding examples where relevant. Keep existing consumers compatible or make
a deliberate versioned migration. Do not execute expression strings or silently
accept unknown keys. Preserve live hostState behavior and multi-view shared state.

Test normal/boundary/invalid values and combinations, inspect real animation
start/stop and reduced motion, sync generated copies, regenerate affected
thumbnails/state exemplars and update the API/style docs. Report checks and any
remaining limitation. Do not publish or deploy.
```

## Review visuals and regenerate thumbnails

```text
Review [types/family/all components] in software/cadagent/webkit/scada/ui. Read README.md,
STYLE_GUIDE.md and CONTRIBUTING.md, then verify generated assets with the library
build/check command. Use the actual renderer, public state metadata and real
Chromium, not replacement illustrations.

Inspect silhouettes, contrast, labels, state symbols, ports, gauge clearance and
animation at small-card, large-preview and system-view sizes. Check inactive,
paused, warning, fault, offline, disconnected/open states, every declared damage
option and numeric low/middle/high endpoints
where declared. Verify reduced motion and keyboard/modal focus. If multiple
system views are involved, confirm that they observe one external model session
and that navigation does not reset readings, commands or incident state.

Fix only demonstrated issues in canonical source. Run affected tests, regenerate
thumbnails using npm --prefix tools/webkit/scada run thumbnails and inspect the contact
sheet plus representative individual files. Check metadata/thumbnails.json and
README links against all declared types and UI primitives. Report evidence paths
and actual results; do not claim that static thumbnails prove animation behavior.
```

## Integrate into another repository

```text
Integrate the private local @valpatel/scada-ui package into [repository/app].
Read the package README, STYLE_GUIDE.md, CONTRIBUTING.md, current viewer API and
versioned system-format/binding documentation. Use actual public exports and a
local file dependency or packed tarball; do not assume it is published to npm or
that a new open-source license has been granted.

Create a validated system definition for [equipment/views]. Keep one canonical
model/adapter and clock outside the UI package. Map explicit state paths and
commands through the documented adapter. Different layouts must observe that
same session; a second view must not create a second model or reset time/history.
Keep presentation-only previews separate from command-enabled equipment.

Load the complete CSS dependency chain, supply unique IDs and accessible labels,
and use the shared viewer/workspace lifecycle. Preserve focused controls while
updates arrive and destroy view subscriptions/dialogs on teardown. Do not add
PLC/network access or physical validity claims unless separately requested and
implemented.

Run schema/binding and interaction tests in the target app; verify initial state,
updates, commands, two-view continuity, invalid definitions, teardown, keyboard
operation, reduced motion and responsive layout in a real browser. Generate
updated thumbnails only if component visuals changed. Document the adapter and
report actual checks, dependencies and limitations. Do not publish or deploy.
```

## Connect a CAD frontend or another renderer

```text
Connect [CAD/frontend] to the reusable SCADA system and simulation packages.
Use the versioned system definition for component identity, ports, controls,
bindings and named views. Keep the headless model session independent of SVG,
DOM, screenshots and framework components. Do not duplicate its state or clock.

For every mapped symbol, preserve its declared numeric units/ranges and damage
enum. Subscribe to the same normalized snapshot used by the browser viewer and
dispatch explicit typed commands through the adapter. Separate physical model
outputs from presentation choices such as paused decoration. Replace placeholder
equations only behind that boundary and document assumptions/calibration status.

Test consistent identity and readings across at least two frontends, including
off/on, low/middle/high values, faults, each supported damage state, repair and
snapshot import/export. Verify that removing one frontend does not stop or reset
the shared model. Report exact mappings, unsupported visuals and checks run.
```

## Select a variant or author a researched power/agriculture view

```text
Read the package API, system format, style guide and POWER_REFERENCES /
AGRICULTURE_REFERENCES. Use findScadaComponents and getScadaFacets to locate
existing equipment by role, technology, medium and application. Resolve the
chosen type/variant before authoring endpoint ports; never reinterpret a gas
fuel inlet as a shaft or liquid-fuel feed.

Use one canonical equipment graph and several layouts over the same external
model adapter. Keep exchanger and reactor circuits isolated, with explicit model
thermal relationships instead of material connections across boundaries. Keep
AC, DC, mechanical, optical and fluid resources explicit. A fuel or enclosure
variant does not establish capacity, efficiency or material compatibility.

Read primary references for structural distinctions and record what was actually
inspected. Label invented tags, coordinates, numerical defaults and dynamics as
editable illustrative assumptions. Do not import operating procedures, protection
settings, neutronics or calibrated crop/radiation readings into a toy model.

Check every applicable numeric state, direction, source selection, damage mode,
validity condition and animation gate. Production, residual heat, independent
circulation and environmental motion require separate gates. Run shared-view,
port/variant/schema, save/restore and real-browser checks. Regenerate affected
preview assets and update metadata/docs only after the source is stable.
```

## Add or revise a gallery asset

```text
Read this package's AGENTS.md, STYLE_GUIDE.md and docs/GALLERY_EXPORT.md.
Change canonical descriptors/artwork, never a generated SVG or JPEG. Preserve
instance IDs, accessible state descriptions and reduced motion. Keep this
library's gallery under img/; another library gets its own img/ owner.

Confirm every new type/variant appears in the generated family index. Add a
representative comparison to tools/webkit/scada/ui/gallery/samples.json when a new state
needs explanation; do not create a private process model or animation clock.
Run gallery:generate, gallery:check and qa:gallery from the workspace root,
then regenerate/check static thumbnails. Inspect card labels, gauge clearance,
active/fault/damage and reduced-motion image captures. Verify package allowlists
and relative Markdown links. Report actual image-mode and GitHub verification
separately; a raw SVG test is not proof of GitHub README animation.
```

## Review an equipment drawing before regeneration

```text
Inspect the individual equipment at card, inspector and diagram sizes. Trace
every line: it must connect to a meaningful port, handle, cable, actuator or
have a clear schematic purpose. Remove unexplained floating geometry. Follow
material paths with consistent distinct colors and, where needed, short labels
or directional arrows. Preserve recognizable function: conveyor oven versus
rack/batch oven, pump versus generator, and each technology's actual role.

Exercise inactive, active, low/high numeric, warning and relevant damage states.
Motion must follow supplied state and remain legible with reduced motion.
Inspect the device itself; a full-gallery contact sheet alone is insufficient.
Then regenerate SVG/JPEG previews and verify their source-derived manifests.
```
