# Animation scene inputs

Recorded scene inputs and original artwork producers used by the existing README animation tools. Decorative art is distinct from engineering evidence.

```mermaid
flowchart TD
    Y["*.yaml"] --> R["../readme_anim.py"]
    R --> J["*.scene.json"]
    J --> S["../../docs/img/"]
    A["made_with_badge.py"] --> S
    B["repository_map.py"] --> S
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class Y,R,J,S,A,B here
```

| File or folder | Purpose |
|---|---|
| [fea-convergence.yaml](fea-convergence.yaml) | Real-run extraction configuration for the mesh study. |
| [fea-convergence.scene.json](fea-convergence.scene.json) | Recorded mesh-study drawing input. |
| [gyropup-leg.yaml](gyropup-leg.yaml) | Pinned product CAD scene extraction configuration. |
| [gyropup-leg.scene.json](gyropup-leg.scene.json) | Recorded leg drawing input; not the current homepage model. |
| [snap-engagement.yaml](snap-engagement.yaml) | Calculator-derived snap scene configuration. |
| [snap-engagement.scene.json](snap-engagement.scene.json) | Recorded snap engagement drawing input. |
| [made_with_badge.py](made_with_badge.py) | Original vector badge around the project emblem. |
| [repository_map.py](repository_map.py) | Original decorative robot-factory cinematic. |

[Parent map](../README.md)
