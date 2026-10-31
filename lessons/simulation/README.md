# Lessons — simulation

Bought parts, material, load and thermal checks, and the compute they share.

```mermaid
flowchart TD
    B["the exact bought part"] --> S["simulation-and-material.md"]
    S --> C["load and thermal checks<br/>one heavy solver at a time"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class S here
    class B near
    class C out
```

| File | Lessons on |
|---|---|
| [simulation-and-material.md](simulation-and-material.md) | Exact bought parts, slicer grams, re-checking thinner shells, thermal models of printed enclosures, shared compute |

Each lesson follows the [lesson format](../README.md#lesson-format): a rule, the incident, a check and its source. Back to [all lessons](../README.md).
