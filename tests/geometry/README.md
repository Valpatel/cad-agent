# tests/geometry

Tests for [`src/cadagent/geometry/`](../../src/cadagent/geometry/README.md): the shared CAD helpers and reproducible
STEP. Most need CadQuery and skip cleanly without it.

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    G["test_geometry.py<br/>test_step_export.py"] -->|"imports"| P["geometry/<br/>solids, STEP"]
    P --> O["STEP bytes<br/>stable run to run"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class G here
    class P near
    class O out
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `test_geometry.py` | `cadagent.geometry` helpers on real CadQuery solids |
| `test_part_cache.py` | `PartCache`: the BREP cache of built parts, keyed by their sources |
| `test_step_export.py` | Reproducible STEP export: `export_step`, `step_timestamp` and assemblies |

Run: `pytest tests/geometry` (with `PYTHONPATH=src`).

Related: [tests](../README.md) · [where files go](../../CONTRIBUTING.md#where-files-go)
