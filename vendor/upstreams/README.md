# Tracked upstreams

[registry.yaml](registry.yaml) records projects, their licenses, catalogue descriptions and adoption assessments. It feeds the site catalogue and supply-chain audit; it is separate from the [imported-code manifest](../manifest.json).

```mermaid
flowchart LR
    R["registry.yaml<br/>tracked projects"] --> C["site catalogue"]
    R --> A["supply-chain audit"]
    R --> P["reviewed adoption decision"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class R here
    class C,A,P near
```

| File | Purpose |
|---|---|
| [registry.yaml](registry.yaml) | Source data for tracked projects; keep assessments and evidence limits explicit |

[Vendor map](../README.md) · [Weekly update procedure](../../docs/practice/weekly-upstream-update.md) · [Research entry](../../docs/research/README.md)
