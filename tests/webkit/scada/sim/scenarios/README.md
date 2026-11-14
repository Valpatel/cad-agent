# tests/webkit/scada/sim/scenarios

SCADA regression fixtures and tests; source packages remain independently usable.

```mermaid
flowchart TD
  A["Library source"] --> B["Focused tests"]
  B --> C["Contract evidence"]
```

| File or folder | Purpose |
| --- | --- |
| [scada-agriculture-scenarios.test.mjs](scada-agriculture-scenarios.test.mjs) | Agriculture resource conservation, branch isolation and observation identity. |
| [scada-plant-operations.test.mjs](scada-plant-operations.test.mjs) | Connected wastewater, winery and brewery overview routes, instrument readings, valve isolation, PLC/I/O loss and deterministic sessions. |
| [scada-scenarios.test.mjs](scada-scenarios.test.mjs) | Complete catalog coverage, runnable definitions, shared views and commands. |

[Runtime library map](../../../../../software/cadagent/webkit/scada/README.md) · [Parent map](../README.md)

Run this group from the repository root: `node --test --test-concurrency=2 tests/webkit/scada/sim/scenarios/*.test.mjs`. Install development dependencies first with `npm ci --ignore-scripts --prefix tools/webkit/scada`.
