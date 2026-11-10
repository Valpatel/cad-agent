# Incident inbox

Dated incidents preserve evidence, causes, corrective rules and limits. Start from the
[symptom index](../SYMPTOM-INDEX.md); durable guidance belongs in the existing domains and shared lessons.

```mermaid
flowchart LR
    I["inbox/"] --> P["publish/"]
    I --> A["agents/<br/>installation + checkouts"]
    I --> R["review/<br/>gate scope + evidence"]
    I --> S["../SYMPTOM-INDEX.md"]
    S --> L["../../docs/lessons/"]
```

| Location | Contents |
| --- | --- |
| [publish/](publish/README.md) | Browser, document compilation and displayed CAD provenance incidents. |
| [agents/](agents/README.md) | Instruction discovery, installer/update boundaries and checkout path consumers. |
| [review/](review/README.md) | Assembly/relation gate scope, source geometry and recoverable validation evidence. |
| Dated files here | Other operational incidents, grouped further when a domain grows. |

[Agent kit](../README.md)
