**Changed**
- The home page names cad-agent's two layers: a new stack figure shows the shared components (3D viewers, reports,
  BOMs, exploded views and build guides, simulators, deterministic checks) under agent skills and evals, each with its
  maturity from `docs/areas.yaml`. The 3D viewers move up into "See it run", with robot replay, SCADA and build-guide
  cards that open their `/toolkit` examples, and a new "From frontier to local" section says what the evals measure
  today and what is next. `index.md`, `llms.txt`, the page title and the README say the same (#748).
- `/toolkit` example cards carry anchors (`/toolkit#robot-replay`, `#scada-simulations`, `#assembly`, …) (#748).

**New**
- `tools/site/figures/gyropup-turret.mjs` records Gyropup's turret browser playground from a clean local checkout into
  `docs/img/gyropup/turret-playground.webp` and a reduced-motion still, with its commit in `SOURCE.json`. It is a
  playground of a work-in-progress prototype, not physics validation (#748).
