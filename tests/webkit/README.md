# tests/webkit

Node and browser tests for [`software/cadagent/webkit/`](../../software/cadagent/webkit/README.md), the browser pieces.
`*.test.mjs` run under `node --test` with no browser; `*-browser.mjs` drive Chrome or WebKit through Playwright; the
rest are helpers they import.

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    U["webkit-*.test.mjs<br/>node --test"] -->|"imports"| K["software/cadagent/webkit/<br/>*.js"]
    B["webkit-*-browser.mjs<br/>Playwright"] --> S["webkit-server.mjs<br/>serves the kit"]
    S --> K
    V["fixtures/<br/>formula-vectors.json"] --> U
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class U,B,S here
    class K,V near
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `webkit-diagrams-browser.mjs` | Real diagram lifecycle/themes/math, hostile labels, and advisory boundaries on hash-bound emitted sanitizer/math inputs |
| `webkit-fan-curve.test.mjs` | `<cad-fan-curve>` without a browser: every setting gives a point on both curves |
| `webkit-file-corpus.mjs` | Parses a bounded manifest of published originals with the real workers (run by hand) |
| `webkit-file-geometry.test.mjs` | `file-geometry.js`: mesh normalising and model and STL validation |
| `webkit-file-theme-browser.mjs` | Helper: the file viewer's themes in a browser (imported by the file-viewer suite) |
| `webkit-file-theme.test.mjs` | `file-viewer-theme.js`: theme normalising |
| `webkit-file-viewer-browser.mjs` | The original-file viewer in a real browser, on `fixtures/file-viewer/` |
| `webkit-file-worker-node.mjs` | Helper: runs the shipped parser workers in Node, without a browser |
| `webkit-formulas.test.mjs` | `formulas.js` against the golden vectors the Python writes |
| `webkit-fourbar.test.mjs` | `<cad-fourbar>`'s pure parts in Node |
| `webkit-gallery.test.mjs` | `<cad-gallery>`'s pure parts: URL state, search, facets and sorting |
| `webkit-model.test.mjs` | `model.js`, the `<cad-model>` decoder, against the Python reference |
| `webkit-part-table-browser.mjs` | The part table in a real browser |
| `webkit-part-tracker.test.mjs` | `part-tracker.js`: statuses per project, atomic imports, storage denial, cross-tab sync |
| `webkit-printed-boss.test.mjs` | `<cad-printed-boss>` without a browser, against `cadagent.mechanical.bosses` |
| `webkit-server.mjs` | Helper: serves `software/cadagent/webkit/` for the browser suites |
| `webkit-torsion-snap.test.mjs` | `<cad-torsion-snap>` without a browser: the port's numbers, Saint-Venant scaling |
| `webkit-vendor.test.mjs` | The kit's vendored libraries match their receipts |

Run: `node --test tests/webkit/*.test.mjs` and `npm --prefix tools/site run test:part-table`, `test:file-viewer`, `test:diagrams`.
Before the diagram browser suite, run `npm --prefix tools/mermaid ci --ignore-scripts` with Node 22. The suite checks
that the direct library regression modules match the actual emitted input hashes in the committed build record;
missing or different inputs fail rather than skip. Its inert template and inherited-trust controls exercise the
libraries' nondefault advisory boundaries, separately from default strict-renderer exploitability. CI installs this
maintainer context separately; production website builds do not install it.

Related: [tests](../README.md) · [where files go](../../.github/CONTRIBUTING.md#where-files-go)
