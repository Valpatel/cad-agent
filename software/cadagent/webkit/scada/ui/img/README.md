# SCADA UI image gallery

[Package owner](../README.md) · [Equipment map](symbols/README.md) · [Interactive example](../examples/components/index.html) · [State examples](states/README.md) · [UI snapshots](thumbnails/README.md)

Each library owns its own `img/` directory. This package owns equipment artwork, visual states and viewer/workspace previews. [Simulation scenario previews](../../sim/img/README.md) belong to the separate model package.

```mermaid
flowchart TD
  UI["scada-ui / img"] --> Symbols["symbols / equipment families"]
  UI --> States["states / selected visual comparisons"]
  UI --> Captures["thumbnails / equipment and workspace JPEGs"]
  Model["scada-sim / img"] --> Scenarios["model-owned scenario previews"]
  UI -. "sibling library link" .-> Model
```

The catalog contains 239 generated SVG previews. SVG images contain the canonical equipment artwork, native SVG text/readouts and inline CSS animation; no scripts, external styles, fonts or images. GitHub and other Markdown renderers can display them using ordinary relative image links. Animation support depends on the renderer; the first frame remains useful. The live examples provide interactive state controls.

All displayed values and selected states are illustrative, editable rendering inputs. An animated picture is not a process model. Read [the style guide](../STYLE_GUIDE.md) and [contribution guide](../CONTRIBUTING.md) before adding assets.

| Folder | Contents and use |
| --- | --- |
| [symbols/](symbols/README.md) | Every default type and declared variant, grouped by equipment family. |
| [states/](states/README.md) | 31 illustrative comparisons for motion, availability, damage and retained inventory. |
| [thumbnails/](thumbnails/README.md) | Static equipment, variant, state and reusable UI captures. |

Generate SVGs and these maps with `npm run gallery:generate`; verify with `npm run gallery:check`. See the [export contract](../docs/GALLERY_EXPORT.md) and [gallery manifest](../metadata/gallery.json) for provenance and checks.

| Family | Previews | Sample |
| --- | --- | --- |
| [Process vessels](symbols/process/README.md) | 39 | <img src="symbols/process/digester.svg" alt="Process vessels example" width="160"> |
| [Pumps &amp; machinery](symbols/rotating/README.md) | 24 | <img src="symbols/rotating/pump.svg" alt="Pumps &amp; machinery example" width="160"> |
| [Power &amp; energy](symbols/power/README.md) | 55 | <img src="symbols/power/generator.svg" alt="Power &amp; energy example" width="160"> |
| [Valves](symbols/valves/README.md) | 45 | <img src="symbols/valves/gate-valve.svg" alt="Valves example" width="160"> |
| [Instruments](symbols/instruments/README.md) | 8 | <img src="symbols/instruments/pressure-transmitter.svg" alt="Instruments example" width="160"> |
| [PLC &amp; networks](symbols/automation/README.md) | 7 | <img src="symbols/automation/plc-rack.svg" alt="PLC &amp; networks example" width="160"> |
| [Connections](symbols/connections/README.md) | 10 | <img src="symbols/connections/pipe.svg" alt="Connections example" width="160"> |
| [Manufacturing &amp; solids](symbols/manufacturing/README.md) | 18 | <img src="symbols/manufacturing/conveyor.svg" alt="Manufacturing &amp; solids example" width="160"> |
| [Nuclear systems](symbols/nuclear/README.md) | 19 | <img src="symbols/nuclear/pwr-reactor-vessel.svg" alt="Nuclear systems example" width="160"> |
| [Growing &amp; aquaculture](symbols/agriculture/README.md) | 10 | <img src="symbols/agriculture/fish-tank.svg" alt="Growing &amp; aquaculture example" width="160"> |
| [Climate control](symbols/climate/README.md) | 4 | <img src="symbols/climate/greenhouse-vent.svg" alt="Climate control example" width="160"> |
