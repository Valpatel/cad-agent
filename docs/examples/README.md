# Worked examples

These are runnable examples and test inputs. Their computed results do not establish physical performance.

```mermaid
flowchart TD
    S["starter box<br/>cad-agent init"] --> C["build + checks"]
    E["two-wheel comparison<br/>design alternatives"] --> V["evaluate + compare"]
    C --> R["inspect evidence + limits"]
    V --> R
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S,E here
    class C,V,R near
```

| Example | Purpose |
|---|---|
| [starter-box](starter-box/README.md) | The checkout and wheel starter copied by `cad-agent init` |
| [explore-two-wheel](explore-two-wheel/README.md) | Compare design alternatives with the existing evaluator |

[Guides](../README.md) · [Project format](../toolkit.md) · [Exploration](../explore.md)
