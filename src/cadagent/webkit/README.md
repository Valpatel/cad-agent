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
| `stage.js` | `createStage(el, {height})`: renderer, orbit camera, control-room lighting, shadowed floor, grid, glow pad, `setSceneLight(0..1)`, `onFrame(cb)`, `setInsets({left,right,top,bottom})` (keep the model out from under overlay panels), `fitView(points)`. Metres, y up |
| `panel.js` | `section`, `slider`, `jointSliders`, `chips`, `toggle`, `readouts`: HUD panel controls; `collapsiblePanel(hud, panel)` (hide/show the side panel) and `overlayInsets(hud)` (pixels the overlays cover, for `setInsets`) |
| `face.js` | `createFace({palette})`: a canvas-texture cartoon face with eased expressions, blinks, gaze drift and talking; `faceGlyph(name)` for buttons. Palettes `warm` and `visor` |
| `fea-viewer.js`, `fea.html` | `mountFeaViewer(el, url)`: interactive FEA results from `cadagent.fea` `Study.export_viewer()`: the deformed part coloured by stress, stress/strength, local safety factor or displacement; a load-factor slider and a play ramp past first failure (black = past the strength); hot spots with the load at which each fails (click to fly there); held faces, load arrows, section cut, hover and pinned readouts. `fea.html?case=<json>` is the ready page (`&load=1.5&field=sf&spot=1&clip=x:0.4&panel=0` for links and screenshots) |
| `hud.css` | The skin: Valpatel design language (dark void, cyan hairlines, monospace telemetry) |
| `vendor/` | three.js r160 (+ OrbitControls, BufferGeometryUtils), Inter and JetBrains Mono |

## Credits

- Stage, face and HUD skin are adapted from the browser simulator in
  [mvalancy/moxie-robot-saver](https://github.com/mvalancy/moxie-robot-saver) (`sim/web/moxie/scene.js`,
  `sim/web/moxie/face.js`, `sim/web/css/hud.css`), MIT, © 2026 moxie-robot-parent-app contributors.
- three.js r160 (`three@0.160.0`), MIT, © 2010–2023 three.js authors. Unmodified.
- Inter (the Inter Project Authors) and JetBrains Mono (JetBrains), SIL Open Font License 1.1. Unmodified.
