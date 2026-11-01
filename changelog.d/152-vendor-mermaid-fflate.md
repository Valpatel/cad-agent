**Fixed**
- Web kit: vendored Mermaid 11.4.1 → 11.17.2, which clears its nine OSV advisories, among them the two label XSS
  (sequence-diagram KaTeX labels, GHSA-7rqq-prvp-x9jh; architecture `iconText`, GHSA-8gwm-58g9-j8pw), CSS injection,
  prototype pollution and the XY and Gantt chart infinite loops. A browser test now renders both XSS payloads and fails
  if either runs (it does on 11.4.1) (#152).
- Web kit file viewer: the 3MF loader's fflate 0.6.9 (three.js r160's copy) → fflate 0.8.3 from npm. 0.6.9's
  `unzipSync` loops forever on a crafted ZIP64 directory entry (GHSA-px8p-9vwx-vf98); a unit test feeds it that archive
  and requires an error within 5 s. The viewer's own ZIP layout check already refused that archive before the parser saw
  it; the fix covers any other code that imports the kit's `fflate.module.js`. Unzip filters now work as documented (#152).
- `vendor/mermaid/SOURCE.json` and `vendor/file-viewer-sources.json` record each package's npm URL, integrity and file
  SHA-256s; `tests/webkit-vendor.test.mjs` checks the files and the notices against them (#152).

**Projects must change**
- Projects with a copied kit: rerun `cad-agent webkit <dir>` (and rebuild sites made with `cad-agent site`) to ship the
  fixed files. Diagrams keep Mermaid 11's layout and theme; Mermaid 12 (ELK layout and a new default look) is not taken.
