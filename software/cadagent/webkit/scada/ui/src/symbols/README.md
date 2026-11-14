# Equipment symbol rendering

[Source map](../README.md) · [Package map](../../README.md) · [Style guide](../../STYLE_GUIDE.md) · [Gallery](../../img/README.md)

| Owner | Responsibility |
| --- | --- |
| [components.mjs](./components.mjs) | Normalize supplied visual state, choose artwork and compose escaped accessible markup, gauges and condition cues. |
| [components.css](./components.css) | Standalone skin, shared state gates and imports of family animation styles. |
| [art/](./art/README.md) | Process, manufacturing, controls, agriculture and legacy twin geometry. |
| [power/](./power/README.md) | Energy, electrical, generator and conceptual nuclear geometry. |

```mermaid
flowchart TD
  State["Visual state"] --> Components["components.mjs"]
  Components --> Catalog["Catalog validation"]
  Components --> Art["art/ + power/"]
  Components --> Markup["SVG + gauges<br/>+ description"]
  Skin["Family CSS"] --> Markup
  Catalog ~~~ Markup
  Art ~~~ Markup
```

Render functions own no model clock, network, audio, repair latch or accident scheduler. Preserve instance-local SVG IDs, escaping, declared fields and the documented `hostState` bridge. Production, observation, retained conditions and fault effects need separate gates; a global stop must not silently erase supplied inventory or heat.

[State coverage](../../docs/STATE_COVERAGE.md) records what has actually been checked and what remains incomplete. Use [the single-component example](../../examples/components/README.md) for integration and the package-owned gallery for review. Add geometry here rather than editing generated SVG/JPEG previews.

<a href="../../img/symbols/rotating/submersible-pump/default.svg"><img src="../../img/symbols/rotating/submersible-pump/default.svg" width="200" alt="Submersible pump symbol"></a>
<a href="../../img/symbols/power/solar-panel/default.svg"><img src="../../img/symbols/power/solar-panel/default.svg" width="200" alt="Solar panel symbol"></a>

## Files

| File | Purpose |
| --- | --- |
| [index.mjs](index.mjs) | Public aggregate exports for this owner. |
