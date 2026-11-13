# SCADA simulation lab

Cad-agent's native browser host for the shared SCADA viewer and headless simulation library.

The arrows describe actual imports and data reads. The application creates one
model session; its main viewer and optional read-only observer subscribe to that
same model. Neither viewer owns the simulation clock.

```mermaid
flowchart TD
  D["sim/scenarios/<br/>system and model JSON"] --> H["main.mjs<br/>session and controls"]
  H --> M["sim/src/<br/>headless model"]
  M --> V["ui/src/<br/>shared viewer"]
  H --> S["sound.mjs<br/>optional audio"]
  V --> O["Main view and<br/>read-only observer"]
  classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
  classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
  class H,S here
  class D,M,V near
```

| File | Responsibility |
| --- | --- |
| [index.html](index.html), [styles.css](styles.css) | Accessible standalone workspace and Toolkit navigation |
| [main.mjs](main.mjs) | Scenario loading, one clock, command dispatch, shared observer and session persistence |
| [model-editor.mjs](model-editor.mjs) | Editable v2 circuit, energy and environmental assumptions |
| [selection.mjs](selection.mjs) | Explicit scenario/type/variant deep-link resolution |
| [search.mjs](search.mjs) | Catalog search and composable industry/technology/facility filters |
| [sound.mjs](sound.mjs) | Opt-in browser audio and deduplicated current-state alarms |

The public entry is `/kit/scada/explorer/index.html?scenario=wastewater-digester`.
A source checkout can serve this folder over HTTP(S) with its sibling `ui/` and
`sim/` libraries. No build step, external API, remote source repository or plant
workbook is needed at runtime.

The default wastewater example connects treatment, sludge digestion, biogas
conditioning, a generator, flare and electrical loads. **Water treatment**,
**Sludge & biogas** and **Power & control** are layouts of the same equipment and
state. All process values are editable normalized estimates. This example does
not model biological removal, methane stoichiometry, hydraulic design, electrical
protection or treatment-quality acceptance.

Use **Fault lab** to inject failures, **Model & guesses** to edit declared
parameters, and **Session** to save/restore state or open the read-only observer.
The observer has its own camera and layout but no process-command capability.
Closing it removes its viewer subscription; the original session continues.
Reset preserves parameter edits, while choosing another scenario loads that
scenario's initial configuration. One simulation minute advances per timer tick
at 1×; the clock suspends while the document is hidden. Audio starts disabled
and remains silent when the model is paused or the document is hidden.

Drag/pinch/wheel moves the camera inside a scrollbar-free viewport. **Zoom to fit**
recovers the whole diagram. Normal document and long-inspector scrolling remains
available. Equipment inspectors keep their text readable independently of diagram
zoom. Keyboard focus, reduced motion and optional sound use the library's controls.

The bundled pump/heater equation providers support compatible saved sessions.
The linked equation bench demonstrates live law replacement; the ordinary
parameter form is not a generic provider editor. Complete external solvers can
implement the same snapshot/subscription/command adapter without using the
placeholder kernel.

[SCADA owner](../README.md) · [UI library](../ui/README.md) ·
[Simulation library](../sim/README.md) ·
[Model/API contract](../sim/docs/MODEL-API.md) ·
[Explorer tests](../../../../../tests/webkit/scada/explorer/README.md)
