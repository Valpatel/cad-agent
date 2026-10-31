# Lessons — process

How the agent works with its sources, the user and a long session.

```mermaid
flowchart TD
    Src["the board's sources"] --> V["verify-from-source.md"]
    User["the user"] --> U["user-intent-and-requirements.md"]
    V & U --> A["agent-process.md<br/>the session itself"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class V,U,A here
    class Src,User near
```

| File | Lessons on |
|---|---|
| [verify-from-source.md](verify-from-source.md) | Confirm board facts from schematics, photos and models, not from assumptions |
| [user-intent-and-requirements.md](user-intent-and-requirements.md) | How the requirements evolved, and the user's corrections |
| [agent-process.md](agent-process.md) | Mid-turn messages, status, consent, prior art, scope, delegation |

Each lesson follows the [lesson format](../README.md#lesson-format): a rule, the incident, a check and its source. Back to [all lessons](../README.md).
