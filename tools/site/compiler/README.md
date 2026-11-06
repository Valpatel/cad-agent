# Site compilers

Compile selected committed sources. Physical paths supply provenance; emitted URLs remain public identities.

```mermaid
flowchart TD
    S["Markdown + source records"] --> C["HTML, catalogue + references"]
    C --> O["public pages + agent indexes"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S here
```

[Site tooling](../README.md) · [Tests](../../../tests/site/README.md)
