# Current source and reuse audit

**Audit base:** cad-agent `33c3f51b574bdfa9171da62c4573beaf840daa95`.
The transfer candidate is SCADA release 9.3, source revision
`1360585c76987e79f1b36a35b04a19f387d32286`, with UI 1.4.1 and model 0.4.0.
These are provenance identifiers. All maintained source, documentation and tools
will move into cad-agent; no remote checkout is required by the proposed design.

This audit records source inspection. It does not report new target-runtime tests,
an installed SCADA integration or a completed engineering qualification. The
[contracts](contracts.md) and [migration plan](migration-and-validation.md) describe
proposed changes and the evidence needed to accept them.

## Browser components already present

Paths below are relative to the repository; line references describe the audit base.
Different viewers already share useful primitives, but several full-page assumptions
prevent them from safely becoming sibling panels in a workbench.

| Current source | Observed behavior | Consequence for integration |
| --- | --- | --- |
| [stage.js](../../../software/cadagent/webkit/stage.js), lines 24–32, 143–159, 203–247 | Container renderer, resize observer, fit/insets, frame subscriptions and disposal; used by ordinary assembly/STL, original-file and FEA viewers. | Retain as a proven **3D** primitive. Two-dimensional domains should not import Three.js for common controls. Its render clock is not the shared simulation clock. |
| [hud.css](../../../software/cadagent/webkit/hud.css), lines 19–35, 52, 112–117; [panel.js](../../../software/cadagent/webkit/panel.js), lines 117–125 | Global `html/body` styles, window-fixed `#app/#hud`, and inset calculations using the window and global `#app`. | Extract scoped tokens/controls separately from full-page layout; measure each host viewport. Preserve standalone shells. |
| [viewer.js](../../../software/cadagent/webkit/viewer.js), lines 15–35, 203–238, 336–348 | Ordinary assembly/STL-manifest mount (`createViewer`) has cancellation, cleanup, part-name selection, state callbacks and disposal. Returned state does not contain all camera/section state. | First real consumer of the proposed host adapter. Preserve domain instance identity; add explicit presentation capture instead of guessing state. |
| [file-viewer.js](../../../software/cadagent/webkit/file-viewer.js), lines 38–78; [file-loader.js](../../../software/cadagent/webkit/file-loader.js) | Request generations, abort, worker cancellation, failed-load preservation, theme/observer cleanup; readiness still writes to `document.body`. | Strong second consumer for lifecycle/loading/status extraction. Embedded readiness must be per instance, and cancellation must reach parsing. |
| [model.js](../../../software/cadagent/webkit/model.js), lines 168–188, 205–260, 363–413 | Poster-first lazy embed, error rollback and reduced-motion support; no disconnected-element lifetime or fetch abort. Deliberately leaves vertical touch scrolling to the page and has no wheel zoom. | Fix remove/reconnect/late completion before frequent host switching. Preserve document-embed interaction; a contained camera needs an explicit different policy. |
| [fea-viewer.js](../../../software/cadagent/webkit/fea-viewer.js), lines 73–83, 117–160, 760–778 | FEA result mount fetches without a mount-abort contract, injects global IDs/CSS and window-relative overlays; disposal exists after successful construction. | Adapt after the first host slice. Scope overlays and handle cancellation/partial allocation while preserving field, mesh, load and probe semantics. |
| [assembly/guide.js](../../../software/cadagent/webkit/assembly/guide.js), lines 26–60, 118–161 | Bounded asset reading and ordinary model validation live inside the assembly owner; other viewers import them. | Existing multiple consumers justify extracting generic IO and mechanical-document validation. Keep guide validation domain-owned and old exports compatible. |
| [assembly/guide.js](../../../software/cadagent/webkit/assembly/guide.js), lines 206–245; [playback.js](../../../software/cadagent/webkit/assembly/playback.js) | Guide controller owns one playback path and disposes its viewer. Steps and playback use absolute instance state and source-bound operations. | Specify renderer ownership before composition: closing guide controls must not destroy a host-owned renderer. Instructions are not a universal simulation model. |
| [part-tracker.js](../../../software/cadagent/webkit/part-tracker.js), lines 7–35 | Project/string-part checkbox persistence. | Procurement/build progress needs its own meaning and authority; it is not a revision-bound review comment or approval. |
| [diagrams.js](../../../software/cadagent/webkit/diagrams.js), lines 18–24, 55–57 | Mermaid document enhancement with horizontal scrolling. | Reuse rendered SVG where useful, but do not claim an interactive system graph already exists. A contained pan/zoom mode is a separate consumer. |

The first shared extraction should prove the ordinary assembly/STL and original-file viewers resize
and dispose independently, including cancellation during worker parsing. A second
handoff should exercise model-instance selection and assembly instructions against
real artifact identity. This establishes reuse before the SCADA domain drives new
host abstractions. Camera representations and solver APIs remain domain-owned.

## Runtime distribution and portable evidence

