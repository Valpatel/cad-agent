# Materials — compact topology diagrams

Static SVG schematics of a declared view, selected by the catalog topologyView when present. Symbols identify equipment; arrows show declared connections, not instantaneous flow or measured facility performance.

[All sectors](../README.md) · [Scenario library](../../../scenarios/README.md)

```mermaid
flowchart LR
  Sector[Sector] --> Scenario[Scenario folders]
  Scenario --> Model[System and model]
  Scenario --> View[Preview]
```

| Scenario | Preview |
| --- | --- |
| [Polymer extrusion](polymer-extrusion/README.md)<br>`polymer-extrusion` | <a href="polymer-extrusion/topology.svg"><img src="polymer-extrusion/topology.svg" width="360" alt="Polymer extrusion declared topology"></a> |
