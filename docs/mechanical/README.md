# Mechanical guides

Choose a feature, read its sources, then run the matching check. The [topic tree](../areas.yaml) records each area's evidence level.

```mermaid
flowchart TD
    F["choose a feature"] --> J["joints or mechanisms"]
    J --> C["run the check<br/>record assumptions"]
    C --> R["review evidence<br/>state physical limits"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class F,C here
    class J,R near
```

| Task | Start here |
|---|---|
| Join printed parts | [Inserts](inserts.md), [screw bosses](screw-bosses.md), [printed joints](printed-joints.md) |
| Support or move a part | [Bearings](bearings.md), [linkages](linkages.md), [rendered motion](rendered-motion.md) |
| Flex or assemble a part | [Compliant mechanisms](compliant.md), [subassembly insertion](subassembly-insertion.md) |

[All guides](../README.md) · [Mechanical lessons](../lessons/mechanical/README.md) · [Skills](../../.agents/skills/README.md)
