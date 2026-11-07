# Integrity gates

Evaluate declared assembly relationships and emit assumption-bearing verdicts. Sampled geometry and access checks do not prove strength or physical fit.

```mermaid
flowchart TD
    R["run.py"] --> A["relations.py + cache.py"]
    A --> G["assembly.py + subassembly.py"]
    A --> C["connectivity.py + containment.py"]
    A --> F["fasteners.py + motion.py"]
    A --> W["wall.py"]
    G & C & F & W --> V["verdict.py"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class R,A,G,C,F,W,V here
```

| File or folder | Purpose |
|---|---|
| [assembly.py](assembly.py) | Declared sequence and insertion/tool access. |
| [subassembly.py](subassembly.py) | Internal scopes and rigid module insertion adapter. |
| [cache.py](cache.py) | Content-and-placement-keyed pairwise cache. |
| [connectivity.py](connectivity.py) | Contact graph and declared connection evidence. |
| [containment.py](containment.py) | Registered contents versus cavity geometry. |
| [fasteners.py](fasteners.py) | Screw stack, material engagement and tool reach. |
| [motion.py](motion.py) | Sample declared joint ranges and interference. |
| [relations.py](relations.py) | Assembly container and pairwise relation states. |
| [run.py](run.py) | Plan and isolate the project gate runs. |
| [verdict.py](verdict.py) | Shared pass/warn/fail record format. |
| [wall.py](wall.py) | Mesh/B-rep inward-ray minimum-wall sampling. |

[Parent map](../README.md)

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package entry point; public imports and compatibility behavior are defined here. |
