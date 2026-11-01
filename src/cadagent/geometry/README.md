# cadagent.geometry

Measuring and checking part geometry. `from cadagent.geometry import ...` is the measuring API (solid validity and
bounds, print STLs, intersections and gaps, downward area, bed fit); the submodules check specific features.

Arrows follow the data. The three helpers at the top are imported by a project's build script, not by cad-agent;
`holes.py` reads the exported STEP files and part list, and `publish/report.py` imports `holes.py` and `within_bed` from
the API.

```mermaid
flowchart TD
    F["fasteners.py<br/>envelopes"] --> B
    K["markings.py<br/>engraving"] --> B
    C["connectors.py<br/>panel windows"] --> B
    B["build script<br/>the project's CadQuery"] -->|"shapes"| G["cadagent.geometry<br/>solids · STL · gaps"]
    G -->|"STL"| X["exports/<br/>STEP · STL · parts file"]
    B -->|"STEP, parts file"| X
    X --> H["holes.py<br/>cad-agent holes"]
    H --> HJ["exports/<br/>hole-checks.json"]
    HJ --> R["publish/report.py<br/>results JSON"]
    G --> R
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class F,K,C,G,H here
    class B,R near
    class X,HJ out
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
