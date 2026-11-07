# Starter CAD

The copied starter build script uses toolkit joint calculations for a box and lid.

```mermaid
flowchart TD
    I["../cad-agent.yaml"] --> C["build.py"]
    C --> O["../exports/"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class I,C,O here
```

| File or folder | Purpose |
|---|---|
| [build.py](build.py) | Generate STEP/assembly outputs from configurable dimensions. |

[Parent map](../README.md)
