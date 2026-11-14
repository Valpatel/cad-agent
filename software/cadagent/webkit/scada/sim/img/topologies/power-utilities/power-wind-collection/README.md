# Wind collection network

[Power & utilities](../README.md) · [All sectors](../../README.md)

Static SVG schematics of a declared view, selected by the catalog topologyView when present. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Wind collection network declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Static declared `field` view |
| [Scenario documentation](../../../../scenarios/power-wind-collection/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/power-wind-collection/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/power-wind-collection/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/power-utilities/power-wind-collection/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
