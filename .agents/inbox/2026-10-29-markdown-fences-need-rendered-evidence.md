# A Mermaid fence is source, not a rendered diagram

On 2026-10-29 a product's “How Gyropup is engineered” page exposed its Mermaid definition. A production Chromium probe found one visible `code.language-mermaid`, zero article SVGs and zero diagram scripts. Its custom Markdown builder had a heading renderer but no diagram runtime. The generic toolkit only asserted transformed `<pre class="mermaid">` markup and used a CDN start-on-load snippet, so those tests did not establish rendering or recovery.

Corrective rule: ship a pinned renderer and initialize it on the actual generated consumer pages; observe later Markdown insertions rather than relying on a one-time load event. Require rendered SVG geometry/labels and hidden default source in Chromium and WebKit. Exercise multiple diagrams, phone containment, the page's actual light/dark surface, held/failed runtime loads, retry and a malformed graph beside healthy graphs. Keep failures visible and preserve source in an optional disclosure.

Limits: diagram source semantics still need engineering review. Browser rendering does not verify the design, the fidelity of an architecture diagram, or its physical claims. The shared helper's theme is selected when a block is inserted; arbitrary external theme toggles require a caller-managed remount.
