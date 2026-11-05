# Research

Find what already works, read the source, then promote only what the evidence supports.

The arrows show the route from discovery to a tested reusable method.

```mermaid
flowchart TD
    L["landscape.md<br/>find existing tools"] --> R["references/<br/>read + cite sources"]
    R --> P["process-profiles.yaml<br/>encode scoped rules"]
    P --> C["../src/cadagent/<br/>apply the rule"]
    C --> T["../tests/<br/>worked examples + defects"]
    T --> S["../skills/<br/>when to use it"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class L,R,P here
    class C,T,S near
```

| Evidence | Files and use |
|---|---|
| Reference registry | [Core sources](references.yaml), [shards, evidence ladder and promotion procedure](references/README.md); one id space, not one confidence level |
| Tools to adopt or wrap | [Landscape](landscape.md) and [data](landscape.json), [agent toolkits](agent-toolkits-2026-10.md), [upstream registry](../vendor/upstreams/registry.yaml) |
| Process rules | [Profiles and limits](process-profiles.md), [rule data](process-profiles.yaml); unread rules cannot drive checks |
| Compliant mechanisms | [Survey](compliant-mechanisms.md) → [snap-fit method](../docs/compliant.md) |
| Simulation | [Tools](simulation-tools.md), [FEA/process survey](fea-and-process-tools.md) → [toolkit](../docs/toolkit.md) |
| Sheet metal | [Survey](sheet-metal.md), [guides](sheet-metal-guides.md), [joining](sheet-metal-joining.md), [parts data](sheet-hardware.yaml) |
| Review practice | [Design workflows](design-workflows.md) and [data](design-workflows.json) → [pitfall checks](../docs/common-issues.md) |
| Supply chain | [Dated report](security-report.md), [machine report](security-report.json), [accepted findings](security-accepted.yaml); regenerate rather than hand-edit reports |
| Benchmarks | [Gate timing script](bench/gate_timing.py); timings describe its selected cases and environment |

`cad-agent rules <feature>` serves scoped rule cards; `cad-agent choose joining --load N` starts a joining decision. [Profiles and card limits](process-profiles.md) explain the inputs, source confidence and gaps; the cards are generated from the rule data, not copied into this map.

`python -m cadagent.review.references --check` checks registry consistency and citation/evidence rules. It does not verify every source claim or prove a physical result. The [existing evaluation paths and limits](../lessons/process/2026-11-05-recovery-audit.md#evidence-that-can-improve-the-toolkit-today) distinguish deterministic regression checks from the planned model-comparison framework.

[Home](../README.md) · [Guides](../docs/README.md) · [Skills](../skills/README.md) · [Lessons](../lessons/README.md)
