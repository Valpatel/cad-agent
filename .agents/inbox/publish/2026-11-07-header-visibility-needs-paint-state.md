# Check visibility separately from geometry, and retain the failed measurement

## Evidence — 2026-11-07 UTC

The actual WebKit consumer on release candidate `01e2a03b` failed in run
`42347308225`, job `128327736519`, with:

```text
header 320px dark: Dark theme extends outside the viewport
```

The independent specimen branch later reported the same error at `4976aed9`.
The other release WebKit job passed. Neither a passing sibling nor earlier source
reviews invalidates the failed application assertion. The existing header check
saved only a message, so its original rectangles and painted frame are unavailable.

Read-only component probes used a retained real site whose header CSS, theme script,
icon and Inter font bytes match the release source. Normal control boxes stayed
inside the viewport in 144 resize samples. A further 32 samples including the SVG
children also stayed inside. These local successes do **not** reproduce or explain
the failed CI frame.

## Consumer gap and correction

The visibility predicate checked rectangle size, computed visibility and ancestor
opacity, but did not check `display: none`. A nonzero rectangle alone cannot establish
that an SVG paints. The refined predicate explicitly checks display on the element
and its ancestors while preserving every visible-child rectangle, viewport limit,
four-pixel gap and required navigation control.

The existing test now exercises two complementary controls: an actually hidden icon
with a deliberately substituted stale rectangle, and an actually visible icon moved
outside the viewport. The first must be ignored; the second must be rejected. This
is a controlled consumer test, not a claim that the historical CI frame contained
that exact hidden-icon condition.

The browser artifact now keeps raw icon display/rectangle state, parent/control
rectangles, font status and screenshots at 320 pixels and at every failure. Future
failures can distinguish a painted layout problem from stale hidden geometry.

## Corrective rule and limits

Check whether content paints before interpreting its reported geometry. Keep paired
hidden and visible controls, and retain the original failure before changing a test.
Do not widen thresholds, skip the affected viewport or retry an unexplained failure
into acceptance. Component evidence does not replace the final built-site CI run;
the original CI cause remains unproven until actual captured state identifies it.

## Keep the requested viewport's paint with its measurement

On 2026-11-07, PR444 at `8a9f099c` failed WebKit run `42371996335`, job `128401855485`, with the same
320-pixel dark-theme message. This time the existing artifacts retained the actual failed state:

```text
320-dark.json: width 320, fonts loaded
wordmark left 18 / right 142.234375; theme control left 308.328125 / right 342.328125
320-light.json: wordmark left 12 / right 106.234375; theme control left 274 / right 308
```

The dark JSON has the preceding 390-pixel layout, but its PNG captured immediately afterward visibly paints
the fitting narrow header with its decorative mark hidden. This establishes a mismatch between the sampled
geometry and later paint; it does not identify the browser engine's internal cause or explain the older failures
whose rectangles were never retained. The failing 320-pixel case remains a failure, not an accepted sibling pass.

One independently reviewed local study compared the original two-frame sequence with an exact CSS viewport-query
barrier: 16 cases, zero failures in either group, four genuinely escaped/hidden controls rejected, no external
requests or page errors, owned browser and preview processes reaped. Thus it did **not** reproduce the CI error
or prove that a query barrier fixes it. The retained site was `7c15440`, not a full `8a9f099c` build; its header
template, theme/site scripts, icon and six font files matched, and its CSS differed only by an unrelated
installation-link selector absent from the catalogue page. Keep that component scope separate from whole-site CI.

The consumer now retains the pre-paint boxes and raw CSS/query state, captures one fixed viewport PNG, then
asserts the same strict geometry after that paint. It also asserts the requested width and matching CSS viewport.
Every one of the same 33 widths and both themes remains; every required control, visible-child rectangle,
viewport bound and four-pixel gap remains. Hidden-header, stale-hidden-icon and genuinely escaped-icon controls
go through the identical capture step and must still reject after paint. This is a fixed readiness contract,
not a geometry-based wait, retry until fit, increased timeout or changed application CSS.

Current full built-site CI in both engines remains the acceptance criterion. Local non-reproduction does not
clear a failed application assertion, establish the historical cause or qualify the rest of a release.

## Migrate the required primary destination without weakening visibility checks

**Evidence, 2026-11-12 UTC, #599/#600:** at `de39921b`, normal Chromium run43136002038/job130911380308 and the same run's WebKit final log rejected 88 header strings: 66 width/theme checks still required `nav a[href="/catalog"]`, 20 route checks still required a catalogue header link, and two hidden-icon baselines contained that same missing-link problem. The approved product header already used Explore at `/explore`. Auditing the complete final assertion found no unrelated error; the icon messages were contaminated baselines, not independent evidence of a new geometry defect.

**Correction and proof:** require the intended primary Explore destination while retaining the legacy catalogue route, all 33 widths, both themes, visibility checks, viewport bounds, four-pixel gaps, hidden-header cases and hidden/escaped-icon controls. Add a planted obsolete-primary-URL control, so a fitting header with the wrong destination still fails. The exact corrected header function passed 76 focused cases; visible-primary checks passed on 22 route/viewport pairs, including both `/explore` and `/catalog`. The owned capped unit completed in 28.2 seconds and was inactive with an empty control group.

**Related image-test assumption:** lazy strip images can be horizontally offscreen on phones. Bring each actual image into view before requiring complete/nonzero natural width, then restore both strip and page scroll before the initial-layout measurement. A separate bounded four-state image check passed, and a deliberately broken displayed asset was rejected. Product lazy loading and CSP were unchanged; no observed WebKit lazy-image defect is claimed. Its owned unit completed in 6.9 seconds and was inactive with an empty control group.

**Rule and limits:** update the intended navigation contract when a reviewed navigation change ships; do not restore obsolete UI, drop visibility/geometry requirements or infer a separate failure from a dirty baseline. These are focused Chromium proofs on the accepted unchanged UI producer, not a full-suite or cross-engine pass. Fresh normal CI in both engines and an independent exact-head review remain required.
