# Back-to-back HVDC interface

[Power & utilities](../README.md) · [All sectors](../../README.md)

Static SVG schematics of the first declared view. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Back-to-back HVDC interface declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Compact declared first-view topology |
| [Scenario documentation](../../../../scenarios/power-hvdc-interface/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/power-hvdc-interface/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/power-hvdc-interface/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/power-utilities/power-hvdc-interface/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
