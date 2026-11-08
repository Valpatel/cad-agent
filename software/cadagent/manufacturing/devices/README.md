# Machine integrations

Adapters own their vendor's authentication and transport. They expose demonstrated capabilities;
artifact preparation and job execution stay in the [manufacturing domain](../README.md).

```mermaid
flowchart TD
    C["manufacturing workflow"] --> B["bambu/<br/>read-only adapter"]
    B --> O["observations + limits"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    class C,B,O here
```

| File or folder | Purpose |
|---|---|
| [bambu/](bambu/README.md) | Read-only cloud account and printer observations. |
| [__init__.py](__init__.py) | Package namespace; no connection at import time. |
