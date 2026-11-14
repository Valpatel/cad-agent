---
name: scada-component-authoring
description: Use when adding or repairing a SCADA equipment symbol, variant, visual state, animation, schema entry or its reusable gallery preview.
license: UNLICENSED
metadata:
  requires: "node npm"
  optional: "scada-browser"
  optional-for: "SCADA browser capture and visual verification"
---

# Author a SCADA component

> **Needs:** `node` 22.22.2+, 24.15.0+, or 26+ and `npm`; Python Playwright and local Chromium for SCADA browser capture and visual verification. `cad-agent agents install` says which of these this computer lacks. Without Python Playwright and local Chromium, skip that step; without the rest, do not use it.

Use the maintained cad-agent checkout. Read the [SCADA owner map](../../../software/cadagent/webkit/scada/README.md)
and scoped instructions before editing. Follow [work tracking](../cad-work-tracking/SKILL.md),
[independent review](../cad-pr-review/SKILL.md) and [supply-chain review](../cad-supply-chain/SKILL.md)
where applicable; this skill adds no separate approval process. Runtime APIs and
source-owned generators are authoritative.

1. Read the [style guide](../../../software/cadagent/webkit/scada/ui/STYLE_GUIDE.md),
   [state coverage](../../../software/cadagent/webkit/scada/ui/docs/STATE_COVERAGE.md)
   and [public API](../../../software/cadagent/webkit/scada/ui/docs/API.md). Inspect
   the relevant existing family. Record references and distinguish original art,
   measured/source-derived properties and illustrative geometry.
2. Give the type/variant a stable ID and explicit supported state fields in the
   [catalog owner](../../../software/cadagent/webkit/scada/ui/src/catalog/README.md).
   Place SVG implementation in the relevant symbol family. Keep catalog/contracts
   independent of rendering, and keep the UI independent of models and host policy.
3. Design a recognisable silhouette and state matrix: off/on, zero/low/normal/high
   output, disconnected/unavailable, open/closed, warning, damage and recovery as
   relevant. Off does not imply empty, cold or depressurized. Show retained stock,
   heat and leakage when supplied. Colour and animation supplement readable labels.
4. Use shared artwork/animation helpers; inspect small cards, full diagram and
   equipment inspector. Distinct devices need distinct silhouettes. Repeated SVGs
   need collision-free IDs. Reduced motion retains status and meaningful state.
5. Add a simple model mapping or explicit unsupported-behavior statement in the
   [model registry](../../../software/cadagent/webkit/scada/sim/src/model-registry.mjs).
   Do not smuggle physics into SVG code. Equation changes use
   [model adaptation](../scada-model-adaptation/SKILL.md).
6. Extend focused [UI tests](../../../tests/webkit/scada/ui/README.md) and affected
   model/scenario cases. Test actual damage-only state, healthy → failed → repaired,
   unavailable observations and numeric bounds. A changed class name is not proof
   of motion or correct state meaning.
7. Run the owning generators and checks from the repository root:

   ```sh
   npm --prefix tools/webkit/scada run build:schema
   npm --prefix tools/webkit/scada run build:metadata
   npm --prefix tools/webkit/scada test
   npm --prefix tools/webkit/scada run gallery:generate
   npm --prefix tools/webkit/scada run gallery:check
   npm --prefix tools/webkit/scada run thumbnails
   npm --prefix tools/webkit/scada run thumbnails:check
   ```

8. Follow [viewer review](../scada-viewer-review/SKILL.md) for actual motion,
   controls, focus and contained camera behavior. Preserve the library-owned
   [img/ gallery](../../../software/cadagent/webkit/scada/ui/img/README.md), including
   previews for every added type and variant. Generated metadata/hashes are outputs;
   repair their owner rather than patching freshness receipts by hand.
9. Update local maps/API/state coverage and report exact executed checks, inspected
   states, source identity and limits. Use [documentation maintenance](../repository-documentation/SKILL.md)
   for hierarchy and browseability. Existing coverage is not fresh proof for changed art.

[Skill map](README.md) · [All skills](../README.md) · [Retained terms](../../../software/cadagent/webkit/scada/LICENSE.txt)
