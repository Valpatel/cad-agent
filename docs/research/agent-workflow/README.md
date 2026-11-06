# Agent tools and workflows

Compare existing tools before adding a capability. These surveys record what was read and evaluated, with dates and limits.

```mermaid
flowchart LR
    S["sources + surveys"] --> E["evaluate an existing tool"]
    E --> D["adopt, wrap or pass"]
    D --> T["reusable technique<br/>check its evidence"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class E,D here
    class S,T near
```

| Survey | Use |
|---|---|
| [Landscape](landscape.md) | Tools, libraries and benchmarks we track |
| [Agent toolkits](agent-toolkits-2026-10.md) | Dated agent-tool comparisons and adoption notes |
| [Design workflows](design-workflows.md) | Methods, gaps and evaluation evidence |

[Research map](../README.md) · [Skills](../../../skills/README.md)
