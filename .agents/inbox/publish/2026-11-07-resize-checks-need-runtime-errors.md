# Resize checks need runtime errors from the page they resize

On 2026-11-07 UTC, the actual v0.26.1 public consumer failed on WebKit while resizing `/docs/toolkit`: `ResizeObserver loop completed with undelivered notifications.` The actual document returned HTTP 200 at the expected revision `02cbc3c9cef53ef34a97fb24c14a133499af91ec`; the loaded navigation script matched released bytes. Request, HTTP and CSP errors were absent. Sixteen no-JavaScript cases and the Chromium navigation case completed; the second public domain and final checks were never reached. [Original failure](https://github.com/Valpatel/cad-agent/issues/450#issuecomment-6707822239).

The existing `foldProblems` resize page and copy-layout sweep had no `pageerror` listener. Errors collected on other pages could not cover these separate browser contexts. Good geometry and a later quiet paint therefore could pass while the tested interaction emitted an error.

## Evidence and limits

- The first local diagnostic stopped before acquiring any browser: it incorrectly required `kit/copy.css`, although the real copy component embeds its stylesheet in `copy.js`. The failed preflight was retained and only the asset assumption was corrected.
- One corrected local replay retained all 16 original/component-removal/observer-trace cases, two trials in each engine. Every action completed with zero runtime/request/HTTP errors. The source stayed clean and both owned browser processes and the preview process exited. Receipt SHA-256: `947a97cadfcc1fd7aacdf26b82146566802aa8812f9df883f2daa550262a18b7`.
- That non-reproduction does not clear the actual public error. Component removal and instrumentation change timing. Observer traces point at the copy component and show synchronous changes to room styles and overflow attributes during delivery, but do not establish the historical warning's cause.

## The existing copy consumer exposed the error

The next finite diagnostic used the actual released copy-layout consumer, preserving its six mouse/touch widths, 41 planted boundary columns, copied labels, late button stylesheet and overlap checks. The page list was restricted to the saved actual toolkit document. Unfiltered runtime listeners were attached before navigation. The source and served static assets stayed bound to the released revision.

On 2026-11-07 UTC, `timeout --signal=TERM --kill-after=15s 180s node cad450-copy-consumer-diagnostic.mjs` completed all twelve contexts. WebKit emitted the same error at both 768 px touch and 1366 px mouse, where the existing planted/late-style scenarios run. All geometry checks passed. Chromium's six contexts were quiet. The diagnostic exited zero because its purpose was to retain findings, not to declare product acceptance; its receipt contains those two errors. All owned processes exited and source readback stayed clean. Receipt SHA-256: `5b33db45f70d79a425b9f8c4e56f24e9c7c2bc13719af5acebb33f846e997ff2`.

The copy component synchronously calls `fit()` during observer delivery; that operation can change the observed boxes through padding or the widest-label measurement. The correction coalesces only observer-triggered fitting onto the next animation frame. Initial, font-ready and pointer-mode measurements remain unchanged, as do the no-overlap and exact-copy contracts. Both existing consumer pages now collect unfiltered runtime errors and retain them with state and subsequent paint. Paired old/new validation and publication acceptance remain pending at this checkpoint.

This reproduces the error class in the existing copy consumer; it does not establish the exact timing of the earlier public navigation failure. The [Resize Observer draft's delivery algorithm](https://drafts.csswg.org/resize-observer/#deliver-resize-loop-error) reports an error when observations are skipped. No exception is added for it.

## Corrective rule

Collect unfiltered runtime errors before navigation on the exact page that performs the interaction. Keep the original errors, observed state and subsequent screenshot separately; a later successful frame cannot erase an earlier error. Test real copy behavior and navigation actions without relaxing geometry or reader-choice requirements. A deterministic scheduling control may demonstrate and prevent a feedback hazard, but must not be described as reproducing an unexplained historical failure.

## Boundaries

Local checks are not publication acceptance. Keep issue450 and the release acceptance open until the correction passes independent review, normal CI and an actual reviewed public consumer. No error whitelist or unchanged public retry is a substitute.
