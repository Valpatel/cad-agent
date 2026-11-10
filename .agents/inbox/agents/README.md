# Agent setup and checkout incidents

Dated evidence for instruction discovery, installation/update consumers and checkout dependencies.
Use the [symptom index](../../SYMPTOM-INDEX.md) to find the relevant case.

```mermaid
flowchart LR
    D["discovery + installation"] --> P["path and platform consumers"]
    P --> C["contained checkouts"]
    C --> W["contributor workflow"]
```

| File | Lesson |
| --- | --- |
| [Discovery boundaries](2026-11-06-agent-discovery-and-resource-boundaries.md) | Exact installed resources, supported checkout names and scoped harness evidence. |
| [Platform markers](2026-11-07-platform-markers-must-reach-update-consumers.md) | Installation requirements must reach every real update consumer. |
| [Checkout containers](2026-11-10-checkout-containers-must-preserve-path-consumers.md) | Preserve source, ownership, environments and every path consumer when organizing trees. |

[Incident inbox](../README.md)
