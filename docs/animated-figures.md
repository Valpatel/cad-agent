# Animated figures from real CAD

The README's hero is not drawn by hand. `tools/readme_anim.py` makes it from a real project's files:
- the STEP assembly, drawn as edges by hidden-line removal;
- the linkage's kinematics, solved from link lengths measured in the CAD;
- clearances from the assembly gates' relation engine;
- stress bands from the project's own FEA field.

It writes one SVG of about 100 KB that animates with CSS alone, so GitHub shows it in a README `<img>`.

The first figure is [Gyropup](https://github.com/Valpatel/gyropup)'s five-bar leg (MIT): `docs/img/hero/gyropup-leg.svg`. The SVGs in `docs/img/hero/` may be reused on the site and elsewhere. Each one names its source in its caption and `<desc>`.

## Regenerate or check

```bash
PYTHONPATH=src python3 tools/readme_anim.py            # write every SVG from its committed scene
PYTHONPATH=src python3 tools/readme_anim.py --check    # exit 1 if a committed SVG differs or breaks a rule
```

`tests/test_readme_anim.py` runs `--check`, so a renderer change that alters a figure fails CI until the SVG is regenerated and committed.

Rendering needs only cad-agent's core dependencies.

## Re-measure from the project

```bash
PYTHONPATH=src python3 tools/readme_anim.py --extract hero --source <checkout of the project>
```

Extraction needs the `cad` extra (CadQuery). Use a clean checkout of the project's published branch, not a working tree with uncommitted changes. The scene records the commit and every input file's sha256.

The clearance sweep is slow, because each pair is an exact `relate()` call (#186). Its result is reused from the committed scene while the assembly, the parts, the linkage and the clearance spec are unchanged. Pass `--fresh` to run it again. Gyropup's leg takes about 25 s without the sweep.

## Make one for another assembly

Copy `tools/anim/gyropup-leg.yaml`, then add the figure to `FIGURES` in `tools/readme_anim.py`. The spec names:
- **the assembly**: one STEP, one solid per part.
- **the parts**: solids by their number in the STEP. Each part has:
  - the body it moves with;
  - an explode distance along the joint axis;
  - a style;
  - optionally a part file whose volume the solid must match. If the STEP is rebuilt and its solids are renumbered, extraction fails instead of drawing the wrong part.
- **the linkage**: a planar one.
  - Joints are measured from coaxial solids, and the link lengths are checked against the design's.
  - The solve order says which joints are found from which.
  - The driven joint follows a path.
  - Four-bars driven by an output point, five-bars and chains of dyads all fit (`cadagent.publish.anim.linkage`).
- **the view**: a direction and an up vector. Set the stage box in pixels.
- **the FEA field**: optional, a `cadagent-fea-viewer` v1 file (what `cadagent.fea` writes for the viewer), with the stress bands as fractions of strength.
- **the words**: the wordmark and tagline, drawn as outlines because an `<img>` loads no fonts. Labels and captions sit under `present`, so they can change without re-extracting.

A different kind of figure (a board into its enclosure, print layers, a convergence chart) gets its own scene module next to `cadagent.publish.anim.hero`. It reuses the shared parts:
- edge projection: `cad`;
- the rasteriser and outlines: `raster`;
- paths, timeline, theme and the embed rules: `svg`;
- text outlines: `text`.

## What a figure must pass

`cadagent.publish.anim.svg.problems()` lists what makes an SVG unsafe or unfit to embed. Each rule has a test that breaks it:
- at most 250 KB;
- well-formed XML;
- no `<script>`, `<foreignObject>`, `<iframe>`, `<image>`, `<use>` or `<a>`;
- no event-handler attributes;
- no `href`, `src`, `url()` or `@import` pointing outside the document;
- `role="img"` with an `aria-label`, and a `<title>`;
- CSS animation only, no SMIL;
- a `prefers-reduced-motion` rule that stops every animation. The still it leaves is the final frame.

Both colour schemes are in the one SVG (`prefers-color-scheme`), on its own background. It was checked on github.com in WebKit and Chrome at 1440 and 390 px. At phone widths the words beside the drawing are hidden and the check marks are enlarged.

## What it approximates

- **Hidden lines.** Each solid hides only its own edges. Solids hide each other by their filled silhouettes, painted back to front in an order taken from depth rasters.
- **Motion.** Each moving solid is drawn in slices along the joint axis. Each slice is moved by an exact rotation at its own depth. The scene records the largest error over the visible surface, per part. For Gyropup's leg it is about 1 px. The hidden lines stay those of the reference pose.
- **Clearance.** It is checked at sampled poses, not as a swept volume.
- **Stress.** The colours show the FEA's surface field, capped at its design stress. The numbers shown are the FEA's own.

CAD and simulation narrow a design down. They do not prove that a printed part fits or holds.
