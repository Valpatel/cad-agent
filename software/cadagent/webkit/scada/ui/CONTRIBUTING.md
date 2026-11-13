# Contributing to SCADA UI

Start with [README.md](./README.md), [STYLE_GUIDE.md](./STYLE_GUIDE.md) and the relevant API/system-format documentation. Use [AGENT_PROMPTS.md](./AGENT_PROMPTS.md) when handing work to another agent. This package is a private local package, not a published npm release; its manifest does not grant a new open-source license.

## Edit the canonical source

`packages/scada-ui/src/` is the source of truth. The website's matching files under `dist/client/packages/scada-ui/` are a generated package projection. Do not edit a copied module or stylesheet and leave the package behind.

From the repository root:

```sh
npm run build:schema
npm run build:library
npm run check:schema
npm run check:library
```

The schema build derives type, variant and state choices from the canonical registry; update its generator for structural schema changes. The library build regenerates `packages/scada-ui/metadata/components.json`; the workspace site build projects the package under `dist/client/packages/scada-ui/`. Checks are read-only and fail when generated output is stale. Add new public modules deliberately to the package entry and export map. The site package projection mirrors the declared publish allowlist, including stable flat entries and nested runtime modules/styles. New implementation code belongs in its existing domain; add a public facade only when an actual compatibility or API contract requires it. The build removes stale modules only inside package-owned output domains. It never overwrites unrelated application styles. Keep installed-package imports self-contained; an installed tarball must not need a script or dependency from `../../`.

Consumers do not need this repository's build workflow. A file dependency or packed tarball contains browser-ready ES modules, CSS and metadata.

The flat public and historical entry files are facades. Follow [the source map](./src/README.md) to their implementation owners; do not put new implementation into a facade.

## Choose the correct layer

| Change | Owner / location |
| --- | --- |
| Equipment identity, states, ports, defaults | `src/catalog/registry.mjs` and `src/catalog/definitions/` |
| Ordinary equipment geometry | Renderer helpers in `src/symbols/components.mjs` |
| PLC/network geometry | `src/symbols/art/control.mjs` |
| Existing twin illustrations | `src/symbols/art/twin.mjs`, `src/symbols/art/twin.css` |
| Standalone state styling and motion | `src/symbols/components.css` |
| Dialog, focus, toolbar and workspace lifecycle | `src/workspace/workspace.mjs`, `src/workspace/workspace.css` |
| System definitions and bindings | `src/contracts/system-definition.mjs`, `schema/scada-system.schema.json`, [SYSTEM_FORMAT.md](./docs/SYSTEM_FORMAT.md) |
| Generic layout/view controller | `src/viewer/viewer.mjs`, `src/viewer/viewer.css`; [viewer API](./docs/API.md#viewer-api), with application logic in the adapter |
| Process equations, equipment faults, plant clock | Host application/model, outside this package |
| App catalog behavior | `apps/digester/src/catalog/`, composed by the application |
| Portable image gallery | Generated `img/symbols/`, `img/states/`, Markdown indexes and `metadata/gallery.json` |
| Static equipment / UI captures | Generated `img/thumbnails/`, with `metadata/thumbnails.json` |

Add meaningful tests for new states, invalid input, behavior or lifecycle. Avoid tests that merely repeat a hardcoded implementation list. Preserve existing type IDs and state semantics unless a deliberate versioned migration is part of the requested change. Do not introduce a second model instance per view.

## Implementation sequence

1. Inspect neighboring components and the relevant style/API contract. State what is visual and what the external model must supply.
2. Add or change typed metadata, then geometry and state styling. Use unique instance IDs and escaped accessible labels. Never evaluate JSON or binding expressions as code.
3. Integrate through the public entry points and a host adapter. Preserve the active controls and focus when values update. Route teardown must not reset an externally owned model or clock.
4. Add focused tests for the behavior and failure cases, then synchronize generated files.
5. Render in Chromium and inspect the changed equipment at card, preview and system-view sizes. Verify normal, inactive, warning, fault, offline, disconnected/open states as applicable, and numeric endpoints.
6. Regenerate thumbnails for visible changes, update the README map and examples, and verify packaged imports/assets. Summarize actual checks and remaining limitations.

## Checks in this repository

Install development dependencies once with `npm ci`. For library changes, run the workspace Node suites with:

```sh
npm run build
npm test
npm run check:generated
```

The package suite exercises actual `npm pack`, offline installation, public exports and stylesheet dependencies. The component/workspace suites cover metadata validation, unique SVG IDs, accessibility, dialogs and lifecycle. Viewer/system suites should cover the public schema, bindings, command dispatch, external updates and teardown as those layers change. Run `npm test` before a release or when a change affects the app/model boundary.

With Python Playwright and Chromium available:

```sh
npm run qa:component-states -- --static-root dist/client --output work/component-states
npm run qa:app-components -- --static-root dist/client --output work/components-browser
npm run thumbnails
npm run thumbnails -- --check
```

The state check evaluates real animation and status behavior. The catalog check uses visible controls, clipboard, downloads and a before/after plant snapshot to verify isolation. Review the screenshots; passing computed bounds alone is not a visual review. Test phone, tablet and desktop widths when layout changes. Use the focused workspace/live-view checks when changing the viewer, shared shell or live artwork adapter.

The thumbnail generator owns all equipment images, workspace/viewer examples, state exemplars, the contact sheet and `metadata/thumbnails.json`. Regenerate from the current canonical source after syncing it. Do not manually paint or crop generated images to hide a rendering defect. A changed count/type name requires corresponding README and manifest updates. Read the generator's `--help` for its actual current options rather than inventing flags.

Root release packaging is separate from an ordinary source edit:

```sh
npm run package:library
npm run qa:components
```

Run the standalone-kit check using its documented arguments for the current environment. An npm tarball, a standalone browser ZIP, the full app source ZIP and a live Site deployment are different outputs. Do not claim one updates another automatically.

## Completion report

Report the component/API changes, canonical and generated files touched, tests actually run, screenshots inspected, thumbnail/metadata freshness and package verification. Distinguish a visual-state preview from physics, and local candidate checks from live publication. Do not publish a package or deploy a Site merely because its local checks passed; release actions follow the user's authorized task.

## Gallery maintenance

The [package-owned gallery](./img/README.md) is part of the reusable package and its distribution allowlist. Add new types/variants to the canonical registry; the exporter discovers them automatically. Selected comparisons in `scripts/gallery/samples.json` demonstrate distinct visual states, while each descriptor remains the full editable state contract. The SVG exporter must never redraw a second copy of equipment geometry.

Run `npm run gallery:generate`, `npm run gallery:check` and `npm run qa:gallery`; regenerate static captures with `npm run thumbnails` and verify `npm run thumbnails -- --check`. The gallery generator accepts `--output work/gallery-study` for a separate candidate and refuses to replace outputs if source changes while it runs. Do not hand-edit SVGs, generated category indexes, source hashes or image hashes. The exporter has a declared development-only CSS parser and browser checks for full-stylesheet parity; see [its design notes](./docs/GALLERY_EXPORT.md).

Use relative Markdown links within the owning package. Keep scenario captures in `scada-sim/img/`, not in this artwork package. Browser previews, npm tarballs, GitHub README rendering and live publication are distinct validation targets; report only the ones actually checked.
