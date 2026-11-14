# Biopharma — compact topology diagrams

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
| [Biopharma fermentation](biopharma-fermentation/README.md)<br>`biopharma-fermentation` | <a href="biopharma-fermentation/topology.svg"><img src="biopharma-fermentation/topology.svg" width="360" alt="Biopharma fermentation declared topology"></a> |
