# Guides

Choose a task, then follow its method, sources and checks. [The topic tree](areas.yaml) is the complete index.

The arrows show how a guide connects to the files that support it.

```mermaid
flowchart TD
    A["areas.yaml<br/>choose a topic"] --> G["toolkit.md<br/>find a command"]
    G --> S["../src/cadagent/<br/>run the method"]
    G --> R["../research/<br/>read its sources"]
    S --> T["../tests/<br/>check the result"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A,G here
    class S,R,T near
```

| I want to… | Start here |
|---|---|
| Design and check a part | [Toolkit and project format](toolkit.md), [design dossier](dossier.md), [integrity gates](gates.md) |
| Choose a joint or mechanism | [Inserts](inserts.md), [printed joints](printed-joints.md), [snap fits](compliant.md), [bearings](bearings.md), [linkages](linkages.md) |
| Make sheet-metal parts | [Sheet-metal hardware](sheet-metal-hardware.md), [source survey](../research/sheet-metal.md) |
| Compare designs | [Exploration](explore.md), [shared formulas](formulas.md), [fans](fans.md) |
| Review electronics and evidence | [PCB workflow](pcb.md), [review packets](review-packet.md), [pitfall checks](common-issues.md) |
| Understand an animated result | [Rendered motion](rendered-motion.md), [figure provenance](animated-figures.md), [image inputs](img/) |
| Find source-backed practice | [Research map](../research/README.md), [experts](experts.md), [skills](../skills/README.md) |
| Improve the system | [Evidence loop](../README.md#how-it-improves-itself), [vision and evaluation limits](vision.md), [contributor workflow](../CONTRIBUTING.md) |
| Maintain upstream dependencies | [Weekly update procedure](weekly-upstream-update.md), [supply-chain guidance](supply-chain.md) |
| Work on the site | [Style guide](style-guide.md), [web kit](toolkit.md), [page configuration](pages.yaml), [catalogue configuration](catalog.yaml) |

[Home](../README.md) · [Tests](../tests/README.md) · [Lessons](../lessons/README.md) · [Recovery snapshot](../lessons/process/2026-11-05-recovery-audit.md)
