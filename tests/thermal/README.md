# tests/thermal

Tests for [`src/cadagent/thermal/`](../../src/cadagent/thermal/README.md): plate-fin heat sinks and fan operating
points. The fan curve formulas are tested in [`formulas/`](../formulas/README.md).

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    H["test_heatsink.py"] -->|"imports"| T["thermal/heatsink.py"]
    T --> O["R_th · pressure drop<br/>operating point"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class H here
    class T near
    class O out
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `test_heatsink.py` | Plate-fin heat sink model: limits, trends, the fan operating point and the porous fit |

Run: `pytest tests/thermal` (with `PYTHONPATH=src`).

Related: [tests](../README.md) · [where files go](../../CONTRIBUTING.md#where-files-go)
