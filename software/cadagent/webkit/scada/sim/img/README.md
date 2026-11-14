# Simulation scenario gallery

**61 illustrative systems** grouped by sector. These previews belong to the simulation library and travel with its system/model examples.

Each image shows the real viewer after resetting the model, pausing the host clock and using Zoom to fit. Diagram layout is illustrative; overview text size depends on the system bounds. Open the portable Explorer example to zoom, inspect equipment and issue commands.

[Package owner](../README.md) · [Compact SVG topology maps](topologies/README.md) · [Thumbnail folder map](thumbnails/README.md) · [Explorer instructions](../../explorer/README.md) · [Contact sheet](thumbnails/contact-sheet.jpg) · [Capture manifest](../metadata/thumbnails.json)

The UI library owns its separate [symbol and workspace gallery](../../ui/img/README.md). Each library keeps its own image directory; there is no shared root asset bucket.

```mermaid
flowchart LR
  Definitions["scada-sim scenarios / system and model JSON"] --> Host["Explorer host and shared UI viewer"]
  Host --> Capture["Reset, pause and Zoom to fit"]
  Capture --> Images["scada-sim img / thumbnails"]
  Images --> Map["Sector gallery and contact sheet"]
```

| Folder or file | Purpose |
| --- | --- |
| [topologies/](topologies/README.md) | Compact static vector process maps with equipment symbols and declared directed connections. |
| [thumbnails/](thumbnails/README.md) | One real initial-view JPEG per scenario, plus the complete contact sheet. |
| [Capture manifest](../metadata/thumbnails.json) | Source hashes, captured view, camera coverage and image dimensions. |

The SCADA development tools own capture tooling; this model package owns the resulting images. Regenerate captures only when rendering or model inputs change. Documentation-only map refreshes use `npm --prefix tools/webkit/scada run thumbnails:scenarios -- --indexes-only` after the existing capture provenance and bytes pass validation.

## Agriculture &amp; aquaculture

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/agriculture-aquaculture/aquaponics-media-bed/preview.jpg"><img src="thumbnails/agriculture-aquaculture/aquaponics-media-bed/preview.jpg" alt="Media-bed aquaponics initial diagram" width="300"></a> | **Media-bed aquaponics**<br>`aquaponics-media-bed` | [System JSON](../scenarios/aquaponics-media-bed/system.json) · [Model JSON](../scenarios/aquaponics-media-bed/model.json) · [Portable example](../../explorer/index.html?scenario=aquaponics-media-bed) |
| <a href="thumbnails/agriculture-aquaculture/aquaponics-dwc/preview.jpg"><img src="thumbnails/agriculture-aquaculture/aquaponics-dwc/preview.jpg" alt="Raft / DWC aquaponics initial diagram" width="300"></a> | **Raft / DWC aquaponics**<br>`aquaponics-dwc` | [System JSON](../scenarios/aquaponics-dwc/system.json) · [Model JSON](../scenarios/aquaponics-dwc/model.json) · [Portable example](../../explorer/index.html?scenario=aquaponics-dwc) |
| <a href="thumbnails/agriculture-aquaculture/hydroponics-nft/preview.jpg"><img src="thumbnails/agriculture-aquaculture/hydroponics-nft/preview.jpg" alt="NFT hydroponics initial diagram" width="300"></a> | **NFT hydroponics**<br>`hydroponics-nft` | [System JSON](../scenarios/hydroponics-nft/system.json) · [Model JSON](../scenarios/hydroponics-nft/model.json) · [Portable example](../../explorer/index.html?scenario=hydroponics-nft) |
| <a href="thumbnails/agriculture-aquaculture/hydroponics-ebb-flow/preview.jpg"><img src="thumbnails/agriculture-aquaculture/hydroponics-ebb-flow/preview.jpg" alt="Ebb-and-flow nursery initial diagram" width="300"></a> | **Ebb-and-flow nursery**<br>`hydroponics-ebb-flow` | [System JSON](../scenarios/hydroponics-ebb-flow/system.json) · [Model JSON](../scenarios/hydroponics-ebb-flow/model.json) · [Portable example](../../explorer/index.html?scenario=hydroponics-ebb-flow) |
| <a href="thumbnails/agriculture-aquaculture/greenhouse-drip/preview.jpg"><img src="thumbnails/agriculture-aquaculture/greenhouse-drip/preview.jpg" alt="Drip / substrate greenhouse initial diagram" width="300"></a> | **Drip / substrate greenhouse**<br>`greenhouse-drip` | [System JSON](../scenarios/greenhouse-drip/system.json) · [Model JSON](../scenarios/greenhouse-drip/model.json) · [Portable example](../../explorer/index.html?scenario=greenhouse-drip) |
| <a href="thumbnails/agriculture-aquaculture/indoor-aeroponics/preview.jpg"><img src="thumbnails/agriculture-aquaculture/indoor-aeroponics/preview.jpg" alt="Indoor vertical / aeroponic room initial diagram" width="300"></a> | **Indoor vertical / aeroponic room**<br>`indoor-aeroponics` | [System JSON](../scenarios/indoor-aeroponics/system.json) · [Model JSON](../scenarios/indoor-aeroponics/model.json) · [Portable example](../../explorer/index.html?scenario=indoor-aeroponics) |

