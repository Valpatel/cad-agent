# PLC & networks

[Parent map](../README.md) · [Gallery](../../README.md) · [Package owner](../../../README.md) · [Interactive equipment example](../../../examples/components/index.html)

Generated from the library renderer. These images show supplied illustrative visual state; they do not run a system model. Motion follows the image viewer’s reduced-motion preference where supported. Static renderers retain the equipment and readouts.

```mermaid
flowchart LR
  Catalog["Equipment descriptor"] --> State["Supplied visual state"]
  State --> Art["Canonical SVG artwork"]
  Art --> Preview["Portable animated image"]
```

This folder contains **7 previews**. Open an image for its full size; use the interactive example to change fields. The table lists the rendering inputs for each asset. Regenerate this map with `npm run gallery:generate`; do not edit generated SVGs or indexes.

| Preview | Equipment and supplied state |
| --- | --- |
| <a href="plc-rack.svg"><img src="plc-rack.svg" alt="PLC rack. Active illustrative preview" width="320"></a> | **PLC rack**<br>`plc-rack`<br>Active illustrative preview<br><br>Power supply, CPU and modular IO on a common backplane.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `load`, `damage`. |
| <a href="plc-cpu.svg"><img src="plc-cpu.svg" alt="PLC CPU. Active illustrative preview" width="320"></a> | **PLC CPU**<br>`plc-cpu`<br>Active illustrative preview<br><br>Controller module with mode indicators, scan status and service port.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `load`, `damage`. |
| <a href="remote-io.svg"><img src="remote-io.svg" alt="Remote IO station. Active illustrative preview" width="320"></a> | **Remote IO station**<br>`remote-io`<br>Active illustrative preview<br><br>Distributed input and output modules with field terminal blocks.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `load`, `damage`. |
| <a href="hmi.svg"><img src="hmi.svg" alt="Operator HMI. Active illustrative preview" width="320"></a> | **Operator HMI**<br>`hmi`<br>Active illustrative preview<br><br>Panel-mounted touch display with a miniature process diagram.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `damage`. |
| <a href="scada-server.svg"><img src="scada-server.svg" alt="SCADA server. Active illustrative preview" width="320"></a> | **SCADA server**<br>`scada-server`<br>Active illustrative preview<br><br>Server enclosure with drive bays, trend display and network activity.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `load`, `damage`. |
| <a href="network-switch.svg"><img src="network-switch.svg" alt="Industrial network switch. Active illustrative preview" width="320"></a> | **Industrial network switch**<br>`network-switch`<br>Active illustrative preview<br><br>Rugged Ethernet switch with individual RJ45 ports and link activity.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `load`, `damage`. |
| <a href="radio.svg"><img src="radio.svg" alt="Telemetry radio. Active illustrative preview" width="320"></a> | **Telemetry radio**<br>`radio`<br>Active illustrative preview<br><br>Antenna, radio enclosure and pulsing bidirectional signal arcs.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `connected`, `damage`. |
