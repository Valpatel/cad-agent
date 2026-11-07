# Independent roles

Two role prompts support independent review and recovery. This folder map is not installed as a third role.

```mermaid
flowchart TD
    A["README.md"]
    B["cad-pr-reviewer.md"]
    C["cad-resume.md"]
    A --> B
    A --> C
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class B,C near
```

<details>
<summary>Files and sources</summary>

| File or folder | Purpose |
|---|---|
| [cad-pr-reviewer.md](cad-pr-reviewer.md) | Independent review of source, CAD and evidence; no authoring or merging. |
| [cad-resume.md](cad-resume.md) | Recover interrupted issue, branch and run state. |

</details>

[Agent kit](../README.md). The [installer](../../software/cadagent/agentkit.py) skips exactly `README.md`; other role Markdown must still pass its frontmatter checks.