## Biopharma

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/biopharma/biopharma-fermentation/preview.jpg"><img src="thumbnails/biopharma/biopharma-fermentation/preview.jpg" alt="Biopharma fermentation initial diagram" width="300"></a> | **Biopharma fermentation**<br>`biopharma-fermentation` | [System JSON](../scenarios/biopharma-fermentation/system.json) · [Model JSON](../scenarios/biopharma-fermentation/model.json) · [Portable example](../../explorer/index.html?scenario=biopharma-fermentation) |

## Chemicals

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/chemicals/paint-blending/preview.jpg"><img src="thumbnails/chemicals/paint-blending/preview.jpg" alt="Paint blending initial diagram" width="300"></a> | **Paint blending**<br>`paint-blending` | [System JSON](../scenarios/paint-blending/system.json) · [Model JSON](../scenarios/paint-blending/model.json) · [Portable example](../../explorer/index.html?scenario=paint-blending) |
| <a href="thumbnails/chemicals/industrial-detergent/preview.jpg"><img src="thumbnails/chemicals/industrial-detergent/preview.jpg" alt="Industrial detergent initial diagram" width="300"></a> | **Industrial detergent**<br>`industrial-detergent` | [System JSON](../scenarios/industrial-detergent/system.json) · [Model JSON](../scenarios/industrial-detergent/model.json) · [Portable example](../../explorer/index.html?scenario=industrial-detergent) |

## Construction materials

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/construction-materials/concrete-batching/preview.jpg"><img src="thumbnails/construction-materials/concrete-batching/preview.jpg" alt="Concrete batching initial diagram" width="300"></a> | **Concrete batching**<br>`concrete-batching` | [System JSON](../scenarios/concrete-batching/system.json) · [Model JSON](../scenarios/concrete-batching/model.json) · [Portable example](../../explorer/index.html?scenario=concrete-batching) |
| <a href="thumbnails/construction-materials/cement/preview.jpg"><img src="thumbnails/construction-materials/cement/preview.jpg" alt="Cement processing initial diagram" width="300"></a> | **Cement processing**<br>`cement` | [System JSON](../scenarios/cement/system.json) · [Model JSON](../scenarios/cement/model.json) · [Portable example](../../explorer/index.html?scenario=cement) |

## Consumer products

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/consumer-products/shampoo/preview.jpg"><img src="thumbnails/consumer-products/shampoo/preview.jpg" alt="Shampoo blending initial diagram" width="300"></a> | **Shampoo blending**<br>`shampoo` | [System JSON](../scenarios/shampoo/system.json) · [Model JSON](../scenarios/shampoo/model.json) · [Portable example](../../explorer/index.html?scenario=shampoo) |

