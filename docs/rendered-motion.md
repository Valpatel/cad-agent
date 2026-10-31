# Rendered joint motion validation

The maintained [trace protocol](../skills/cad-motion-validation/references/trace-protocol.md) ships with the
[cad-motion-validation skill](../skills/cad-motion-validation/SKILL.md), including when the workflow installer
copies the skill to a different machine. It documents the independent CAD reference, actual renderer capture,
`cad-agent motion-trace` CLI, required coverage, diagnostics and evidence limits.

```mermaid
flowchart TD
    CAD["CAD source<br/>axes, pivots, landmarks"] --> Ref["reference contract<br/>one home frame"]
    Scene["the browser's scene<br/>world matrices × mesh vertices"] --> Obs["observed trace"]
    Ref & Obs --> T["cad-agent motion-trace<br/>compares across each range"]
    G["gates --only motion<br/>CAD interference"] -.->|"complements"| T
    T --> Rep["report<br/>coverage, diagnostics, input hashes"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class Ref,Obs,T here
    class CAD,Scene,G near
    class Rep out
```

Two independent paths meet only in the comparison: the reference comes from the CAD, the observation from the
renderer that people actually look at, so a pivot error in either shows up.
