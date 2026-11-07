# Worked examples

These are runnable examples and test inputs. Their computed results do not establish physical performance.

```mermaid
flowchart TD
    S["choose an example"] --> C["run its build<br/>or comparison"]
    C --> R["inspect evidence<br/>record limits"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S,C here
    class R near
```

| Example | Purpose |
|---|---|
| [numbered-coupons](numbered-coupons/README.md) | Uniquely stamped physical fit coupons, immutable source/artifact identity and a strict native project plate; no printer operation |
| [starter-box](starter-box/README.md) | The checkout and wheel starter copied by `cad-agent init` |
| [explore-two-wheel](explore-two-wheel/README.md) | Compare design alternatives with the existing evaluator |

[Guides](../README.md) · [Project format](../toolkit.md) · [Exploration](../explore.md)
