# Contributing to SCADA UI

Read [README.md](README.md), [STYLE_GUIDE.md](STYLE_GUIDE.md) and the relevant [API](docs/API.md) / [system contract](docs/SYSTEM_FORMAT.md). The [component skill](https://github.com/Valpatel/cad-agent/blob/dev/.agents/skills/scada-component-authoring/SKILL.md) and [agent prompts](AGENT_PROMPTS.md) give repeatable authoring tasks. This private package retains its existing terms; packaging does not grant a new license.

## Ownership

`software/cadagent/webkit/scada/ui/src/` is canonical. The cad-agent site compiler publishes those files under `/kit/scada/ui/`. Make changes in the source owner and regenerate derived data and images. The package export map points directly to domain implementations; do not add historical-path wrappers or copied runtime trees.

| Change | Owner |
| --- | --- |
| Type identity, states, ports, defaults and discovery | `src/catalog/registry.mjs`, `src/catalog/definitions/` and `src/catalog/discovery.mjs` |
| Equipment geometry and state motion | `src/symbols/`, with process/control art in `art/` and power equipment in `power/` |
| Dialogs, focus, toolbars and teardown | `src/workspace/` |
| System data and bindings | `src/contracts/`, `schema/` and [SYSTEM_FORMAT.md](docs/SYSTEM_FORMAT.md) |
| Diagram, camera and inspector | `src/viewer/` |
| Equations, simulation clock and fault state | [Model library](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/sim/README.md), with lifecycle owned by the host |
| Scenario selection, files and audio | [Explorer](https://github.com/Valpatel/cad-agent/blob/dev/software/cadagent/webkit/scada/explorer/README.md) |
| Portable symbol gallery and captures | Generated `img/` and provenance in `metadata/` |
| Development tools and checks | [Tools](https://github.com/Valpatel/cad-agent/blob/dev/tools/webkit/scada/ui/README.md) and [tests](https://github.com/Valpatel/cad-agent/blob/dev/tests/webkit/scada/ui/README.md), outside runtime packages |

Catalog and contracts must not import renderers, controllers or the host. Renderers receive state; they do not create a model, start timers or perform IO. Keep package-local imports self-contained so a packed package works without repository tooling.

## Implementation sequence

1. Inspect adjacent components and the state contract. State what is visual and what the model supplies; document assumptions and unsupported behavior.
2. Update metadata, geometry and scoped motion. Use unique instance IDs, escaped labels, accessible descriptions and reduced-motion states. JSON and bindings remain data.
3. Integrate through exported APIs and one shared model adapter. Preserve focus and in-progress input during updates. Destroying a view must not reset the external model.
4. Add focused tests for new behavior and failure cases. Synchronize derived schema and metadata when their inputs change.
5. Inspect actual browser renders at card, diagram and inspector sizes: inactive, low/mid/high, warning, fault, offline, open/closed, damage and repair as applicable. Inspect device-specific motion and retained inventory as well as status badges.
6. Regenerate affected gallery outputs and captures; verify the package exports and isolated consumer. Update folder maps and agent guidance with the resulting contract.

## Commands from the checkout root

```sh
npm --prefix tools/webkit/scada ci
npm --prefix tools/webkit/scada run build:schema
npm --prefix tools/webkit/scada run build:metadata
npm --prefix tools/webkit/scada run check:schema
npm --prefix tools/webkit/scada run check:metadata
npm --prefix tools/webkit/scada test
```

The source tests cover contracts, rendering, dialog lifecycle, camera interactions, model boundaries and packed consumers. Choose focused suites while editing; run the full relevant suite before a release.

With Python Playwright and Chromium installed:

```sh
python tools/webkit/scada/ui/qa/check-component-states.py --help
npm --prefix tools/webkit/scada run qa:viewer
npm --prefix tools/webkit/scada run gallery:generate
npm --prefix tools/webkit/scada run gallery:check
npm --prefix tools/webkit/scada run qa:gallery
npm --prefix tools/webkit/scada run thumbnails
npm --prefix tools/webkit/scada run thumbnails:check
```

Read each tool's `--help` for current flags. Browser receipts and computed bounds complement visual inspection; they do not establish readable geometry by themselves. For camera and shell changes check desktop, tablet, phone, touch, keyboard, reduced motion and Zoom to fit. Record which screenshots were inspected.

The gallery exporter uses canonical renderers. Samples live in [the tool owner](https://github.com/Valpatel/cad-agent/blob/dev/tools/webkit/scada/ui/gallery/README.md); the generator owns SVGs, Markdown indexes and hashes. Never paint over a generated screenshot or edit a receipt to accept a stale output. Scenario captures belong to `sim/img/`; every future toolkit owns its own gallery.

A browser-ready runtime package can be packed directly:

```sh
npm pack ./software/cadagent/webkit/scada/ui --pack-destination /tmp
```

A runtime tarball, full source checkout, generated website and live deployment are different artifacts. Follow the canonical repository release workflow for publication and report only the scopes actually verified. Historical release archives remain immutable records.

## Completion evidence

Report the API or visual change, canonical files and generated outputs, tests run, browser states inspected and remaining limitations. Preserve retained terms, the single source owner and candid model assumptions. See [GALLERY_EXPORT.md](docs/GALLERY_EXPORT.md) for exporter design and [state coverage](docs/STATE_COVERAGE.md) for recorded gaps.
