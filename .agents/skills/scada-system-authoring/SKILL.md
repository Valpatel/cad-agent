---
name: scada-system-authoring
description: Use when defining a SCADA process, adding an example simulation, composing multiple layouts over one model or integrating a supported model adapter.
license: UNLICENSED
metadata:
  requires: "node npm"
  optional: "scada-browser"
  optional-for: "SCADA browser capture and visual verification"
---

# Author a shared SCADA system

> **Needs:** `node` 22 or newer and `npm`; Python Playwright and local Chromium for SCADA browser capture and visual verification. `cad-agent agents install` says which of these this computer lacks. Without Python Playwright and local Chromium, skip that step; without the rest, do not use it.

Use the maintained cad-agent checkout. Read the [SCADA owner map](../../../software/cadagent/webkit/scada/README.md)
and scoped instructions before editing. Follow [work tracking](../cad-work-tracking/SKILL.md),
[independent review](../cad-pr-review/SKILL.md) and [supply-chain review](../cad-supply-chain/SKILL.md)
where applicable; this skill adds no separate approval process. Runtime APIs and
source-owned generators are authoritative.

1. Read the [system format](../../../software/cadagent/webkit/scada/ui/docs/SYSTEM_FORMAT.md),
   [model API](../../../software/cadagent/webkit/scada/sim/docs/MODEL-API.md) and
   [integration guide](../../../software/cadagent/webkit/scada/sim/docs/INTEGRATION.md).
   Start with an existing scenario of the required version. Name stable equipment,
   ports, variants, flows, views, observed quantities, sources and unknowns.
2. Keep `system.json`, `model.json`, runtime snapshots and view/camera state
   separate. Use `validateSystemDefinition()` and
   `validatePlaceholderModelDefinition()`; JSON Schema shape alone does not check
   referenced ports, bindings and circuit topology. Preserve versioned formats.
3. Explicitly choose v1 compatibility or v2 circuit behavior. V2 declares resource
   circuits, fluids, finite stocks, supply/conversion boundaries and thermal links.
   A line drawn between symbols does not create a physical or electrical connection.
4. Keep all guessed values labelled and editable through validated model controls.
   Record units, source/measurement identity, assumptions and excluded behavior.
   Normalized example indices remain illustrative even if the display uses an
   engineering unit label. Use [model adaptation](../scada-model-adaptation/SKILL.md)
   when equations or an external engine must change.
5. Mount all layouts against one model/adapter. The host owns one clock, loading,
   persistence, sound and destruction. A view only subscribes. Read-only v1 adapters
   omit dispatch; v2 read-only adapters reject dispatch. Express both as unavailable
   controls, and test that observation never advances or resets the model.
6. Add `sim/scenarios/<id>/{system,model}.json` and its entry in authored
   `sim/scenarios/index.json`. Keep the canonical host in
   [explorer/](../../../software/cadagent/webkit/scada/explorer/README.md).
   Scenario maps and topology/capture galleries are generated; update their facts
   and owning tools, never the generated Markdown or provenance hashes directly.
7. Test idle/run at different loads, at least one fault/repair and resource boundary,
   rejected command and version-compatible snapshot continuation. A failed restore
   leaves the prior state intact and starts no clock. Compare both views to the
   model, rather than checking only that a button changed colour.

   ```sh
   npm --prefix tools/webkit/scada test
   npm --prefix tools/webkit/scada run check:default-baseline
   npm --prefix tools/webkit/scada run docs:scenarios
   npm --prefix tools/webkit/scada run docs:scenarios:check
   npm --prefix tools/webkit/scada run topologies:generate
   npm --prefix tools/webkit/scada run topologies:check
   npm --prefix tools/webkit/scada run thumbnails:scenarios
   npm --prefix tools/webkit/scada run thumbnails:scenarios:check
   ```

8. Use [viewer review](../scada-viewer-review/SKILL.md) for branches, direction,
   readable labels, equipment dialogs, pan/zoom and Fit at desktop/phone sizes.
   Preserve the frozen baseline's original scope when adding a new scenario; the
   new example gets its own behavioral tests instead of rewriting history.
9. Report actual source/model/provider versions, assumptions, cases, replay
   evidence and missing physics. A topology SVG and a paused JPEG are useful
   previews; neither proves live interaction or engineering qualification.

[Skill map](README.md) · [All skills](../README.md) · [Retained terms](../../../software/cadagent/webkit/scada/LICENSE.txt)
