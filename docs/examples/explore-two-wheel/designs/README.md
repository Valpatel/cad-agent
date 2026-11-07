# Exploration candidates

Hand-authored parameter and part-slot variations consumed by the parent example.

```mermaid
flowchart TD
    I["../cad-agent.yaml"] --> C["standard.json"]
    C --> O["../exports/"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class I,C,O here
```

| File or folder | Purpose |
|---|---|
| [standard.json](standard.json) | Base candidate and shared parameters. |
| [light.json](light.json) | Smaller wheel, actuator and battery variant. |
| [strong.json](strong.json) | Higher output and compute variant. |
| [long-range.json](long-range.json) | Larger pack and camera variant. |

[Parent map](../README.md)
