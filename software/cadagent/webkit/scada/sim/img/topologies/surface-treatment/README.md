# Surface treatment — compact topology diagrams

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
| [Metal-finishing line](metal-finishing/README.md)<br>`metal-finishing` | <a href="metal-finishing/topology.svg"><img src="metal-finishing/topology.svg" width="360" alt="Metal-finishing line declared topology"></a> |
