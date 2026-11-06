# Lessons — electronics

PCB evidence, the board in its enclosure, and release packaging. From a second project, a CAN breakout board and housing (2026-10-26); its Source lines name that project's incident notes.

```mermaid
flowchart TD
    K["KiCad reports"] --> P["pcb-evidence-and-review.md"]
    S["the exported STEP"] --> P
    P --> R["a release package"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class P here
    class K,S near
    class R out
```

| File | Lessons on |
|---|---|
| [pcb-evidence-and-review.md](pcb-evidence-and-review.md) | KiCad report severities and waivers, parity, source hashes, routing geometry, STEP handedness, readback renders, release allowlists |

Each lesson follows the [lesson format](../README.md#lesson-format): a rule, the incident, a check and its source. Back to [all lessons](../README.md).