## Fiber processing

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/fiber-processing/pulp-paper/preview.jpg"><img src="thumbnails/fiber-processing/pulp-paper/preview.jpg" alt="Pulp &amp; paper initial diagram" width="300"></a> | **Pulp &amp; paper**<br>`pulp-paper` | [System JSON](../scenarios/pulp-paper/system.json) · [Model JSON](../scenarios/pulp-paper/model.json) · [Portable example](../../explorer/index.html?scenario=pulp-paper) |

## Food &amp; beverage

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/food-beverage/winery/preview.jpg"><img src="thumbnails/food-beverage/winery/preview.jpg" alt="Winery initial diagram" width="300"></a> | **Winery**<br>`winery` | [System JSON](../scenarios/winery/system.json) · [Model JSON](../scenarios/winery/model.json) · [Portable example](../../explorer/index.html?scenario=winery) |
| <a href="thumbnails/food-beverage/brewery/preview.jpg"><img src="thumbnails/food-beverage/brewery/preview.jpg" alt="Brewery initial diagram" width="300"></a> | **Brewery**<br>`brewery` | [System JSON](../scenarios/brewery/system.json) · [Model JSON](../scenarios/brewery/model.json) · [Portable example](../../explorer/index.html?scenario=brewery) |
| <a href="thumbnails/food-beverage/fortune-cookies/preview.jpg"><img src="thumbnails/food-beverage/fortune-cookies/preview.jpg" alt="Fortune-cookie factory initial diagram" width="300"></a> | **Fortune-cookie factory**<br>`fortune-cookies` | [System JSON](../scenarios/fortune-cookies/system.json) · [Model JSON](../scenarios/fortune-cookies/model.json) · [Portable example](../../explorer/index.html?scenario=fortune-cookies) |
| <a href="thumbnails/food-beverage/carbonated-beverages/preview.jpg"><img src="thumbnails/food-beverage/carbonated-beverages/preview.jpg" alt="Carbonated beverages initial diagram" width="300"></a> | **Carbonated beverages**<br>`carbonated-beverages` | [System JSON](../scenarios/carbonated-beverages/system.json) · [Model JSON](../scenarios/carbonated-beverages/model.json) · [Portable example](../../explorer/index.html?scenario=carbonated-beverages) |
| <a href="thumbnails/food-beverage/dairy/preview.jpg"><img src="thumbnails/food-beverage/dairy/preview.jpg" alt="Dairy processing initial diagram" width="300"></a> | **Dairy processing**<br>`dairy` | [System JSON](../scenarios/dairy/system.json) · [Model JSON](../scenarios/dairy/model.json) · [Portable example](../../explorer/index.html?scenario=dairy) |
| <a href="thumbnails/food-beverage/fruit-juice/preview.jpg"><img src="thumbnails/food-beverage/fruit-juice/preview.jpg" alt="Fruit-juice line initial diagram" width="300"></a> | **Fruit-juice line**<br>`fruit-juice` | [System JSON](../scenarios/fruit-juice/system.json) · [Model JSON](../scenarios/fruit-juice/model.json) · [Portable example](../../explorer/index.html?scenario=fruit-juice) |

## Manufacturing &amp; thermal processing

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/manufacturing-thermal-processing/electric-batch-oven/preview.jpg"><img src="thumbnails/manufacturing-thermal-processing/electric-batch-oven/preview.jpg" alt="Electric batch heating cell initial diagram" width="300"></a> | **Electric batch heating cell**<br>`electric-batch-oven` | [System JSON](../scenarios/electric-batch-oven/system.json) · [Model JSON](../scenarios/electric-batch-oven/model.json) · [Portable example](../../explorer/index.html?scenario=electric-batch-oven) |

## Materials

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/materials/polymer-extrusion/preview.jpg"><img src="thumbnails/materials/polymer-extrusion/preview.jpg" alt="Polymer extrusion initial diagram" width="300"></a> | **Polymer extrusion**<br>`polymer-extrusion` | [System JSON](../scenarios/polymer-extrusion/system.json) · [Model JSON](../scenarios/polymer-extrusion/model.json) · [Portable example](../../explorer/index.html?scenario=polymer-extrusion) |

