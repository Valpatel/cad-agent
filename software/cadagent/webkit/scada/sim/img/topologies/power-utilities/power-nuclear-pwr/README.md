# Pressurized-water nuclear concept

[Power & utilities](../README.md) · [All sectors](../../README.md)

Static SVG schematics of a declared view, selected by the catalog topologyView when present. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

<a href="topology.svg"><img src="topology.svg" width="900" alt="Pressurized-water nuclear concept declared topology"></a>

```mermaid
flowchart LR
  System[System definition] --> View[Preview]
  Symbols[Equipment symbols] --> View
```

| File or source | Purpose |
| --- | --- |
| [Preview](topology.svg) | Static declared `primary` view |
| [Scenario documentation](../../../../scenarios/power-nuclear-pwr/README.md) | Equipment roles, focused views and editable assumptions |
| [System JSON](../../../../scenarios/power-nuclear-pwr/system.json) | Equipment, ports, connections and layouts |
| [Model JSON](../../../../scenarios/power-nuclear-pwr/model.json) | Replaceable behavior and initial values |
| [Captured model state](../../../thumbnails/power-utilities/power-nuclear-pwr/README.md) | Another representation of this scenario |
| [Generation metadata](../../../../metadata/topologies.json) | Source and output provenance |
