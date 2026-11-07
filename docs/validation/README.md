# Recorded validation receipts

Dated validation records bind specific source and tool inputs. They are historical observations, not current production or physical acceptance.

```mermaid
flowchart TD
    M["file-viewer-corpus-manifest.json"] --> R["file-viewer-corpus-results.json"]
    V["file-viewer-validation.json"] --> R
    N["volume-2026-10-29/"] --> R
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class M,R,V,N here
```

| File or folder | Purpose |
|---|---|
| [file-viewer-corpus-manifest.json](file-viewer-corpus-manifest.json) | Source identity and corpus item inventory. |
| [file-viewer-corpus-results.json](file-viewer-corpus-results.json) | Recorded corpus results bound to that manifest. |
| [file-viewer-validation.json](file-viewer-validation.json) | Earlier browser validation receipt. |
| [volume-2026-10-29/](volume-2026-10-29/) | Dated numeric precision outputs; owned as one evidence collection. |

[Parent map](../README.md)
