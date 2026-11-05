# Site publication

Choose committed page sources and preserve public page addresses when maintenance files move.

The arrows show source selection and its consumers; a public URL does not replace the source file.

```mermaid
flowchart TD
    G["git inventory<br/>NUL-delimited paths"] --> P["publication.mjs<br/>select page sources"]
    P --> B["../build-site.mjs<br/>HTML + Markdown twins"]
    P --> A["tests/repo/<br/>publication parity"]
    B --> U["/CONTRIBUTING<br/>stable public address"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class P here
    class G,B,A,U near
```

| File | Purpose |
|---|---|
| [publication.mjs](publication.mjs) | Dependency-free source selector and source→public-path mapping; missing mandatory moved sources fail instead of silently disappearing |

[Tools](../README.md) · [Site build](../build-site.mjs) · [Site tests](../../tests/site/README.md)
