# CI provisioning tools

Small runner provisioning corrections live here as the tools root reaches its growth limit.
The release and review entry points remain in the parent directory.

```mermaid
flowchart TD
    W["Full CI"] --> M["Check mirrors"]
    M --> A["HTTPS fallbacks"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    class W,M,A here
```

| File | Purpose |
| --- | --- |
| [apt_mirror.py](apt_mirror.py) | Remove the exact stalled Azure HTTP mirror entry after validating pinned priorities and the Ubuntu 24.04/noble source profile; retain Canonical HTTPS fallbacks and apt signature checks. |

[Tools](../README.md)
