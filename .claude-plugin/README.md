# Plugin entry

The plugin manifest points at the canonical agent kit inside this repository.

```mermaid
flowchart TD
    A["README.md"]
    B["plugin.json"]
    C["../.agents/README.md"]
    A --> B
    B --> C
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [plugin.json](plugin.json) | Plugin identity, version and explicit skill/role entries. |

</details>

[Repository](../README.md) · [Agent kit](../.agents/README.md). This map does not add a plugin hook or alter its declared roles.

The surrounding toolkit uses MIT; the SCADA-derived skills retain the terms in
[the SCADA notice](../software/cadagent/webkit/scada/LICENSE.txt). The manifest declares
this mixed scope explicitly; installation does not grant additional rights.
