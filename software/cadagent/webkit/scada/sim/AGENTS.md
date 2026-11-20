# Scope: software/cadagent/webkit/scada/sim

Read [the package map](./README.md), [source owners](./src/README.md),
[model API](./docs/MODEL-API.md) and [scenario map](./scenarios/README.md) before editing.
The repository [AGENTS.md](https://github.com/Valpatel/cad-agent/blob/dev/AGENTS.md) and [SCADA domain instructions](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/AGENTS.md) define the shared workflow and local boundaries.

- Keep the engine headless. Importing it starts no clock; hosts choose explicit
  stepping or the optional injected-timer `start`/`stop` lifecycle. Rendering,
  persistence, audio and browser-page lifecycle belong to hosts.
- Preserve explicit v1/v2 contracts. System JSON describes equipment and views;
  model JSON describes behavior and assumptions. Multiple views observe one
  model. Validate both documents and keep IDs and experiment recipes aligned.
- Parameters and placeholder responses remain editable and clearly illustrative.
  A connected symbol does not prove material balance, a protection interlock or
  a validated engineering model. Record unsupported behavior instead of inferring it.
- For measured-system calibration, equation replacement or an external engine,
  use the [model-adaptation guide](./docs/REAL_MODEL_ADAPTATION.md) and
  [agent skill](https://github.com/Valpatel/cad-agent/blob/dev/.agents/skills/scada-model-adaptation/SKILL.md). Identify the
  supported replacement boundary before coding; preserve units, observation
  validity, replay and the host's one-session lifecycle. New calibration evidence
  does not retroactively validate unrelated equipment or scenarios.
- New equipment equations belong in registered providers before changing shared
  family defaults. Keep `evaluate` pure and synchronous; advance owned JSON state
  only through the accepted-substep callback. Preserve explicit unit conversions,
  absolute supply/isolation gates, finite ledgers and provider/state identities.
  Model JSON selects registered code; it never supplies executable expressions.
  Test hot swaps, late-step failure rollback and exact compatible continuation.
- Every scenario folder owns a README mapping its actual files, model roles,
  focused views, assumptions and catalog experiments. Use the
  [documentation-maintenance skill](https://github.com/Valpatel/cad-agent/blob/dev/.agents/skills/repository-documentation/SKILL.md)
  and `node tools/site/compiler/site-repo-map.mjs --check` when adding or moving source or documentation.
- This package owns `img/`. Captured viewer JPEGs and schematic topology SVGs
  have different meanings. The Explorer capture tool owns the former; model
  development tools own the latter. Edit generators, never generated maps,
  image bytes or provenance hashes. Keep process maps compact and readable;
  use distinct equipment symbols rather than long columns of generic boxes.
- Regenerate topology SVGs with root `npm --prefix tools/webkit/scada run topologies:generate`; check them
  with `npm --prefix tools/webkit/scada run topologies:check`. Use `npm --prefix tools/webkit/scada run thumbnails:scenarios` only when
  capture inputs require new viewer images. Its validated `--indexes-only`
  mode refreshes prose without claiming a new screenshot capture.
- Keep source-only development links in shipped documentation pointed to the
  repository. Runtime npm distributions exclude tools/tests; source archives
  retain them. Package versions and published release archives are immutable
  release identities, not a reason to overwrite old archives after a docs edit.

For model changes run package `npm --prefix tools/webkit/scada test`, metadata checks and
`npm --prefix tools/webkit/scada run check:default-baseline`, then applicable
workspace integration/browser checks. For docs run `node tools/site/compiler/site-repo-map.mjs --check`, render
changed Mermaid through the site renderer, and inspect affected SVGs in a browser.
Report the actual checks, source scope and remaining limitations.
