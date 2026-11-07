# Reviewed scan baselines

Accepted scan fingerprints for the exact imported project revisions.

```mermaid
flowchart TD
    A["README.md"]
    B["../manifest.json"]
    C["../../../tools/vendor_sync.py"]
    B --> A
    C --> A
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [agentcad.json](agentcad.json) | Reviewed fingerprint for agentcad. |
| [bd_warehouse.json](bd_warehouse.json) | Reviewed fingerprint for bd_warehouse. |
| [build123d-mcp.json](build123d-mcp.json) | Reviewed fingerprint for build123d-mcp. |
| [kicad-happy.json](kicad-happy.json) | Reviewed fingerprint for kicad-happy. |
| [kicad-mcp-pro.json](kicad-mcp-pro.json) | Reviewed fingerprint for kicad-mcp-pro. |
| [text-to-cad.json](text-to-cad.json) | Reviewed fingerprint for text-to-cad. |

</details>

[Vendor index](../README.md) · [Import/accept producer](../../../tools/vendor_sync.py) · [Audit consumer](../../../tools/resource_audit.py). Existing receipts are preserved; adding this map does not accept new findings.
