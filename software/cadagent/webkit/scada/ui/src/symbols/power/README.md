# Energy, electrical and nuclear artwork

[Symbol map](../README.md) · [Source map](../../README.md) · [Package map](../../../README.md) · [Power references](../../../docs/POWER_REFERENCES.md)

| Source | Owns |
| --- | --- |
| [energy.mjs](./energy.mjs) | Prime movers, thermal/hydro/solar/marine equipment and supplied transport layers. |
| [electrical.mjs](./electrical.mjs) | Converters, contacts, instrument transformers, relay and substation forms. |
| [generators.mjs](./generators.mjs) | Explicit genset technology/enclosure variants. |
| [nuclear.mjs](./nuclear.mjs) | Conceptual nuclear vessels, circuits, rods and monitoring. |
| [primitives.mjs](./primitives.mjs) | Shared original geometry, materials and detail helpers. |
| [power.css](./power.css) / [nuclear.css](./nuclear.css) | Scoped motion, state gates and static/reduced-motion presentations. |
| [map.svg](./map.svg) | Compact source map of renderer imports and shared geometry ownership. |

The arrows show artwork imports from the parent renderer; the footer names the shared helper's consumers.

![Power artwork source map](./map.svg)

Technology, circuit and fuel descriptors belong in [power metadata](../../catalog/definitions/power.mjs). The artwork receives state; it does not decide protection trips, solve electrical networks or simulate reactor dynamics. Keep source production, external circulation, retained heat and telemetry validity separate. A fault label does not imply a successful protective action.

[State coverage](../../../docs/STATE_COVERAGE.md) records verified distinctions and open design/model limitations. Nuclear drawings use fictional illustrative readings and original schematic geometry; reference notes do not make them validated safety or design models.

<a href="../../../img/symbols/power/solar-panel/default.svg"><img src="../../../img/symbols/power/solar-panel/default.svg" width="195" alt="Solar photovoltaic equipment preview"></a>
<a href="../../../img/symbols/nuclear/pwr-reactor-vessel/default.svg"><img src="../../../img/symbols/nuclear/pwr-reactor-vessel/default.svg" width="195" alt="Conceptual pressurized-water reactor vessel preview"></a>
