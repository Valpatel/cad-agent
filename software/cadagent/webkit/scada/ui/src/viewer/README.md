# Diagram view and controller

[Source map](../README.md) · [Package map](../../README.md) · [Viewer API](../../docs/API.md#viewer-api) · [Runnable example](../../examples/viewer/README.md)

```mermaid
flowchart TD
  Session["External adapter"] --> Controller["ScadaViewer"]
  Document["System document"] --> Controller
  Controller --> Diagram["Diagram renderer"]
  Controller --> Quick["Quick controls"]
  Quick --> Details["Full details / host"]
  Controller --> Camera["ScadaCamera"]
  Diagram --> Symbols["Symbols"]
  Host["Host diagram"] --> Camera
```

`viewer.mjs` and `viewer.css` own diagram layout, equipment context, zoom, inspection and command dispatch. `renderScadaDiagram` is presentation; `ScadaViewer` is the adapter-driven controller. The external adapter owns snapshots, subscriptions and optional command execution. Several views can share that adapter. Switching or destroying a view must never reset the external model, and rendering motion is separate from simulation time.

Equipment buttons show canonical IDs and names without a persistent selection
fill or toggle semantics. `openInspector()` opens a nonmodal, screen-space
`ScadaPopover` anchored to that equipment. It follows the camera and shows only
equipment-scoped controls and compact readings. `openDetails()` uses the full
native inspector or the host's `onDetails` callback. Both levels keep the same
equipment identity and adapter; changing IDs closes the old inspection context,
while ordinary ticks preserve focused drafts.

<a href="../../img/thumbnails/workspace/generic-viewer.jpg"><img src="../../img/thumbnails/workspace/generic-viewer.jpg" width="680" alt="Shared SCADA viewer with contained diagram and equipment controls"></a>

Declared toggle controls can opt into one direct equipment action through
`control.diagram` ([format](../../docs/SYSTEM_FORMAT.md#commands-and-controls)).
The action is a separate native button beside the inspector button and dispatches
through the same adapter. It follows the bound switch state, never inferred flow,
and stays absent in read-only views. No plant-specific commands live here.

| Source | Ownership |
| --- | --- |
| [viewer.mjs](./viewer.mjs) | Pure diagram geometry renderer and adapter-driven selection, inspection and command controller. Public camera re-export. |
| [process-layout.mjs](./process-layout.mjs) | Pure, opt-in process-chain geometry projection. Retains identities and declared ports; complex authored diagrams are left intact. |
| [camera.mjs](./camera.mjs) | DOM-only 2D pan/zoom, fit, pointer/touch/keyboard navigation, one screen-space zoom/reset/Fit toolbar and resize/lifecycle cleanup. No imports or model dependencies. |
| [viewer.css](./viewer.css) | Bounded viewport, diagram appearance and camera controls; imports workspace/popover styles. Ordinary page and inspector scrolling remain available. |

The default `ScadaViewer` mounts a camera and preserves its transform across snapshot patches. Host attachment with `render:false` leaves camera ownership to the host. `ScadaCamera` also accepts a direct world element without renderer markup, so reference drawings and simulator layouts share interaction behavior without sharing a physical model. Keep camera state in presentation preferences; never use pan/zoom to mutate equipment or simulation state. See the [camera contract](../../docs/API.md#reusable-2d-camera) for methods and lifecycle guarantees.

The child dependencies have their own maps: [symbols](../symbols/README.md), [workspace](../workspace/README.md) and [system contracts](../contracts/README.md). The viewer accepts a validated document and adapter, not a URL to a plant or a hidden model constructor. Missing readings stay diagnosable; read-only adapters omit command dispatch.
