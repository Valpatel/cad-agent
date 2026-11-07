# A current repository does not make an old CAD export current

## Observed on 2026-11-07 UTC

The owner reported a hanging battery and an obsolete tall turret on the cad-agent website homepage after the
README cinematic had been released. Inspecting `tools/site/assets/models/gyropup.json` showed source
`b79896a446cc57391fcd3707c0b898b6f80d2f3d` (2026-11-02), 33 visible groups and 118,300 triangles. The matching
poster visibly retained that layout. The homepage and README were separate consumers.

The existing showcase producer read committed `exports/robot/*.step` through `export_view`, then stamped the
checkout's HEAD into the model record. A clean newer checkout alone could therefore relabel old exported geometry.
The current Gyropup README's accepted native extraction constructs 233 source parts, but its saved scene is only
a 2D projection. Neither the old STEP snapshot nor reverse-projecting that scene supplies a current 3D model.

Fleet job 240 then constructed the current main collector: 233 source parts, 33 visible groups, 116,672 triangles
and 390,479 packed bytes, with all source/stat/hardware guards unchanged. Comparing actual old/new bounds showed
the turret frame top drop from 520.5 to 434.5 mm, but battery bounds remained exactly
`[-153, -43.5, -219.04, 153, 43.5, -122.04]` mm. Gyropup issue 193's last owner checkpoint explicitly said the
front/rear holder work had not started beyond survey notes. The battery complaint was an unfinished product
change, not another stale export. [Native artifact review](https://github.com/Valpatel/cad-agent/pull/425#issuecomment-6704549724).

## Corrective rule

Refresh the actual consumer's asset set from current constructor shapes. Reuse the product's conservative source
closure, hardware-tree check, pinned CAD runtime and tracked J501 snapshot; use a fresh derived cache and preserve
all tracked product files. Pack the real meshes with the existing viewer tool, retaining the original named group
membership and explicit interior/fastener omissions. Bind the model, binary, poster and project-card hashes to one
record so a mismatched attractive poster cannot pass as a model update.

The existing model consumer must check those relationships as well as decode geometry, bounds and size. Keep
historical FEA illustrations and their source labels separate. Record actual native execution and visual acceptance
on issue #422's implementation PR before claiming the stale homepage has been corrected.

## Limits

This establishes displayed CAD provenance, not physical fit or strength. Bought hardware may still be modeled
envelopes in the product source. A source-matched export may expose design problems; do not hide geometry to improve
its appearance or claim all illustrations are current because the homepage model was regenerated.
A current-source match also does not prove a requested design change was implemented: compare the relevant geometry
and check the product issue. Keep that unfinished work open rather than hiding it in a presentation-only export.
