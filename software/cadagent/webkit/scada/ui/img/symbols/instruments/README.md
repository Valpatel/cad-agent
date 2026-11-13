# Instruments

[Parent map](../README.md) · [Gallery](../../README.md) · [Package owner](../../../README.md) · [Interactive equipment example](../../../examples/components/index.html)

Generated from the library renderer. These images show supplied illustrative visual state; they do not run a system model. Motion follows the image viewer’s reduced-motion preference where supported. Static renderers retain the equipment and readouts.

```mermaid
flowchart LR
  Catalog["Equipment descriptor"] --> State["Supplied visual state"]
  State --> Art["Canonical SVG artwork"]
  Art --> Preview["Portable animated image"]
```

This folder contains **8 previews**. Open an image for its full size; use the interactive example to change fields. The table lists the rendering inputs for each asset. Regenerate this map with `npm run gallery:generate`; do not edit generated SVGs or indexes.

| Preview | Equipment and supplied state |
| --- | --- |
| <a href="pressure-transmitter.svg"><img src="pressure-transmitter.svg" alt="Pressure transmitter. Active illustrative preview" width="320"></a> | **Pressure transmitter**<br>`pressure-transmitter`<br>Active illustrative preview<br><br>Round pressure dial with a sensing stem, needle and signal halo.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `value`, `damage`. |
| <a href="flow-meter.svg"><img src="flow-meter.svg" alt="Inline flow meter. Active illustrative preview" width="320"></a> | **Inline flow meter**<br>`flow-meter`<br>Active illustrative preview<br><br>Flanged spool, digital display and animated direction markers.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `value`, `damage`. |
| <a href="temperature-sensor.svg"><img src="temperature-sensor.svg" alt="Temperature probe. Active illustrative preview" width="320"></a> | **Temperature probe**<br>`temperature-sensor`<br>Active illustrative preview<br><br>Thermowell probe with a temperature bulb and local transmitter head.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `value`, `damage`. |
| <a href="level-sensor.svg"><img src="level-sensor.svg" alt="Level transmitter. Active illustrative preview" width="320"></a> | **Level transmitter**<br>`level-sensor`<br>Active illustrative preview<br><br>Radar head with a downward sensing cone and vertical fill ruler.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `value`, `damage`. |
| <a href="gas-analyzer.svg"><img src="gas-analyzer.svg" alt="Gas analyzer. Active illustrative preview" width="320"></a> | **Gas analyzer**<br>`gas-analyzer`<br>Active illustrative preview<br><br>Sampling cabinet with gas tubing, spectrum trace and local display.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `value`, `damage`. |
| <a href="water-quality-probe.svg"><img src="water-quality-probe.svg" alt="Water-quality probe. Active illustrative preview" width="320"></a> | **Water-quality probe**<br>`water-quality-probe`<br>Active illustrative preview<br><br>Immersed probe with explicit pH, EC or dissolved-oxygen identity; readings remain illustrative indices.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `measurement`, `value`, `damage`. |
| <a href="humidity-sensor.svg"><img src="humidity-sensor.svg" alt="Humidity sensor. Active illustrative preview" width="320"></a> | **Humidity sensor**<br>`humidity-sensor`<br>Active illustrative preview<br><br>Ventilated sensing enclosure with a humidity identity and external reading.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `humidity`, `damage`. |
| <a href="light-sensor.svg"><img src="light-sensor.svg" alt="PAR light sensor. Active illustrative preview" width="320"></a> | **PAR light sensor**<br>`light-sensor`<br>Active illustrative preview<br><br>Quantum-sensor silhouette with a light identity; no conversion to physical PAR is inferred.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `light`, `damage`. |
