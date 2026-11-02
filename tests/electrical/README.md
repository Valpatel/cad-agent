# tests/electrical

Tests for [`src/cadagent/electrical/`](../../src/cadagent/electrical/README.md): PCB evidence and routed-board
measurements.

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    P["test_pcb.py<br/>test_pcb_routing.py"] -->|"imports"| E["electrical/pcb.py<br/>pcb_routing.py"]
    E --> O["check rows<br/>and measurements"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class P here
    class E near
    class O out
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `test_pcb.py` | `cadagent.electrical.pcb`: board evidence fails closed on missing, stale or incomplete reports |
| `test_pcb_routing.py` | `cadagent.electrical.pcb_routing`: trunk lengths, layer crossings and differential pairs |

Run: `pytest tests/electrical` (with `PYTHONPATH=src`).

Related: [tests](../README.md) · [where files go](../../CONTRIBUTING.md#where-files-go)