| Existing owner | Current behavior | Required migration work |
| --- | --- | --- |
| [pyproject.toml](../../../pyproject.toml), lines 48–49 | Package data includes `webkit/*`, `webkit/assembly/*` and `webkit/vendor/**/*`. | Admit nested runtime dependencies explicitly; verify the built wheel. A blanket recursive glob would also admit galleries and development files. |
| [cli.py](../../../software/cadagent/cli.py), lines 378–384 | `webkit` recursively merges the installed kit into a project. | Preserve the default and old URLs first. A later owned-file receipt may remove unchanged obsolete toolkit files, never unowned project files. |
| [release.py](../../../software/cadagent/publish/release.py), lines 589–604, 1098–1100 | Assembly exports capture the entire kit and hash every runtime file. | Resolve an assembly-reader dependency profile before adding SCADA. Extend the existing receipt rather than maintaining a second hash ledger. |
| [site.py](../../../software/cadagent/publish/site.py), lines 358–363, 684–692 | Static project sites copy a fixed Mermaid subset; the local server separately exposes installed files under `/_cadagent/kit/` with containment checks. | Use the same profile resolver for portable exports and preserve the server route. A local URL working does not prove offline completeness. |
| [build-site.mjs](../../../tools/site/build-site.mjs), lines 91–94, 675–708 | Public site copies all tracked kit files. CSP inspection recurses through HTML; canonical headers enumerate only immediate kit HTML files. | Separate runtime, optional gallery and example publication. Extend nested-page canonical handling when domain entry pages appear. |
| [tools/site/package.json](../../../tools/site/package.json), lines 6–13 | Test commands enumerate current file/folder patterns. | Register new nested suites explicitly; adding a test file alone does not run it in CI. |

A runtime profile must include transitive ESM, dynamic imports, CSS URLs, workers,
WASM/decoders, fonts and required notices. This is different from capability
metadata, project artifacts and the one-time transfer inventory. Source ownership
can include a library's integral `img/` gallery without placing its images in every
wheel consumer or assembly archive.

[guides.py](../../../software/cadagent/publish/guides.py), lines 54–104 and 129–182,
already captures exact bytes at preflight, enforces contained references and binds
guide/model/mesh identity. Retain this strong pattern; its assembly schema remains
specialized. The [installed-wheel smoke](../../../tests/cli/test_init.py), lines
145–249, builds from committed source, removes that source, verifies installed kit
bytes and performs a real ESM import. Extend it instead of testing only TOML text.
The [portable guide suite](../../../tests/publish/README.md) already has extracted
ZIP and removed-source consumer tests; those remain compatibility gates.

## Reports, domain formats and discovery

[report.py](../../../software/cadagent/publish/report.py), lines 200–232, reads
configured Boolean pass keys and optional evidence. Missing images can fall back
to a link to the result JSON. [evidence.py](../../../software/cadagent/review/evidence.py),
lines 21–44, verifies declared hashes but deliberately accepts legacy records that
omit them. New simulation receipts therefore need a strict versioned wrapper:
required input/config/provider/output identity, required captures and actual producer
success. This does not require invalidating all legacy reports.

[cli.py](../../../software/cadagent/cli.py), lines 74–102, runs `cad.steps[].run`
with the project's Python interpreter. A Node-backed model producer needs an explicit
Python wrapper with timeout and nonzero-exit propagation; pointing the field at a
JavaScript file is insufficient. Use existing `cad.checks`, `cad.html_pages`,
[publishing](../../../software/cadagent/publish/README.md) and
[simulation reports](../../../software/cadagent/simulation/simreport.py) where their
contracts fit. Do not reinterpret mechanical `all` as universal model validation.

| Domain | Existing capability | Boundary to preserve or add |
| --- | --- | --- |
| Mechanical | Packed/original-file 3D viewing, geometric checks, assembly playback, FEA and analytical calculators. | CAD millimetres/z-up, Stage metres/y-up, solver units and instance identities need explicit adapters. Exact BREP identity is platform-bound; tolerance-based geometry identity has different semantics. |
| PCB | [pcb.py](../../../software/cadagent/electrical/pcb.py) adapts KiCad ERC/DRC evidence; [pcb_routing.py](../../../software/cadagent/electrical/pcb_routing.py) measures routed copper without KiCad. | Reuse evidence and measurements. An interactive layer/net/component review viewer is additional work; KiCad remains the editor. CAD validity and production qualification remain distinct. |
| Electrical/panel and harness | [Area map](../../areas.yaml), lines 308–343, already reserves panels and harness at idea maturity; no shared viewer is established by this audit. | Plan terminal/pin/net/cable identities, explicit connections, layer/route visibility and revision-bound review. Do not claim importers or electrical solvers exist. |
| Build and review | Source-bound guide schema, project check/report pipeline, dossier and integrity gates. | Keep guide steps, procurement progress, comments, approvals and simulation commands separate even when their controls share a shell. |

