# Recorded timing experiment

`gate_timing.py` is the source of the recorded experiment described in the [workflow survey](../agent-workflow/design-workflows.md). Its old measurements remain dated evidence, not a claim about a current machine or a production model.

```mermaid
flowchart LR
    I["experiment inputs"] --> B["gate_timing.py"]
    B --> M["recorded timings<br/>parameters + limits"]
    M --> S["workflow survey"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class B here
    class I,M,S near
```

| File | Purpose |
|---|---|
| [gate_timing.py](gate_timing.py) | Reproduce the documented experiment with explicit inputs |

[Research map](../README.md)
