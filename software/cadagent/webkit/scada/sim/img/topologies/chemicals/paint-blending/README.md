# Paint blending

[Chemicals](../README.md) · [All sectors](../../README.md)

Static SVG schematics of a declared view, selected by the catalog topologyView when present. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Paint blending declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Static declared `process` view |
| [Scenario documentation](../../../../scenarios/paint-blending/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/paint-blending/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/paint-blending/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/chemicals/paint-blending/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
