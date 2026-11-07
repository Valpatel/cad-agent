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
