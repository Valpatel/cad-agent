# Lessons — review

Evidence that holds up, and what reviewers need to see. Up: [all lessons](../README.md).

```mermaid
flowchart TD
    V["verification-and-evidence.md<br/>checks and honest claims"] --> S["review-site-ux.md<br/>what the reviewer sees"]
    O["original-file-viewer.md<br/>the files they open"] --> S
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class V,S,O here
```

| File | Lessons on |
|---|---|
| [verification-and-evidence.md](verification-and-evidence.md) | Checks that caught bugs, false positives, honest claims, stale outputs |
| [review-site-ux.md](review-site-ux.md) | What the user wanted to see on the review site, and why (with a later CAN-project wheel-zoom follow-up, 2026-10-27) |
| [original-file-viewer.md](original-file-viewer.md) | Original-file identity, parser units and frames, cancellable loading, dependency and wheel evidence |

Each lesson follows the [lesson format](../README.md#lesson-format): a rule, the incident, a check and its source.
