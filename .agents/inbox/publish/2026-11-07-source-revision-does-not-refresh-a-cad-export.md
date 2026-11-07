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
