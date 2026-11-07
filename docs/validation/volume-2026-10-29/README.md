# Volume precision — 2026-10-29

Immutable observations from the dated volume-precision comparison. They describe those inputs and methods, not a current acceptance run.

```mermaid
flowchart TD
    A["inputs.json"]
    B["default.json"]
    C["gauss.json"]
    D["gk.json"]
    A --> B
    A --> C
    A --> D
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C,D near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [inputs.json](inputs.json) | Recorded comparison inputs. |
| [default.json](default.json) | Recorded default-method output. |
| [gauss.json](gauss.json) | Recorded Gauss-method output. |
| [gk.json](gk.json) | Recorded Gauss–Kronrod-method output. |

</details>

[Validation index](../README.md) · [Method and limits](../../practice/volume-precision.md)
