**Fixed**
- The home page's 3D Gyropup, its poster and its projects card show the current robot (two five-bar legs, the P3
  body, the turret), not the retired serial leg. The card is now made by `tools/site-model-poster.mjs` and recorded
  in `docs/img/gyropup/SOURCE.json` (#331).
- `cadagent.publish.view.export_view`: a part's `bounds_mm` is the solid's box, measured before meshing, not the box
  enlarged by the mesh's deflection (up to 1.4 mm at 0.8 mm tolerance) (#331).
