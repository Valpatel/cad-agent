**Changed**
- The home page leads with what runs: "See it run" sits under the hero, with Gyropup's turret playground first, then
  the two 3D viewers and cards that open `/toolkit` robot replay, SCADA and build-guide examples (#748).
- A new "What is in cad-agent" figure shows the stack as a layer cake of blocks, from the open source it is built on,
  through the libraries, simulators, checks and tests, web widgets and command-line tools, to knowledge and the agent
  kit. Counts (commands, skills, formulas, tests, references, …) are computed by the build; dashed blocks are planned
  and link their issue. The README, `index.md`, `llms.txt` and the page title say the same (#748).
- The checks reel keeps its animated tiles; three more checks stay one click away as text links. A "From frontier to
  local" section says what the evals measure today and what is next (#748).
- `/toolkit` example cards carry anchors (`/toolkit#robot-replay`, `#scada-simulations`, `#assembly`, …) (#748).

**New**
- `tools/site/figures/gyropup-turret.mjs` records Gyropup's turret browser playground from a clean local checkout into
  `docs/img/gyropup/turret-playground.webp` and a reduced-motion still, with its commit in `SOURCE.json`. It is a
  playground of a work-in-progress prototype, not physics validation (#748).
