# Text-to-CAD patch

The existing patch disables telemetry, update checking and API access in the imported tool. Read its diff and the pinned manifest before applying it elsewhere.

```mermaid
flowchart TD
    A["README.md"]
    B["0001-disable-telemetry-<br/>update-check-and-api.patch"]
    C["../../manifest.json"]
    C --> B
    A --> B
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [0001-disable-telemetry-update-check-and-api.patch](0001-disable-telemetry-update-check-and-api.patch) | Existing local change applied by the vendor import tool. |

</details>

[Patch index](../README.md) · [Pinned imports](../../manifest.json)
