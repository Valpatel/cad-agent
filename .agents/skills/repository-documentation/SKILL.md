---
name: repository-documentation
description: Use when maintaining cad-agent folder maps, source-owned diagrams, reference/skill navigation or the generated SCADA gallery and scenario documentation.
license: UNLICENSED
metadata:
  requires: "node npm"
  optional: "scada-browser"
  optional-for: "SCADA browser capture and visual verification"
---

# Maintain navigable source documentation

> **Needs:** `node` 22 or newer and `npm`; Python Playwright and local Chromium for SCADA browser capture and visual verification. `cad-agent agents install` says which of these this computer lacks. Without Python Playwright and local Chromium, skip that step; without the rest, do not use it.

Use the maintained cad-agent checkout. Read the [repository map](../../../docs/map.md)
and the affected owner’s scoped instructions before editing. Follow [work tracking](../cad-work-tracking/SKILL.md),
[independent review](../cad-pr-review/SKILL.md) and [supply-chain review](../cad-supply-chain/SKILL.md)
where applicable; this skill adds no separate approval process. Runtime APIs and
source-owned generators are authoritative.

Read the repository [structure rules](../../../AGENTS.md),
[README style guide](../../../docs/practice/style-guide.md), and affected owner map.
The repository's existing map/compiler is authoritative; do not add a parallel
README inventory or a second canonical guide.

1. Find the actual source owner and readers. Distinguish authored source, generated
   metadata/images/pages, installed runtime and immutable release receipts. Fix
   the owner/generator, not a copied site page or provenance hash.
2. Review the hierarchy as a GitHub reader before and after each change. Give every
   populated owner a concise README, useful dependency picture, file/child table,
   parent link and relevant preview. Group real domains as they grow; no empty
   toolkit folders or generic root asset bucket. Preserve source history on moves.
3. Link API/format guides beside their library; user workflows live under docs/;
   canonical skills under .agents/skills; studied references under their current
   research/registry owners. Tools/tests have explicit domain homes. Keep each
   library's img/ integral. Distinguish illustrative icons, topology and captured
   viewer images; none alone proves model accuracy or live state.
4. Use compact diagrams for meaningful dependencies. Process topology uses its
   equipment-symbol SVG generator, not a tall list of Mermaid boxes. Render actual
   changed diagrams through the target site compiler and inspect reading size.
5. Preserve package-local links in portable docs. Links to source-only tools/tests
   should name cad-agent's canonical source when those files are excluded from an
   exported package. Never depend on the historical SCADA repository. Keep private
   machine paths/credentials out of maintained guides and historical receipts intact.
6. Regenerate only the affected owners:

   ```sh
   node tools/site/compiler/site-repo-map.mjs --write
   node tools/site/compiler/site-repo-map.mjs --check
   python -m pytest -q tests/repo/test_areas.py tests/repo/test_layout.py tests/repo/test_skills.py
   npm --prefix tools/webkit/scada run docs:scenarios
   npm --prefix tools/webkit/scada run docs:scenarios:check
   npm --prefix tools/webkit/scada run gallery:check
   npm --prefix tools/webkit/scada run topologies:check
   ```

7. Register new guides/skills in docs/areas.yaml and the actual existing catalogue
   and installer. The map checker inspects the current source inventory, including
   untracked additions. Re-run relevant site/diagram suites;
   Python map checks alone do not prove rendering. A map's arrows must describe
   actual imports/outputs, or be explicitly labelled a proposal.
8. Report executed checks, visually inspected figures and unresolved scope. A
   reference record may be catalogued or studied; a locally cloned resource may
   still be unpinned. Do not promote those states merely because a link is present.

The [local-use guide](../../../docs/practice/scada/local-use.md) explains source and
runtime consumers. [Resources and growth](../../../docs/practice/scada/resources-and-growth.md)
keeps reference metadata, mirrored bytes and source ownership distinct.

[Skill map](README.md) · [All skills](../README.md) · [Retained terms](../../../software/cadagent/webkit/scada/LICENSE.txt)
