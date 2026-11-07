# Design dossier

Load declared design intent, register geometric facts and check independent review sign-off; declarations do not prove a physical assembly.

```mermaid
flowchart TD
    L["load.py"] --> M["model.py"]
    R["registry.py"] --> I["lint.py"]
    M --> I
    I --> V["review.py"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class L,M,R,I,V here
```

| File or folder | Purpose |
|---|---|
| [load.py](load.py) | YAML loading, item locations and identifier resolution. |
| [model.py](model.py) | Plain dossier dataclasses and serialisation. |
| [registry.py](registry.py) | CAD-side parts, cavities, axes, joints and assembly declarations. |
| [lint.py](lint.py) | Non-geometric dossier lint and status transitions. |
| [review.py](review.py) | Reviewer packets and hash-bound section sign-off. |

[Parent map](../README.md)

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package entry point; public imports and compatibility behavior are defined here. |