Existing mechanical simulation is more than rendered playback:
[robot.py](../../../software/cadagent/simulation/robot.py), lines 1–17, exports CAD
millimetres into SI URDF/MJCF; [motion_trace.py](../../../software/cadagent/mechanical/motion_trace.py),
lines 1–10 and 60–66, checks independent motion intent in its declared assembly frame.
Do not let a shared presentation clock replace those engines or use the renderer as
its own validation oracle. Original-file loading currently covers STL/STEP/3MF,
not DXF, Gerber or KiCad boards. Footprint export/parser utilities are useful
existing tools, not evidence of a complete PCB review renderer.

The public catalog already owns stable identities and schema compatibility.
[site-catalog.mjs](../../../tools/site/compiler/site-catalog.mjs), lines 99–115,
uses `project` for outside open-source projects; do not silently redefine that kind.
Evolve existing [catalog](../../catalog.yaml) and [area](../../areas.yaml) inputs
for Toolkit capabilities and Explore design examples. New embeds must coordinate
[sanitizer](../../../tools/site/compiler/site-html.mjs), stylesheet/preload
registration in `build-site.mjs` and conditional boot in
[site.js](../../../tools/site/assets/site.js). A copied module alone does not integrate
an example into the public site.

## SCADA transfer candidate: implemented source, not target features

The release candidate separates model-free SVG/viewer components from headless
v1/v2 simulation engines. Its system, model and snapshot documents are distinct.
The viewer adapter offers `getSnapshot()`, `subscribe()` and optional `dispatch()`;
the host supplies session lifetime. Two views can observe one model. Preserve the
actual read-only behavior: the generic adapter omits dispatch, while the v2 adapter
retains a dispatch method that rejects writes.

Swappable equations are implemented in source, not merely described in a guide:
`PlaceholderSystemModel(..., {equationProviders})`, data-only versioned bindings,
and transactional `setEquationBindings()`. Trusted synchronous providers declare
engine/phase support, parameter/state schemas and versions. Evaluation is separate
from accepted-step state advancement; kernel allocation and hard limits remain
owned by the engine. Snapshot provider state includes identity and schema signature.
Atomic rejection/rollback and replay behavior must survive transfer.

The candidate contains original linear/quadratic centrifugal-pump providers and a
v2 resistive-heater provider, explicit SI-to-index conversions and editable assumed
parameters. These demonstrate equation replacement, not a calibrated plant model
or a general hydraulic/multiphysics network solver. External solver adapters remain
a separate integration boundary. Transfer the executable examples, negative tests,
model-adaptation skills and unit conventions together; importing artwork alone
would discard the capability this integration is intended to preserve.

The full reusable inventory includes 142 equipment types, 97 variants and 60
scenarios, plus source-owned galleries, generators, documentation and agent
procedures. These are inventory counts, not a claim that every equipment state or
physical behavior is complete. Preserve the recorded coverage gaps. The candidate
packages declare `private: true` and `UNLICENSED`; target redistribution terms and
asset provenance must be recorded before public inclusion under cad-agent's license.

## Reuse decisions and limits

| Candidate | Recommended disposition | Reason |
| --- | --- | --- |
| Existing webkit/Three.js viewers and controls | Reuse and adapt; extract proven common seams. | Real consumers, offline assets and regression suites already exist. No framework rewrite is justified by this audit. |
| Existing publishing, guide preflight and evidence owners | Extend with profiles and strict new receipts. | They already capture source-bound portable artifacts and retain failure information. |
| KiCad and existing PCB checks | Keep authoring external; add viewing/review adapters. | Layer review does not require recreating PCB editing or its design-rule engine. |
| GraphDone-style navigation | Study explicit artifact portals, return context and semantic LOD. | A logical graph can connect viewers without becoming their renderer, solver or coordinate system. Seamless transitions remain unselected. |
| Canonical agent kit | Extend [.agents/skills](../../../.agents/skills/README.md) and the existing installer/catalog. | Procedures must ship with real target-owned APIs, prerequisites and checks; a readable prompt alone is not an executed capability. |

Agent readiness also needs a concrete extension: [agentkit.py](../../../software/cadagent/agentkit.py),
lines 102–119, checks existing tool prerequisites and requires a source checkout;
it does not yet check Node/npm for SCADA. The [standard evaluation runner](../../../tools/evaluation/standard_eval.py),
lines 14–16 and 33–50, supports named existing graders, not SCADA tasks. Transfer
skills with target-local references and real readiness checks; qualify a bounded
positive/negative SCADA grader before claiming an autonomous task was evaluated.

Before implementation, capture baseline archive membership and repeat actual browser
consumer checks. Later acceptance must cover independent sibling disposal, contained
pan/zoom/Fit, offline closure, stale/invalid identity, one SCADA clock and transfer
operation without the old repository. Commands and ordered gates belong to the
[migration and validation plan](migration-and-validation.md).

[Design map](README.md) · [Integration plan](integration-plan.md) · [Contracts](contracts.md)
