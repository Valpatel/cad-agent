# Starter checks

Checks copied with the starter and consumed by its cad-agent.yaml commands.

```mermaid
flowchart TD
    I["../cad-agent.yaml"] --> C["checks.py"]
    C --> O["../exports/"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class I,C,O here
```

| File or folder | Purpose |
|---|---|
| [checks.py](checks.py) | Write insert-joint and example check verdicts. |

[Parent map](../README.md)