## Mineral processing

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/mineral-processing/mineral-crushing/preview.jpg"><img src="thumbnails/mineral-processing/mineral-crushing/preview.jpg" alt="Mineral crushing &amp; screening initial diagram" width="300"></a> | **Mineral crushing &amp; screening**<br>`mineral-crushing` | [System JSON](../scenarios/mineral-crushing/system.json) · [Model JSON](../scenarios/mineral-crushing/model.json) · [Portable example](../../explorer/index.html?scenario=mineral-crushing) |
| <a href="thumbnails/mineral-processing/mineral-flotation/preview.jpg"><img src="thumbnails/mineral-processing/mineral-flotation/preview.jpg" alt="Mineral flotation initial diagram" width="300"></a> | **Mineral flotation**<br>`mineral-flotation` | [System JSON](../scenarios/mineral-flotation/system.json) · [Model JSON](../scenarios/mineral-flotation/model.json) · [Portable example](../../explorer/index.html?scenario=mineral-flotation) |

## Pharmaceuticals

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/pharmaceuticals/pharma-oral-liquid/preview.jpg"><img src="thumbnails/pharmaceuticals/pharma-oral-liquid/preview.jpg" alt="Oral-liquid manufacturing initial diagram" width="300"></a> | **Oral-liquid manufacturing**<br>`pharma-oral-liquid` | [System JSON](../scenarios/pharma-oral-liquid/system.json) · [Model JSON](../scenarios/pharma-oral-liquid/model.json) · [Portable example](../../explorer/index.html?scenario=pharma-oral-liquid) |
| <a href="thumbnails/pharmaceuticals/tablets/preview.jpg"><img src="thumbnails/pharmaceuticals/tablets/preview.jpg" alt="Tablet manufacturing initial diagram" width="300"></a> | **Tablet manufacturing**<br>`tablets` | [System JSON](../scenarios/tablets/system.json) · [Model JSON](../scenarios/tablets/model.json) · [Portable example](../../explorer/index.html?scenario=tablets) |
| <a href="thumbnails/pharmaceuticals/sterile-filling/preview.jpg"><img src="thumbnails/pharmaceuticals/sterile-filling/preview.jpg" alt="Sterile-filling concept initial diagram" width="300"></a> | **Sterile-filling concept**<br>`sterile-filling` | [System JSON](../scenarios/sterile-filling/system.json) · [Model JSON](../scenarios/sterile-filling/model.json) · [Portable example](../../explorer/index.html?scenario=sterile-filling) |

