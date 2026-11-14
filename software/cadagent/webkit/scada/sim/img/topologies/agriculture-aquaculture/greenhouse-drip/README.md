# Drip / substrate greenhouse

[Agriculture & aquaculture](../README.md) · [All sectors](../../README.md)

Static SVG schematics of the first declared view. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Drip / substrate greenhouse declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Compact declared first-view topology |
| [Scenario documentation](../../../../scenarios/greenhouse-drip/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/greenhouse-drip/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/greenhouse-drip/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/agriculture-aquaculture/greenhouse-drip/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
