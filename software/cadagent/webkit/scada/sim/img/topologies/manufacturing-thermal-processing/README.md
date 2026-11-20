# Manufacturing & thermal processing — compact topology diagrams

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
| [Electric batch heating cell](electric-batch-oven/README.md)<br>`electric-batch-oven` | <a href="electric-batch-oven/topology.svg"><img src="electric-batch-oven/topology.svg" width="360" alt="Electric batch heating cell declared topology"></a> |
