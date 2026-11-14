# SCADA architecture and source map

The runtime is divided by responsibility, with ordinary ES modules and explicit
adapters. A browser viewer does not own a second solver, and a model does not
import the DOM, artwork, audio or hosting.

| Owner | Responsibility |
| --- | --- |
| `software/cadagent/webkit/scada/ui/` | Equipment descriptors and SVG states, system validation, viewer/controller, workspace controls, styles and image gallery |
| `software/cadagent/webkit/scada/sim/` | Headless v1/v2 engines, equations, model/snapshot validation, adapters, scenarios and image gallery |
| `software/cadagent/webkit/scada/explorer/` | Scenario loading, session/clock lifetime, persistence, audio, commands and example host interface |
| `tools/webkit/scada/` | Schema/metadata, gallery, topology, scenario documentation and capture producers |
| `tests/webkit/scada/` | UI/model/adapter/scenario and browser regression evidence |
| `.agents/skills/scada-*/` | Repeatable authoring, model replacement, visual review and consumer verification |

Each owner has a README leading to its files, child domains and related tools.
API and format guides stay beside their libraries so a source extraction has its
explanation. User workflows live here. Generated assets have one producer; site
publication is a projection, not another source tree to patch.

## Documents and sessions

| Artifact | Meaning |
| --- | --- |
| `scada-system` v1 JSON | Stable equipment/port identities, explicit connections, layouts, snapshot bindings and declared controls |
| `scada-placeholder-model` v1 or v2 JSON | Engine selection, parameter data, assumptions, circuits, finite resources and model bindings |
| Versioned snapshot | Saved engine state, clock/random state and validated provider-owned state |
| View state | Selected layout/equipment and camera; not model state |

Use the [system format](../../../software/cadagent/webkit/scada/ui/docs/SYSTEM_FORMAT.md)
and [model API](../../../software/cadagent/webkit/scada/sim/docs/MODEL-API.md) as the
canonical contracts. JSON Schema validates shape; runtime validators additionally
check references, bindings, topology and compatible versions. Layout proximity
never creates a process, electrical or review relationship.

The host creates one model and one clock. `ScadaViewer` consumes `getSnapshot()`,
`subscribe(listener)` returning unsubscribe, and optional `dispatch(command)`.
Multiple layouts/observers borrow that same model. Destroying a presentation must
not advance, reset or destroy the session. Both v1 and v2 read-only adapters omit
`dispatch`, so viewers expose commands only when the adapter supports them.

## Replace equations or the complete engine

The model library implements two replacement seams today:

- Trusted `equationProviders` select supported constitutive laws and owned state
  through data-only bindings. Pure evaluation can repeat during solving; state
  advances once per accepted substep. Binding swaps preserve core time/stocks and
  reset provider-owned state. Invalid swaps/restores roll back atomically.
- A whole external solver can implement the viewer adapter without adopting the
  example kernel. It explicitly maps equipment IDs, units, time, data quality,
  commands, authority and restart support.

See [real model adaptation](../../../software/cadagent/webkit/scada/sim/docs/REAL_MODEL_ADAPTATION.md),
[physical equation examples](../../../software/cadagent/webkit/scada/sim/examples/equation-models/README.md)
and the [switching bench](../../../software/cadagent/webkit/scada/sim/examples/model-switching/README.md).
V1 normalized inventory uses rate × minutes / 10; v2 uses rate × minutes. Preserve
those explicit bridges when using SI helper equations. Local pump/heater equations
and attractive animation do not establish a qualified full hydraulic network.

## Extending shared workbenches

Keep imports pointed at their canonical source owner and publish from that owner. Runtime packages, host applications and maintenance tools have separate lifecycles and distribution scopes.

Shared controls, asset loading, lifecycle and selection can serve multiple domains
when actual consumers prove the abstraction. SCADA remains 2D/process-oriented;
mechanical cameras, PCB layers/nets and harness pin/mating-face identities keep
their own contracts. Future toolkits should follow the same source/tool/test/skill
boundaries, with their own integral galleries and measured acceptance evidence.
Do not pre-create empty folders or claim a new parser/viewer exists from its plan.

[Guide map](README.md) · [Resources and growth](resources-and-growth.md)