## Power &amp; utilities

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/power-utilities/power-gas-simple-cycle/preview.jpg"><img src="thumbnails/power-utilities/power-gas-simple-cycle/preview.jpg" alt="Simple-cycle gas turbine initial diagram" width="300"></a> | **Simple-cycle gas turbine**<br>`power-gas-simple-cycle` | [System JSON](../scenarios/power-gas-simple-cycle/system.json) · [Model JSON](../scenarios/power-gas-simple-cycle/model.json) · [Portable example](../../explorer/index.html?scenario=power-gas-simple-cycle) |
| <a href="thumbnails/power-utilities/power-gas-combined-cycle/preview.jpg"><img src="thumbnails/power-utilities/power-gas-combined-cycle/preview.jpg" alt="Combined-cycle gas plant initial diagram" width="300"></a> | **Combined-cycle gas plant**<br>`power-gas-combined-cycle` | [System JSON](../scenarios/power-gas-combined-cycle/system.json) · [Model JSON](../scenarios/power-gas-combined-cycle/model.json) · [Portable example](../../explorer/index.html?scenario=power-gas-combined-cycle) |
| <a href="thumbnails/power-utilities/power-coal-steam/preview.jpg"><img src="thumbnails/power-utilities/power-coal-steam/preview.jpg" alt="Coal steam-cycle plant initial diagram" width="300"></a> | **Coal steam-cycle plant**<br>`power-coal-steam` | [System JSON](../scenarios/power-coal-steam/system.json) · [Model JSON](../scenarios/power-coal-steam/model.json) · [Portable example](../../explorer/index.html?scenario=power-coal-steam) |
| <a href="thumbnails/power-utilities/power-biomass-chp/preview.jpg"><img src="thumbnails/power-utilities/power-biomass-chp/preview.jpg" alt="Biomass CHP initial diagram" width="300"></a> | **Biomass CHP**<br>`power-biomass-chp` | [System JSON](../scenarios/power-biomass-chp/system.json) · [Model JSON](../scenarios/power-biomass-chp/model.json) · [Portable example](../../explorer/index.html?scenario=power-biomass-chp) |
| <a href="thumbnails/power-utilities/power-hydro-impoundment/preview.jpg"><img src="thumbnails/power-utilities/power-hydro-impoundment/preview.jpg" alt="Impoundment hydropower initial diagram" width="300"></a> | **Impoundment hydropower**<br>`power-hydro-impoundment` | [System JSON](../scenarios/power-hydro-impoundment/system.json) · [Model JSON](../scenarios/power-hydro-impoundment/model.json) · [Portable example](../../explorer/index.html?scenario=power-hydro-impoundment) |
| <a href="thumbnails/power-utilities/power-hydro-diversion/preview.jpg"><img src="thumbnails/power-utilities/power-hydro-diversion/preview.jpg" alt="Diversion hydropower initial diagram" width="300"></a> | **Diversion hydropower**<br>`power-hydro-diversion` | [System JSON](../scenarios/power-hydro-diversion/system.json) · [Model JSON](../scenarios/power-hydro-diversion/model.json) · [Portable example](../../explorer/index.html?scenario=power-hydro-diversion) |
| <a href="thumbnails/power-utilities/power-pumped-storage/preview.jpg"><img src="thumbnails/power-utilities/power-pumped-storage/preview.jpg" alt="Reversible pumped storage initial diagram" width="300"></a> | **Reversible pumped storage**<br>`power-pumped-storage` | [System JSON](../scenarios/power-pumped-storage/system.json) · [Model JSON](../scenarios/power-pumped-storage/model.json) · [Portable example](../../explorer/index.html?scenario=power-pumped-storage) |
| <a href="thumbnails/power-utilities/power-nuclear-pwr/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-pwr/preview.jpg" alt="Pressurized-water nuclear concept initial diagram" width="300"></a> | **Pressurized-water nuclear concept**<br>`power-nuclear-pwr` | [System JSON](../scenarios/power-nuclear-pwr/system.json) · [Model JSON](../scenarios/power-nuclear-pwr/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-pwr) |
| <a href="thumbnails/power-utilities/power-nuclear-phwr/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-phwr/preview.jpg" alt="Pressure-channel heavy-water concept initial diagram" width="300"></a> | **Pressure-channel heavy-water concept**<br>`power-nuclear-phwr` | [System JSON](../scenarios/power-nuclear-phwr/system.json) · [Model JSON](../scenarios/power-nuclear-phwr/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-phwr) |
| <a href="thumbnails/power-utilities/power-nuclear-htgr/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-htgr/preview.jpg" alt="Helium-cooled reactor concept initial diagram" width="300"></a> | **Helium-cooled reactor concept**<br>`power-nuclear-htgr` | [System JSON](../scenarios/power-nuclear-htgr/system.json) · [Model JSON](../scenarios/power-nuclear-htgr/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-htgr) |
| <a href="thumbnails/power-utilities/power-nuclear-sodium-fast/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-sodium-fast/preview.jpg" alt="Pool-type sodium fast-reactor concept initial diagram" width="300"></a> | **Pool-type sodium fast-reactor concept**<br>`power-nuclear-sodium-fast` | [System JSON](../scenarios/power-nuclear-sodium-fast/system.json) · [Model JSON](../scenarios/power-nuclear-sodium-fast/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-sodium-fast) |
| <a href="thumbnails/power-utilities/power-nuclear-molten-salt/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-molten-salt/preview.jpg" alt="Solid-fuel salt-cooled nuclear concept initial diagram" width="300"></a> | **Solid-fuel salt-cooled nuclear concept**<br>`power-nuclear-molten-salt` | [System JSON](../scenarios/power-nuclear-molten-salt/system.json) · [Model JSON](../scenarios/power-nuclear-molten-salt/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-molten-salt) |
| <a href="thumbnails/power-utilities/power-nuclear-bwr/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-bwr/preview.jpg" alt="Boiling-water nuclear concept initial diagram" width="300"></a> | **Boiling-water nuclear concept**<br>`power-nuclear-bwr` | [System JSON](../scenarios/power-nuclear-bwr/system.json) · [Model JSON](../scenarios/power-nuclear-bwr/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-bwr) |
| <a href="thumbnails/power-utilities/power-nuclear-lw-smr/preview.jpg"><img src="thumbnails/power-utilities/power-nuclear-lw-smr/preview.jpg" alt="Two-module integral-PWR concept initial diagram" width="300"></a> | **Two-module integral-PWR concept**<br>`power-nuclear-lw-smr` | [System JSON](../scenarios/power-nuclear-lw-smr/system.json) · [Model JSON](../scenarios/power-nuclear-lw-smr/model.json) · [Portable example](../../explorer/index.html?scenario=power-nuclear-lw-smr) |
| <a href="thumbnails/power-utilities/power-ng-engine-chp/preview.jpg"><img src="thumbnails/power-utilities/power-ng-engine-chp/preview.jpg" alt="Natural-gas engine CHP initial diagram" width="300"></a> | **Natural-gas engine CHP**<br>`power-ng-engine-chp` | [System JSON](../scenarios/power-ng-engine-chp/system.json) · [Model JSON](../scenarios/power-ng-engine-chp/model.json) · [Portable example](../../explorer/index.html?scenario=power-ng-engine-chp) |
| <a href="thumbnails/power-utilities/power-diesel-standby/preview.jpg"><img src="thumbnails/power-utilities/power-diesel-standby/preview.jpg" alt="Diesel standby supply initial diagram" width="300"></a> | **Diesel standby supply**<br>`power-diesel-standby` | [System JSON](../scenarios/power-diesel-standby/system.json) · [Model JSON](../scenarios/power-diesel-standby/model.json) · [Portable example](../../explorer/index.html?scenario=power-diesel-standby) |
| <a href="thumbnails/power-utilities/power-gasoline-portable/preview.jpg"><img src="thumbnails/power-utilities/power-gasoline-portable/preview.jpg" alt="Portable gasoline generator initial diagram" width="300"></a> | **Portable gasoline generator**<br>`power-gasoline-portable` | [System JSON](../scenarios/power-gasoline-portable/system.json) · [Model JSON](../scenarios/power-gasoline-portable/model.json) · [Portable example](../../explorer/index.html?scenario=power-gasoline-portable) |
| <a href="thumbnails/power-utilities/power-substation-distribution/preview.jpg"><img src="thumbnails/power-utilities/power-substation-distribution/preview.jpg" alt="Distribution substation initial diagram" width="300"></a> | **Distribution substation**<br>`power-substation-distribution` | [System JSON](../scenarios/power-substation-distribution/system.json) · [Model JSON](../scenarios/power-substation-distribution/model.json) · [Portable example](../../explorer/index.html?scenario=power-substation-distribution) |
| <a href="thumbnails/power-utilities/power-substation-gsu/preview.jpg"><img src="thumbnails/power-utilities/power-substation-gsu/preview.jpg" alt="Generator step-up substation initial diagram" width="300"></a> | **Generator step-up substation**<br>`power-substation-gsu` | [System JSON](../scenarios/power-substation-gsu/system.json) · [Model JSON](../scenarios/power-substation-gsu/model.json) · [Portable example](../../explorer/index.html?scenario=power-substation-gsu) |
| <a href="thumbnails/power-utilities/power-substation-gis/preview.jpg"><img src="thumbnails/power-utilities/power-substation-gis/preview.jpg" alt="Gas-insulated substation interface initial diagram" width="300"></a> | **Gas-insulated substation interface**<br>`power-substation-gis` | [System JSON](../scenarios/power-substation-gis/system.json) · [Model JSON](../scenarios/power-substation-gis/model.json) · [Portable example](../../explorer/index.html?scenario=power-substation-gis) |
| <a href="thumbnails/power-utilities/power-hvdc-interface/preview.jpg"><img src="thumbnails/power-utilities/power-hvdc-interface/preview.jpg" alt="Back-to-back HVDC interface initial diagram" width="300"></a> | **Back-to-back HVDC interface**<br>`power-hvdc-interface` | [System JSON](../scenarios/power-hvdc-interface/system.json) · [Model JSON](../scenarios/power-hvdc-interface/model.json) · [Portable example](../../explorer/index.html?scenario=power-hvdc-interface) |
| <a href="thumbnails/power-utilities/power-solar-pv/preview.jpg"><img src="thumbnails/power-utilities/power-solar-pv/preview.jpg" alt="Photovoltaic field initial diagram" width="300"></a> | **Photovoltaic field**<br>`power-solar-pv` | [System JSON](../scenarios/power-solar-pv/system.json) · [Model JSON](../scenarios/power-solar-pv/model.json) · [Portable example](../../explorer/index.html?scenario=power-solar-pv) |
| <a href="thumbnails/power-utilities/power-wind-collection/preview.jpg"><img src="thumbnails/power-utilities/power-wind-collection/preview.jpg" alt="Wind collection network initial diagram" width="300"></a> | **Wind collection network**<br>`power-wind-collection` | [System JSON](../scenarios/power-wind-collection/system.json) · [Model JSON](../scenarios/power-wind-collection/model.json) · [Portable example](../../explorer/index.html?scenario=power-wind-collection) |
| <a href="thumbnails/power-utilities/power-tidal-current/preview.jpg"><img src="thumbnails/power-utilities/power-tidal-current/preview.jpg" alt="Tidal-current array initial diagram" width="300"></a> | **Tidal-current array**<br>`power-tidal-current` | [System JSON](../scenarios/power-tidal-current/system.json) · [Model JSON](../scenarios/power-tidal-current/model.json) · [Portable example](../../explorer/index.html?scenario=power-tidal-current) |
| <a href="thumbnails/power-utilities/power-wave-point-absorber/preview.jpg"><img src="thumbnails/power-utilities/power-wave-point-absorber/preview.jpg" alt="Wave point-absorber array initial diagram" width="300"></a> | **Wave point-absorber array**<br>`power-wave-point-absorber` | [System JSON](../scenarios/power-wave-point-absorber/system.json) · [Model JSON](../scenarios/power-wave-point-absorber/model.json) · [Portable example](../../explorer/index.html?scenario=power-wave-point-absorber) |
| <a href="thumbnails/power-utilities/power-csp-tower/preview.jpg"><img src="thumbnails/power-utilities/power-csp-tower/preview.jpg" alt="Solar power tower initial diagram" width="300"></a> | **Solar power tower**<br>`power-csp-tower` | [System JSON](../scenarios/power-csp-tower/system.json) · [Model JSON](../scenarios/power-csp-tower/model.json) · [Portable example](../../explorer/index.html?scenario=power-csp-tower) |
| <a href="thumbnails/power-utilities/power-csp-trough/preview.jpg"><img src="thumbnails/power-utilities/power-csp-trough/preview.jpg" alt="Parabolic-trough solar plant initial diagram" width="300"></a> | **Parabolic-trough solar plant**<br>`power-csp-trough` | [System JSON](../scenarios/power-csp-trough/system.json) · [Model JSON](../scenarios/power-csp-trough/model.json) · [Portable example](../../explorer/index.html?scenario=power-csp-trough) |
| <a href="thumbnails/power-utilities/power-fuel-cell/preview.jpg"><img src="thumbnails/power-utilities/power-fuel-cell/preview.jpg" alt="Stationary fuel-cell system initial diagram" width="300"></a> | **Stationary fuel-cell system**<br>`power-fuel-cell` | [System JSON](../scenarios/power-fuel-cell/system.json) · [Model JSON](../scenarios/power-fuel-cell/model.json) · [Portable example](../../explorer/index.html?scenario=power-fuel-cell) |
| <a href="thumbnails/power-utilities/power-geothermal-flash/preview.jpg"><img src="thumbnails/power-utilities/power-geothermal-flash/preview.jpg" alt="Flash geothermal initial diagram" width="300"></a> | **Flash geothermal**<br>`power-geothermal-flash` | [System JSON](../scenarios/power-geothermal-flash/system.json) · [Model JSON](../scenarios/power-geothermal-flash/model.json) · [Portable example](../../explorer/index.html?scenario=power-geothermal-flash) |
| <a href="thumbnails/power-utilities/power-geothermal-binary/preview.jpg"><img src="thumbnails/power-utilities/power-geothermal-binary/preview.jpg" alt="Binary geothermal initial diagram" width="300"></a> | **Binary geothermal**<br>`power-geothermal-binary` | [System JSON](../scenarios/power-geothermal-binary/system.json) · [Model JSON](../scenarios/power-geothermal-binary/model.json) · [Portable example](../../explorer/index.html?scenario=power-geothermal-binary) |
| <a href="thumbnails/power-utilities/power-geothermal-dry-steam/preview.jpg"><img src="thumbnails/power-utilities/power-geothermal-dry-steam/preview.jpg" alt="Dry-steam geothermal initial diagram" width="300"></a> | **Dry-steam geothermal**<br>`power-geothermal-dry-steam` | [System JSON](../scenarios/power-geothermal-dry-steam/system.json) · [Model JSON](../scenarios/power-geothermal-dry-steam/model.json) · [Portable example](../../explorer/index.html?scenario=power-geothermal-dry-steam) |
| <a href="thumbnails/power-utilities/power-battery-storage/preview.jpg"><img src="thumbnails/power-utilities/power-battery-storage/preview.jpg" alt="Battery energy-storage system initial diagram" width="300"></a> | **Battery energy-storage system**<br>`power-battery-storage` | [System JSON](../scenarios/power-battery-storage/system.json) · [Model JSON](../scenarios/power-battery-storage/model.json) · [Portable example](../../explorer/index.html?scenario=power-battery-storage) |
| <a href="thumbnails/power-utilities/power-hybrid-microgrid/preview.jpg"><img src="thumbnails/power-utilities/power-hybrid-microgrid/preview.jpg" alt="Hybrid islandable microgrid initial diagram" width="300"></a> | **Hybrid islandable microgrid**<br>`power-hybrid-microgrid` | [System JSON](../scenarios/power-hybrid-microgrid/system.json) · [Model JSON](../scenarios/power-hybrid-microgrid/model.json) · [Portable example](../../explorer/index.html?scenario=power-hybrid-microgrid) |

