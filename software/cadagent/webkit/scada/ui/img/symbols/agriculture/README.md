# Growing & aquaculture

[Parent map](../README.md) · [Gallery](../../README.md) · [Package owner](../../../README.md) · [Interactive equipment example](../../../examples/components/index.html)

Generated from the library renderer. These images show supplied illustrative visual state; they do not run a system model. Motion follows the image viewer’s reduced-motion preference where supported. Static renderers retain the equipment and readouts.

```mermaid
flowchart LR
  Catalog["Equipment descriptor"] --> State["Supplied visual state"]
  State --> Art["Canonical SVG artwork"]
  Art --> Preview["Portable animated image"]
```

This folder contains **10 previews**. Open an image for its full size; use the interactive example to change fields. The table lists the rendering inputs for each asset. Regenerate this map with `npm run gallery:generate`; do not edit generated SVGs or indexes.

| Preview | Equipment and supplied state |
| --- | --- |
| <a href="fish-tank.svg"><img src="fish-tank.svg" alt="Aquaculture fish tank. Active illustrative preview" width="320"></a> | **Aquaculture fish tank**<br>`fish-tank`<br>Active illustrative preview<br><br>Aquatic vessel with visible inventory, independent aeration and decorative fish silhouettes.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `oxygen`, `load`, `damage`. |
| <a href="biofilter.svg"><img src="biofilter.svg" alt="Biological media filter. Active illustrative preview" width="320"></a> | **Biological media filter**<br>`biofilter`<br>Active illustrative preview<br><br>Visible biomedia vessel with separately supplied water and air.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `oxygen`, `load`, `damage`. |
| <a href="media-grow-bed.svg"><img src="media-grow-bed.svg" alt="Media grow bed. Active illustrative preview" width="320"></a> | **Media grow bed**<br>`media-grow-bed`<br>Active illustrative preview<br><br>Granular root bed with an externally supplied flood/drain phase.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `moisture`, `phase`, `damage`. |
| <a href="dwc-raft-bed.svg"><img src="dwc-raft-bed.svg" alt="Deep-water raft bed. Active illustrative preview" width="320"></a> | **Deep-water raft bed**<br>`dwc-raft-bed`<br>Active illustrative preview<br><br>Floating plant raft above a separate water and aeration volume.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `oxygen`, `load`, `damage`. |
| <a href="nft-channel.svg"><img src="nft-channel.svg" alt="Nutrient-film channel. Active illustrative preview" width="320"></a> | **Nutrient-film channel**<br>`nft-channel`<br>Active illustrative preview<br><br>Shallow solution channel with exposed root positions and gravity return.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `moisture`, `load`, `damage`. |
| <a href="ebb-flow-table.svg"><img src="ebb-flow-table.svg" alt="Ebb-and-flow nursery table. Active illustrative preview" width="320"></a> | **Ebb-and-flow nursery table**<br>`ebb-flow-table`<br>Active illustrative preview<br><br>Raised nursery tray with fill, hold and drain phases controlled by the host.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `level`, `moisture`, `phase`, `damage`. |
| <a href="drip-zone.svg"><img src="drip-zone.svg" alt="Drip irrigation zone. Active illustrative preview" width="320"></a> | **Drip irrigation zone**<br>`drip-zone`<br>Active illustrative preview<br><br>Emitter manifold above substrate pots with a separately visible collection drain.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `moisture`, `load`, `damage`. |
| <a href="aeroponic-chamber.svg"><img src="aeroponic-chamber.svg" alt="Aeroponic root chamber. Active illustrative preview" width="320"></a> | **Aeroponic root chamber**<br>`aeroponic-chamber`<br>Active illustrative preview<br><br>Enclosed roots supplied by an explicit mist manifold and drain.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `moisture`, `load`, `damage`. |
| <a href="grow-light.svg"><img src="grow-light.svg" alt="Horticultural light panel. Active illustrative preview" width="320"></a> | **Horticultural light panel**<br>`grow-light`<br>Active illustrative preview<br><br>Downward-facing light array with electrical input, emitted light and rejected heat.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `light`, `load`, `damage`. |
| <a href="air-diffuser.svg"><img src="air-diffuser.svg" alt="Submerged air diffuser. Active illustrative preview" width="320"></a> | **Submerged air diffuser**<br>`air-diffuser`<br>Active illustrative preview<br><br>Porous diffuser and restrained bubble plume driven by supplied air.<br><br>Editable fields: `active`, `running`, `fault`, `status`, `airflow`, `oxygen`, `damage`. |
