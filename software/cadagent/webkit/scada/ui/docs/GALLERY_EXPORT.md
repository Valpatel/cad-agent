# SVG gallery export

`tools/webkit/scada/ui/generate-gallery.py` exports canonical component artwork as self-contained SVG images. It owns `img/symbols/`, `img/states/`, `img/README.md` and `metadata/gallery.json`. The neighboring thumbnail generator owns JPEG captures under `img/thumbnails/`; model scenario captures belong to `scada-sim/img/`.

Gallery paths follow the library's equipment hierarchy. Animated artwork uses
`img/symbols/<category>/<type>/{default|variant}.svg`; selected state comparisons
use `img/states/<group>/<type>--<sample>.svg`. Static equipment captures use
`img/thumbnails/equipment/<category>/<type>/{default|variant}.jpg`, while real
viewer/workspace captures live in `img/thumbnails/workspace/`. Each populated
folder has a generated README; variants stay beside their type rather than in
one unbounded variants directory. Resolve exact paths from the manifests instead
of constructing a path from a display name.


The exporter calls the same public renderer used by applications. It copies the rendered SVG artwork and instance-scoped IDs unchanged, adapts HTML wrappers to SVG groups, and draws native SVG labels/readout rows from the renderer's gauge output. The adapter has no model, timer, external resource, `foreignObject` or image script. The card is a fixed illustrative state; CSS supplies decorative motion. It is not another equipment implementation.

CSS is parsed by the declared development dependency `rrweb-cssom` and by Chromium. Browser-native selector matching retains rules relevant to that fixed state; computed animation names retain their keyframes. Conditional rules retain relevant selectors, including reduced-motion overrides. Original declaration source is written to the output. Chromium's `CSSRule.cssText` can lose a `var()`-based shorthand when a later longhand overrides it, so its serialization is never used for output. A focused regression test protects this case. Parser type/selector disagreement, unsupported rule kinds, unsupported import syntax and external/circular CSS dependencies stop the export.

This is deliberately a fixed-image exporter, not a general CSS optimizer. A future rule whose animation identity depends on a new media condition needs exporter review and browser parity checks. Unsupported constructs must fail explicitly rather than silently losing artwork. All CSS references stay within the package, and the output retains no stylesheet import or web font dependency.

From the workspace root, run `npm --prefix tools/webkit/scada run gallery:generate` after source changes and `npm --prefix tools/webkit/scada run gallery:check` for read-only freshness. `--output /tmp/scada-gallery-study` creates a package-shaped study without replacing the committed gallery. `npm --prefix tools/webkit/scada run qa:gallery` compares image-mode renders with the full stylesheet, checks active and reduced motion, and saves screenshots for inspection. Generate only after the shared artwork is stable; the exporter rejects a source change during generation.

Development requires Node, the root's exact `rrweb-cssom` dependency, Python Playwright and Chromium. Pillow is used by visual QA. Runtime consumers need none of those tools; the package `files` allowlist ships the images and metadata, not the exporter or tests.

GitHub Markdown uses ordinary relative `<img>` references. A raw SVG browser test does not prove GitHub README behavior; release verification records the actual rendered GitHub image URL separately. Static image renderers remain useful, and the standalone component/viewer examples provide interactive controls.
