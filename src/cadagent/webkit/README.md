# cad-agent web kit

Browser pieces for showing a robot or mechanism: a lit 3D stage, a control-room HUD skin, panel controls and an
expressive face. Plain ES modules, no build step, works offline.

```bash
cad-agent webkit designer/kit      # copies this kit into your project (re-run to update)
```

```html
<link rel="stylesheet" href="kit/hud.css">
<script type="importmap">{"imports": {"three": "./kit/vendor/three/three.module.min.js",
                                      "three/addons/": "./kit/vendor/three/addons/"}}</script>
<div id="app"></div>
<div id="hud"><header id="topbar">…</header><main id="stage-overlay"></main><aside id="panel"></aside></div>
<script type="module">
  import { createStage } from './kit/stage.js';
  const stage = createStage(document.getElementById('app'), { height: 0.7 });  // robot height in metres
  stage.root.add(myRobotGroup);
  stage.onFrame((t, dt) => { /* animate joints */ });
  stage.start();
</script>
```

| File | What it gives you |
|---|---|
| `stage.js` | `createStage(el, {height, zoomSpeed = 0.25, dragZoomSpeed = 1})`: renderer, orbit camera, control-room lighting, shadowed floor, grid, glow pad, `setSceneLight(0..1)`, `onFrame(cb)`, `stop()`, `dispose()`, `setInsets({left,right,top,bottom})` (keep the model out from under overlay panels), `fitView(points)`. Metres, y up |
| `panel.js` | `section`, `slider`, `jointSliders`, `chips`, `toggle`, `readouts`: HUD panel controls; `collapsiblePanel(hud, panel)` (hide/show the side panel) and `overlayInsets(hud)` (pixels the overlays cover, for `setInsets`) |
| `face.js` | `createFace({palette})`: a canvas-texture cartoon face with eased expressions, blinks, gaze drift and talking; `faceGlyph(name)` for buttons. Palettes `warm` and `visor` |
| `fea-viewer.js`, `fea.html` | `mountFeaViewer(el, url)`: interactive FEA results from `cadagent.simulation.fea` `Study.export_viewer()`: the deformed part coloured by stress, stress/strength, local safety factor or displacement; a load-factor slider and a play ramp past first failure (black = past the strength); hot spots with the load at which each fails (click to fly there); held faces, load arrows, section cut, hover and pinned readouts; `dispose()` to re-mount. `fea.html?case=<json>` is the ready page (`&load=1.5&field=sf&spot=1&clip=x:0.4&panel=0` for links and screenshots) |
| `copy.js` | `<cad-copy>`: a one-click copy button on any command, config or prompt block (`<cad-copy><pre>…</pre></cad-copy>`, or `text="…"` to copy something other than what is shown). "Copied" feedback, screen-reader announcement, a select-and-press-Ctrl+C fallback, no dependencies; `enhance(root)` wraps every `<pre>` on a page you do not generate |
| `nav.js`, `nav.css` | `<cad-nav>`: a page tree for long docs. On wide screens it is a sticky column with the current page's outline, marking the section being read (also in a right-hand "On this page" column via `rail="selector"`), plus a filter. On narrow screens it is one toggle. Write the tree, toggle, filter and outline as HTML and link `nav.css` in `<head>`: the first paint is then final, and it all works without script (`aria-label` text is never parsed as markup). Without that markup the script builds the toggle, filter and outline itself |
| `model.js`, `model.css` | `<cad-model src="model.json">`: a whole assembly in 3D on any page, from a model packed by `cadagent.publish.view.pack_view` (welded, 16-bit, gzip: Gyropup's 58 parts are 312 KB). Put a still `<img class="cad-model-poster">` inside and give the element an `aspect-ratio`: the poster is the first paint, and three.js and the model load only once the page has loaded, the element is near the screen and the browser is idle (behind a button with Save-Data on). Drag to turn, part names on hover, Explode and Pause buttons; it turns slowly unless the reader prefers reduced motion. `snapshot(w, h)` renders a still (the poster); works under a strict CSP (no import map, no inline script) |
| `gallery.js`, `gallery.css` | `<cad-gallery>`: tabs, facets, search and sorting over cards the page already wrote, for a catalogue or a parts library. Tabs are links upgraded to ARIA tabs (arrow keys); facets are checkboxes or links matched against each card's `data-<name>` tokens, with counts of what each choice would leave; every choice is a URL parameter, so a view can be shared and Back works. The overview shows the first `limit` cards per group (the page marks the rest, so the first paint is final); a filter sheet for small screens (modal, Escape, focus returned); covers that move on hover, focus or in view, never under reduced motion. Without script every card shows, grouped; chips and labels are text, never markup |
| `hud.css` | The skin: Valpatel design language (dark void, cyan hairlines, monospace telemetry) |
| `vendor/` | three.js r160 (+ OrbitControls, BufferGeometryUtils), Inter and JetBrains Mono |
| `formulas.js`, `formulas-data.js` | The browser port of `cadagent.formulas` (snap arm, cantilever curve and strain profile, four-bar Grashof class, angles, transmission angle and input limits), SI units, tested against the Python on golden vectors (`tools/formula_vectors.py`); printed filaments with their modulus and allowable strain by print direction (generated, do not edit) |
| `cantilever.js`, `cantilever.css` | `<cad-cantilever>`: an interactive snap-arm explorer. Sliders and the material and print direction drive a beam that bends along its computed curve, coloured by strain, with root strain, force and pass/fail. Link the CSS in `<head>` (it reserves the size, so nothing moves) and put a still `<img>` inside as the fallback; keyboard and screen-reader labelled, reduced motion respected, `drawCantilever()` for static figures. The equations and their sources are on the site's Engineering formulas page (`docs/formulas.md`) |
| `fourbar.js`, `fourbar.css` | `<cad-fourbar>`: an interactive four-bar linkage. Sliders set the crank, coupler, rocker and ground; the crank turns, or rocks and stops where the linkage locks, on the open or crossed assembly with the other one dashed, the coupler point's path drawn, the Grashof class, and the transmission angle charted over the input's travel against 40°. Link the CSS in `<head>` (it reserves the size) and put a still `<img>` inside as the fallback; keyboard and screen-reader labelled, reduced motion respected, light or dark from the page's color-scheme, `drawFourbar()` and `drawChart()` for static figures. Rigid links on ideal pins, position only. The equations are on the site's Four-bar linkages page (`docs/linkages.md`) |

## Zoom sensitivity

The shared stage zooms the wheel (and a trackpad pinch, which arrives as ctrl+wheel) at `zoomSpeed: 0.25`, four wheel increments over the previous single-increment distance, and middle-button drag and touch pinch at `dragZoomSpeed: 1`. Small trackpad deltas remain continuous. Pass `{zoomSpeed: 1}` for the earlier wheel sensitivity. Zoom limits, orbit and pan are unchanged. The vendored OrbitControls carries one local patch: the wheel delta is normalised by 100, not by the integer device pixel ratio (which was 0 below a ratio of 1).
The model viewer and FEA viewer inherit the shared default. Projects with copied kits must rerun `cad-agent webkit`;
`cad-agent site --serve` uses the installed toolkit directly (restart after updating it).

## Credits

- Stage, face and HUD skin are adapted from the browser simulator in
  [mvalancy/moxie-robot-saver](https://github.com/mvalancy/moxie-robot-saver) (`sim/web/moxie/scene.js`,
  `sim/web/moxie/face.js`, `sim/web/css/hud.css`), MIT, © 2026 moxie-robot-parent-app contributors.
- three.js r160 (`three@0.160.0`), MIT, © 2010–2023 three.js authors. Unmodified.
- Inter (the Inter Project Authors) and JetBrains Mono (JetBrains), SIL Open Font License 1.1. Unmodified.
