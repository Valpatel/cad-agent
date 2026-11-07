# Example evaluator

Textbook estimates belonging to this example, not generic toolkit physics.

```mermaid
flowchart TD
    I["../cad-agent.yaml"] --> C["evaluate.py"]
    C --> O["../exports/"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class I,C,O here
```

| File or folder | Purpose |
|---|---|
| [evaluate.py](evaluate.py) | Evaluate candidate geometry, power and cost assumptions. |

[Parent map](../README.md)