## Surface treatment

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/surface-treatment/metal-finishing/preview.jpg"><img src="thumbnails/surface-treatment/metal-finishing/preview.jpg" alt="Metal-finishing line initial diagram" width="300"></a> | **Metal-finishing line**<br>`metal-finishing` | [System JSON](../scenarios/metal-finishing/system.json) · [Model JSON](../scenarios/metal-finishing/model.json) · [Portable example](../../explorer/index.html?scenario=metal-finishing) |

## Water &amp; utilities

| Preview | System | Definitions and example |
| --- | --- | --- |
| <a href="thumbnails/water-utilities/wastewater-digester/preview.jpg"><img src="thumbnails/water-utilities/wastewater-digester/preview.jpg" alt="Wastewater &amp; biogas digital twin initial diagram" width="300"></a> | **Wastewater &amp; biogas digital twin**<br>`wastewater-digester` | [System JSON](../scenarios/wastewater-digester/system.json) · [Model JSON](../scenarios/wastewater-digester/model.json) · [Portable example](../../explorer/index.html?scenario=wastewater-digester) |

Generated by the Explorer capture tool with `npm --prefix tools/webkit/scada run thumbnails:scenarios`. Check freshness with `npm --prefix tools/webkit/scada run thumbnails:scenarios -- --check`. Do not hand-edit the images, index or capture manifest.
