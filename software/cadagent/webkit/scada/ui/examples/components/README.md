# Single-component browser example

[Examples map](../README.md) · [Package map](../../README.md) · [Component API](../../docs/API.md) · [Catalog owner](../../src/catalog/README.md)

[index.html](./index.html) is a self-contained example page with its small host controls and module script inline. It imports the public component/catalog facades and component stylesheet. Search and family filters choose a descriptor; variant selection preserves the type identity; Active, Animate and Fault supply visual state to the same renderer used elsewhere.

```mermaid
flowchart LR
  search[Search and family filters] --> discovery[Pure discovery API]
  discovery --> selection[Type and variant selection]
  selection --> state[Explicit visual inputs]
  state --> render[renderScadaComponent]
  render --> preview[Preview and copyable API snippet]
```

Run `python -m http.server 8000` from the package root and open `http://localhost:8000/examples/components/`. The displayed code follows the current selection. The example deliberately exposes only a few common controls; the authoritative full field/port list comes from the descriptor, [API](../../docs/API.md) and [state coverage review](../../docs/STATE_COVERAGE.md).

There is no model, plant session or command adapter here. Changing a checkbox changes a local illustration. Use the [viewer example](../viewer/README.md) to connect system-level state and commands. Extend this example without importing the host app or adding timers to the symbol library.

<a href="../../img/symbols/automation/plc-rack.svg"><img src="../../img/symbols/automation/plc-rack.svg" width="210" alt="Animated PLC rack example asset"></a>
<a href="../../img/symbols/power/solar-panel.svg"><img src="../../img/symbols/power/solar-panel.svg" width="210" alt="Animated solar panel example asset"></a>
