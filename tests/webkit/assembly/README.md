# Assembly guide tests

Strict data, reversible states and real multipart rendering for the optional [guide](../../../software/cadagent/webkit/assembly/README.md).

```mermaid
flowchart TD
    U["guide.test.mjs<br/>bad data + asset failures"] --> G["assembly/guide.js"]
    B["browser.mjs<br/>actual multipart scene"] --> V["viewer.js + stage.js"]
    V --> G
```

| File | Coverage |
|---|---|
| `__init__.py` | Empty test-package marker |
| `guide.test.mjs` | Pure validator/controller and bounded request counterexamples |
| `playback.test.mjs` | Explicit order, absolute authored poses, bounded timing, pause/loop/navigation and ownership rejection |
| `browser.mjs` | Real scene/material/coordinate/loading/lifecycle controls in each browser engine |
| `release-browser.mjs` | Real extracted ZIP, two frozen fixtures/WIP, pinned local runtime, no-script fallback and corrupted entry/model/mesh controls |

Run through the existing site npm scripts. See the [feature test matrix](../../../docs/practice/assembly-guide-testing.md) for pending versus verified results.

[Browser tests](../README.md)

`ASSEMBLY_PLAN_ONLY=1` runs only the nine native serial-plan cases through the existing server and cleanup.
They cover the detailed and packed consumers, actual world-vertex witnesses, absolute seeks/reversal/reset,
mid-animation mini-button reversal, source-axis/order mutants, stale refusal and phone/reduced-motion controls.
Use an already installed Playwright runtime via `PLAYWRIGHT_BROWSERS_PATH`; no dependency install is required.
