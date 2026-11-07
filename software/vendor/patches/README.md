# Local upstream patches

Changes applied after importing a pinned upstream revision. Keep the patch and its upstream provenance together.

```mermaid
flowchart TD
    A["README.md"]
    B["text-to-cad/"]
    C["../manifest.json"]
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
| [text-to-cad/](text-to-cad/README.md) | The retained local patch for the imported text-to-cad tool. |

</details>

[Vendor index](../README.md) · [Patch application](../../../tools/vendor_sync.py)
