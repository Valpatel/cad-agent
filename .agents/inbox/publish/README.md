# Publication incidents

Evidence about what the actual rendered page or model shows, separate from source-only checks.

```mermaid
flowchart LR
    P["publish/"] --> S["../../SYMPTOM-INDEX.md"]
    P --> L["../../../docs/lessons/process/"]
```

| Incident | Lesson |
| --- | --- |
| [Markdown diagrams](2026-10-29-markdown-fences-need-rendered-evidence.md) | A fence needs rendered evidence. |
| [Embedded motion](2026-11-07-image-motion-needs-the-image-consumer.md) | Test the actual image consumer. |
| [Header bounds](2026-11-07-header-visibility-needs-paint-state.md) | Distinguish painted content from stale geometry. |
| [Page placement](2026-11-07-page-placement-can-duplicate-footer-art.md) | Compilation can duplicate footer artwork. |
| [Current CAD](2026-11-07-source-revision-does-not-refresh-a-cad-export.md) | A current checkout can contain stale exported geometry. |

[Incident inbox](../README.md)
