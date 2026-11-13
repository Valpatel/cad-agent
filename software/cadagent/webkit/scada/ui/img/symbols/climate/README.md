# Climate control

[Parent map](../README.md) · [Gallery](../../README.md) · [Package owner](../../../README.md) · [Interactive equipment example](../../../examples/components/index.html)

Generated from the library renderer. These images show supplied illustrative visual state; they do not run a system model. Motion follows the image viewer’s reduced-motion preference where supported. Static renderers retain the equipment and readouts.

```mermaid
flowchart LR
  Catalog["Equipment descriptor"] --> State["Supplied visual state"]
  State --> Art["Canonical SVG artwork"]
  Art --> Preview["Portable animated image"]
```

This folder contains **4 previews**. Open an image for its full size; use the interactive example to change fields. The table lists the rendering inputs for each asset. Regenerate this map with `npm run gallery:generate`; do not edit generated SVGs or indexes.

| Preview | Equipment and supplied state |
| --- | --- |
| <a href="greenhouse-vent.svg"><img src="greenhouse-vent.svg" alt="Greenhouse vent. Active illustrative preview" width="320"></a> | **Greenhouse vent**<br>`greenhouse-vent`<br>Active illustrative preview<br><br>Hinged roof vent with explicit position and an independent air path.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `opening`, `airflow`, `damage`. |
| <a href="shade-screen.svg"><img src="shade-screen.svg" alt="Retractable shade screen. Active illustrative preview" width="320"></a> | **Retractable shade screen**<br>`shade-screen`<br>Active illustrative preview<br><br>Retracting mesh screen with visible deployment and separate incident/transmitted light.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `opening`, `light`, `damage`. |
| <a href="evaporative-pad.svg"><img src="evaporative-pad.svg" alt="Evaporative cooling pad. Active illustrative preview" width="320"></a> | **Evaporative cooling pad**<br>`evaporative-pad`<br>Active illustrative preview<br><br>Wetted pad with distinct air passage and recirculating water connections.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `moisture`, `airflow`, `humidity`, `damage`. |
| <a href="dehumidifier.svg"><img src="dehumidifier.svg" alt="Air dehumidifier. Active illustrative preview" width="320"></a> | **Air dehumidifier**<br>`dehumidifier`<br>Active illustrative preview<br><br>Air coil enclosure with fan, condensate collector and separate drain.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `humidity`, `level`, `load`, `damage`. |
