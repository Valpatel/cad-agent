# Rendered joint motion validation

The maintained [trace protocol](../skills/cad-motion-validation/references/trace-protocol.md) ships with the
[cad-motion-validation skill](../skills/cad-motion-validation/SKILL.md), including when the workflow installer
copies the skill to a different machine. It documents the independent CAD reference, actual renderer capture,
`cad-agent motion-trace` CLI, required coverage, diagnostics and evidence limits.

```mermaid
flowchart TD
    CAD["CAD source<br/>axes, landmarks"] --> Ref["reference<br/>home frame"]
    Scene["browser scene<br/>matrices × vertices"] --> Obs["observed<br/>trace"]
    Ref & Obs --> T["motion-trace<br/>compares each range"]
    G["motion gate<br/>interference"] -.->|"complements"| T
    T --> Rep["report<br/>coverage, diagnostics,<br/>input hashes"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class Ref,Obs,T here
    class CAD,Scene,G near
    class Rep out
```

Two independent paths meet only in the comparison: the reference comes from the CAD, the observation from the
renderer that people actually look at, so a pivot error in either shows up.

A closed loop, such as a four-bar or a five-bar leg, is declared under `loops` on top of the joint tree. Its inputs are
sampled together, its other joints are solved, and each sample's loop must close where the solver closes it. See the
protocol, and [Linkages](linkages.md) for the solver.
