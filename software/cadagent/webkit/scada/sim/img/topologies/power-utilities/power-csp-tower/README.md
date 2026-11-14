# Solar power tower

[Power & utilities](../README.md) · [All sectors](../../README.md)

Static SVG schematics of a declared view, selected by the catalog topologyView when present. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Solar power tower declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Static declared `field` view |
| [Scenario documentation](../../../../scenarios/power-csp-tower/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/power-csp-tower/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/power-csp-tower/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/power-utilities/power-csp-tower/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
