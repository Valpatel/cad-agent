# Toolkit software

The installable Python toolkit and pinned third-party source live together here. Product CAD, firmware and application source stay in their product repository.

```mermaid
flowchart TD
    C["cadagent/<br/>Python package + browser SDK"] --> T["../tests/<br/>checks by domain"]
    V["vendor/<br/>pinned upstream source"] --> A["../tools/<br/>audit + reviewed updates"]
    C --> D["../docs/<br/>guides + evidence"]
    V --> D
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class C,V here
    class T,A,D near
```

| Folder | Ownership |
|---|---|
| [cadagent/](cadagent/README.md) | First-party toolkit domains, CLI and packaged browser SDK; installed as `cadagent` |
| [vendor/](vendor/README.md) | Imported upstream trees, license notices, registry and reviewed scan records; excluded from the Python wheel |

Install from the repository root with `python -m pip install -e .`; invoke the same `cad-agent` commands. Generic project examples may use their own `src/` or `vendor/` folders; those names do not refer to this repository's software owner.
