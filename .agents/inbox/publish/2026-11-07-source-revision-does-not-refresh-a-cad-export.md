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

## Repeat the source check after a later product release

Issue #104's next finite refresh follows Gyropup main `01d5823062ace26eddd7d13428cbbfeec9e0105d`
and its [actual publication acceptance](https://github.com/Valpatel/gyropup/pull/256#issuecomment-6710253796).
The recorded closure now contains 95 inputs and hardware tree `d9e2577430dd831bc70cb7a43f24b56f63df7bee`;
the existing model producer and pinned/current packer remain byte-identical to the accepted route above.
This source change requires genuine new construction, not a new revision field on the old meshes.

Preparation checks the exact model-only helper path for historical Git-object requirements before spending
native time. Its input guard hashes current files and its hardware guard reads `HEAD:hardware`; a separate
README refresh CLI's historical reads are not part of this producer. Run the unchanged source preflight before
installation and native work, retaining a missing-object failure rather than substituting a stale source.
Optional timing tools must not prevent the actual producer from starting.

Fleet job 255 failed before CAD when its quiet product fetch reached a 180-second limit, shortened from the
prior accepted 240 seconds. The owned group and three descendants were killed and reaped; no model was made.
Its empty transfer log does not identify a network, server or pack cause. Preserve that failed receipt.
The separately reviewed correction restored 240 seconds and retained transfer progress. Job 256 on cpu-b
then fetched the product in 31.49 seconds and constructed CAD in 121.51 seconds; that does not prove what caused
255 to stall. [Actual native acceptance](https://github.com/Valpatel/cad-agent/issues/104#issuecomment-6710880452)
verified all 13 phases, three unchanged source snapshots, 95 inputs and the exact two-file archive. The new
model has 233 source parts, 33 visible groups, 116,672 triangles and 390,485 packed bytes under the unchanged
400 KiB binary budget. Membership and recorded part bounds match the earlier model; the unpacked payload has
319 differing bytes. This is genuine new construction, without a claim of a dramatic layout change.

The existing headless renderer generated the matching poster/card with a fresh HOME and a bounded owned
user-service cgroup. Detached browser and preview children must be quiescent before checking the five-file
set. Check all tracked hashes and full untracked-aware Git status, not only an expected subset. Preserve the
historical SOURCE prefix and engineering pictures; change only the banner's binding to the actual new model.
Battery bounds remain unchanged. Gyropup #193, broad #104 capability coverage, physical qualification and
actual public release acceptance retain their separate criteria.
