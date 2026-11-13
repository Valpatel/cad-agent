# Equipment previews

[Parent gallery](../README.md) · [Package owner](../../README.md) · [State comparisons](../states/README.md)

**239 default and variant previews** share the canonical equipment renderer. Each family folder contains its own Markdown index with image thumbnails, editable fields and descriptions.

```mermaid
flowchart LR
  Catalog["Canonical equipment catalog"] --> Families["Family folders"]
  Families --> Default["type.svg"]
  Families --> Variant["type--variant.svg"]
  Default --> Index["Family README thumbnails"]
  Variant --> Index
```

These files are generated rendering examples. Catalog definitions and artwork live under the [source owner](../../src/README.md). Run `npm run gallery:generate` after changing an asset; `npm run gallery:check` verifies inventory and output freshness.

| Family folder | Previews | Sample |
| --- | --- | --- |
| [Process vessels](process/README.md) | 39 | <img src="process/digester.svg" alt="Process vessels example" width="200"> |
| [Pumps &amp; machinery](rotating/README.md) | 24 | <img src="rotating/pump.svg" alt="Pumps &amp; machinery example" width="200"> |
| [Power &amp; energy](power/README.md) | 55 | <img src="power/generator.svg" alt="Power &amp; energy example" width="200"> |
| [Valves](valves/README.md) | 45 | <img src="valves/gate-valve.svg" alt="Valves example" width="200"> |
| [Instruments](instruments/README.md) | 8 | <img src="instruments/pressure-transmitter.svg" alt="Instruments example" width="200"> |
| [PLC &amp; networks](automation/README.md) | 7 | <img src="automation/plc-rack.svg" alt="PLC &amp; networks example" width="200"> |
| [Connections](connections/README.md) | 10 | <img src="connections/pipe.svg" alt="Connections example" width="200"> |
| [Manufacturing &amp; solids](manufacturing/README.md) | 18 | <img src="manufacturing/conveyor.svg" alt="Manufacturing &amp; solids example" width="200"> |
| [Nuclear systems](nuclear/README.md) | 19 | <img src="nuclear/pwr-reactor-vessel.svg" alt="Nuclear systems example" width="200"> |
| [Growing &amp; aquaculture](agriculture/README.md) | 10 | <img src="agriculture/fish-tank.svg" alt="Growing &amp; aquaculture example" width="200"> |
| [Climate control](climate/README.md) | 4 | <img src="climate/greenhouse-vent.svg" alt="Climate control example" width="200"> |
