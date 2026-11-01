**New**
- Site: the build draws every Mermaid diagram itself, in headless Chromium through Playwright, and writes the finished
  `<figure class="cad-diagram" data-state="ready">` into the page (`tools/site-diagrams.mjs`). Pages no longer move
  while they load: the worst layout shift on a page with a diagram falls from 0.58 to 0.012, against Google's "good"
  limit of 0.1. Diagrams show without script, and no page downloads Mermaid to draw them. Output is the same bytes for
  the same source, theme, Mermaid and kit, and is cached in `.cache/site-diagrams/`. With no browser, or with
  `--client-diagrams`, the build warns and leaves the diagrams to the reader's browser; `npm run deploy:site` still
  deploys (#132).
- Web kit: `drawDiagram(source, {theme, id, fontFamily, mermaid})` in `diagrams.js` draws one diagram ahead of time and
  returns the finished figure. `observeDiagrams` keeps such figures as they are, and draws one again only when the
  page's theme is not the one it was drawn in (#132).

**Changed**
- Web kit: the sideways-scroll hint is sized by `diagrams.css` from the drawing's width (`--cad-diagram-w`) and the
  figure's, so it shows when it should without script and nothing moves when the script runs. `.cad-diagram` is now a
  size container (`container-type: inline-size`), and the source in the disclosure is `pre.cad-diagram-source` (#132).

**Projects must change**
- Nothing is required. Projects with a copied kit can rerun `cad-agent webkit <dir>` to get `drawDiagram`. A
  `.cad-diagram` placed where its width depends on its content (a float, an inline-block, a shrink-to-fit cell) now
  needs a width of its own, because a size container does not take its width from its children (#132).
