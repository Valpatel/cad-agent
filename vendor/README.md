# Upstream code and metadata

Imported code keeps its upstream layout and license. The registry records projects we track; a registry entry does not mean its code was imported or validated.

```mermaid
flowchart TD
    R["upstreams/registry.yaml<br/>tracked projects"] --> C["site catalogue"]
    M["manifest.json<br/>imported pins"] --> V["project folders<br/>upstream code + licenses"]
    M --> N["THIRD_PARTY_NOTICES.md<br/>credits and license records"]
    V --> A["reports + baselines<br/>reviewed scan findings"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class R,M,N here
    class C,V,A near
```

| File or folder | Purpose |
|---|---|
| [upstreams/](upstreams/README.md) | Tracked-project registry; catalogue data and adoption assessment |
| [manifest.json](manifest.json) | Imported projects, exact source commits and license records |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Vendored, runtime and web-kit credits; the sync tool updates only its vendored-project table |
| `baselines/`, `reports/`, `patches/` | Reviewed scan fingerprints, import reports and local patches |
| Project folders | Imported upstream code; each remains pinned in the manifest |

Use [vendor_sync.py](../tools/vendor_sync.py) for imports and notice updates, and the [supply-chain skill](../skills/cad-supply-chain/SKILL.md) for checks. Repository metadata paths are explicitly classified; unexpected files under them still trigger the vendor audit.
