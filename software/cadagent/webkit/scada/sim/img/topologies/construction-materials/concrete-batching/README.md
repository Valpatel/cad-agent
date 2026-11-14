# Concrete batching

[Construction materials](../README.md) · [All sectors](../../README.md)

Static SVG schematics of the first declared view. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Concrete batching declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Compact declared first-view topology |
| [Scenario documentation](../../../../scenarios/concrete-batching/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/concrete-batching/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/concrete-batching/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/construction-materials/concrete-batching/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
