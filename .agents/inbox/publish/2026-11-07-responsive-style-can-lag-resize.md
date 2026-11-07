# Read responsive styles after the resize event

On 2026-11-07 UTC, PR445 head `85a9dd94e2c49b20afc1fbb95471a7652561dd7a` failed the existing WebKit
`foldProblems` consumer in Actions run 42371564562: `1366 -> 360px: the fold the script opened for the wide
window stays open on the phone`. The original failure is retained in the [PR receipt](https://github.com/Valpatel/cad-agent/pull/445#issuecomment-6706923598).
Navigation JavaScript and CSS were unchanged by the documentation change; that did not invalidate the failure.

## Evidence and cause

A bounded Node 22 / Playwright 1.56.1 diagnostic served a retained site through the existing preview server, using
Chrome 151 and the existing WebKit 26 runtime. The served navigation source matched the failing head exactly:
JS SHA-256 `8bedae399a50ccbbc56516c3092c768357485365d62753d1ae6cb14b85acda77`; CSS
`f92ece30fa7c1142f4be93b34b192f102c3e4c30b17a626dade22bb8b6c091a0`.

The first sixteen cases used unchanged and instrumented source, four trials per engine/mode. The instrumented
copy only recorded values already read inside the real `fit` callback. Four WebKit cases failed the original
2000 ms close check. At the resize callback, `innerWidth` was 360 but the existing computed-style read still
returned `display: contents`, so `wide` was true. A later observation returned `display: block` while the fold
remained open. The eight uninstrumented cases passed locally; the original uninstrumented CI failure remains
separate evidence. Instrumentation changes timing, so the local frequency is not a user failure-rate estimate.

## Correction and controls

The product coalesces resize handling into one animation frame before reading the responsive style. Initial
setup stays synchronous, native reader-owned folds stay open, and an aborted/disconnected component ignores a
pending frame. No breakpoint, timeout or acceptance threshold changes.

A second bounded matrix used the retained old producer with the same tracing, corrected source, and corrected
source with tracing: four trials per engine/mode, 24 total. Three old-source WebKit cases reproduced the failure.
All sixteen corrected cases closed the automatic fold within the unchanged 2000 ms bound and preserved a
reader-opened fold through a wide/narrow round trip. These component controls do not replace whole current-head
browser CI or establish every device's behavior.

The existing whole-browser consumer also records the actual failed open-state observation, subsequent computed
state and subsequent screenshot separately. The existing CI artifact glob retains them; a later fitting paint
cannot erase the earlier failure. The adjacent vision diagram width failure is a separate authored-layout error:
wrap its label to fit the existing 1100 px column; do not enlarge the layout allowance.

**Rule:** a new viewport width does not prove responsive style has caught up during the resize event. Defer the
style-dependent product update to a frame, and verify native/user-owned state as well as automatic state. Preserve
failed observations before later paint; validate a timing fix with the old producer and the same actual consumer.
Do not generalize this navigation observation into an explanation of unrelated header failures without their own
evidence. See the [curated lesson](../../../docs/lessons/review/review-site-ux.md#read-responsive-styles-after-the-resize-event).
