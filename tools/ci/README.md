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
| [apt_mirror.py](apt_mirror.py) | Prefer the registered HTTPS mirror after validating the Ubuntu 24.04/noble source profile; retain Canonical fallbacks/signature checks and report a redacted profile on rejection. |

[Tools](../README.md)
