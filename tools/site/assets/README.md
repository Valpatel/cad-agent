# Website assets

These files keep their public /web/ addresses. The build also copies favicon.ico, install.sh and install.ps1 to their existing root URLs; this owning README is source-only.

```mermaid
flowchart TD
    S["versioned CSS, JS + models"] --> B["site build copies bytes"]
    B --> W["/web/ + root installers"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S here
```

[Site tooling](../README.md) · [Tests](../../../tests/site/README.md)
