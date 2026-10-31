# cadagent.geometry

Measuring and checking part geometry. `from cadagent.geometry import ...` is the measuring API (bounding boxes,
sections, clearances, mesh checks); the submodules check specific features.

```mermaid
flowchart LR
    B["build script<br/>CadQuery · STEP · STL"] --> M["geometry<br/>bounds · sections · clearance"]
    M --> H["holes<br/>empty of material"]
    M --> F["fasteners<br/>envelopes · stacks"]
    M --> C["connectors<br/>panel windows · fit"]
    M --> K["markings<br/>engraving + SVG proof"]
    H & F & C & K --> R["check JSON<br/>→ publish"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class M,H,F,C,K here
    class B near
    class R out
```

| Module | What it does |
|---|---|
| `__init__.py` | Shared geometry checks (CadQuery, OCP, trimesh; all imported lazily) |
| `holes.py` | Every hole in a part is empty of material (`cad-agent holes`); countersinks and drill points are probed as cones |
| `fasteners.py` | Dimension-driven fastener envelopes and axial stack checks |
| `connectors.py` | Mating-connector envelopes: panel windows from the plug, then proof that the plug fits |
| `markings.py` | One XY drawing for engraved markings and a matching SVG proof |

Related: [package map](../README.md) · [gates](../gates/__init__.py) (assembly-level checks) ·
[common issues](../../../docs/common-issues.md) (the mistakes these catch)
