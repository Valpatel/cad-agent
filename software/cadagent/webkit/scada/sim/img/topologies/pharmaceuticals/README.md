# Pharmaceuticals — compact topology diagrams

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
| [Oral-liquid manufacturing](pharma-oral-liquid/README.md)<br>`pharma-oral-liquid` | <a href="pharma-oral-liquid/topology.svg"><img src="pharma-oral-liquid/topology.svg" width="360" alt="Oral-liquid manufacturing declared topology"></a> |
| [Tablet manufacturing](tablets/README.md)<br>`tablets` | <a href="tablets/topology.svg"><img src="tablets/topology.svg" width="360" alt="Tablet manufacturing declared topology"></a> |
| [Sterile-filling concept](sterile-filling/README.md)<br>`sterile-filling` | <a href="sterile-filling/topology.svg"><img src="sterile-filling/topology.svg" width="360" alt="Sterile-filling concept declared topology"></a> |
