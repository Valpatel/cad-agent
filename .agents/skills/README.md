# Skills

Short entry points into tested tools and repeatable engineering workflows. Open the skill for the task at hand.

The arrows mean that a skill directs an agent to existing code, evidence and checks; prose alone does not validate a technique.

```mermaid
flowchart TD
    S["SKILL.md<br/>when + how"] --> C["../../src/cadagent/<br/>engineering code"]
    S --> R["../../docs/research/<br/>sources + limits"]
    C --> T["../../tests/<br/>regression evidence"]
    T --> L["../../docs/lessons/<br/>what failed + why"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class S here
    class C,R,T,L near
```

| Task | Skill |
|---|---|
| Design a part from requirements through review | [design-process](design-process/SKILL.md) |
| Diagnose moving parts, pivots and coordinate frames | [cad-motion-validation](cad-motion-validation/SKILL.md) |
| Select real bought hardware and its CAD | [mcmaster-parts](mcmaster-parts/SKILL.md) |
| Check clinch hardware and riveted sheet-metal joints | [sheet-metal-hardware](sheet-metal-hardware/SKILL.md) |
| Audit dependencies, upstreams and resource safety | [cad-supply-chain](cad-supply-chain/SKILL.md) |
| Keep maintainer work recoverable | [cad-work-tracking](cad-work-tracking/SKILL.md) |
| Obtain independent review and answer findings | [cad-pr-review](cad-pr-review/SKILL.md) |
| Run sustained engineering jobs on compute hosts | [cad-remote-runs](cad-remote-runs/SKILL.md) |

`cad-agent agents install` links the kit into your harness and reports missing requirements; see [the workflow guide](../../docs/practice/agent-workflow.md) before applying maintainer workflows to a project. Skills stay in this folder so harness installation can discover them. New engineering techniques belong in the existing domain code and its tests, with a short skill only when a repeatable workflow needs one.

[Home](../../README.md) · [Guides](../../docs/README.md) · [Research](../../docs/research/README.md) · [Subagents](../agents/) · [Tests](../../tests/README.md)
