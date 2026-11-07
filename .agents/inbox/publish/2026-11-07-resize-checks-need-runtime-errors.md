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

The copy component synchronously calls `fit()` during observer delivery; that operation can change the observed boxes through padding or the widest-label measurement. The correction coalesces only observer-triggered fitting onto the next animation frame. Initial, font-ready and pointer-mode measurements remain unchanged, as do the no-overlap and exact-copy contracts. Both existing consumer pages now collect unfiltered runtime errors and retain them with state and subsequent paint. The initial source checkpoint left paired validation and publication acceptance pending.

This reproduces the error class in the existing copy consumer; it does not establish the exact timing of the earlier public navigation failure. The [Resize Observer draft's delivery algorithm](https://drafts.csswg.org/resize-observer/#deliver-resize-loop-error) reports an error when observations are skipped. No exception is added for it.

## Preserve a partial pass and a separate unexplained failure

A source-bound paired experiment at candidate `4df2d4c2fb1fba89979c2317a64f6bfd99398bc0` used the same refined consumer against released and corrected copy bytes. On WebKit, the consumer rejected both old late-stylesheet cases and passed all six corrected copy contexts plus the full navigation-fold consumer. This demonstrates the targeted component regression and the new error collector without weakening its existing geometry checks.

The **whole paired experiment failed**, exit 1. Both Chromium variants stopped at the 768 px planted-block `page.evaluate` with `Execution context was destroyed, most likely because of a navigation.` Neither finished its remaining copy widths; both navigation-fold runs passed. The receipt preserves that partial result (SHA-256 `489e7ab0d969d80a7a77cede56cccac40c1501e65a6696ddc37c98a55b4c09d7`). Owned processes exited, source stayed clean, and the deadline did not fire. The Playwright message alone does not prove a navigation or an infrastructure cause.

One separately reviewed, bounded Chromium-only diagnostic retained the same old/new 768 px copy actions and added navigation, console, crash, close, execution-context and evaluation-stage events. Both contexts completed with zero errors or geometry failures. Only initial document navigation/context replacement and deliberate close were observed; no events were dropped. Receipt SHA-256: `fc75fd2a716039392e46be1171bca96bc22267b8b2c3dc5a08c1267271f3a01c`. This is **non-reproduction**, with instrumentation and narrower scope; it does not repair or erase the failed broader run. Its original context-loss cause remains unknown.

The actual full CI at `4df2d4c2` independently ran the unchanged all-page website consumer with the new listeners in both engines: [Chromium](https://github.com/Valpatel/cad-agent/actions/runs/42381035843/job/128428505135) and [WebKit](https://github.com/Valpatel/cad-agent/actions/runs/42381035843/job/128428504843) passed. The routes/copy, fold, geometry, rendered diagrams, readability and other existing checks completed. CI uses its pinned browser distribution; it is not a reproduction of every installed Chrome 151 local condition. Final-head CI and actual corrective publication remain separate requirements; any recurrence stays blocking.

## Corrective rule

Collect unfiltered runtime errors before navigation on the exact page that performs the interaction. Keep the original errors, observed state and subsequent screenshot separately; a later successful frame cannot erase an earlier error. Test real copy behavior and navigation actions without relaxing geometry or reader-choice requirements. A deterministic scheduling control may demonstrate and prevent a feedback hazard, but must not be described as reproducing an unexplained historical failure.

## Boundaries

Local checks are not publication acceptance. Keep issue450 and the release acceptance open until the correction passes independent review, normal CI and an actual reviewed public consumer. No error whitelist or unchanged public retry is a substitute.


## A navigation-looking error can be a collected probe promise

**Observed, 2026-11-07 15:58 UTC:** The first actual v0.27.0 two-domain consumer stopped on the first domain's
Chromium 768 px planted-copy case. Its source-bound document returned 200 at main
`918405038071d65e524259c1458bb01c265be456`, and loaded copy/navigation bytes matched. All 41 planted blocks remained
present. Page, HTTP, request and CSP errors were empty, but the interaction did not complete. The run was retained
as failed after 28 readbacks and 12 cases; neither the second domain nor final revision checks was reached.

Native protocol logging preserved the underlying error for the exact `Runtime.callFunctionOn` request containing
the planted async probe and `awaitPromise: true`:

```text
2026-11-07T15:58:29.327Z  response id 738
error code -32000: Promise was collected
```

The same protocol session had no navigation/context-destruction event around that response. Installed
Playwright 1.56.1's `crExecutionContext.js` rewrites broad protocol errors into
`Execution context was destroyed, most likely because of a navigation.` That wording was not the cause.
The failed public receipt correctly marked the copy action incomplete even though cleanup observed the planted
DOM. A preceding scratch consumer had incorrectly marked its copy row successful during cleanup; that bookkeeping
was corrected without changing the overall failed outcome or original evidence.

The correction keeps the exact async test probe rooted on its isolated page until the result is consumed, requires
a completion sentinel, and removes the root afterward. Missing roots fail explicitly. Action and cleanup errors
are retained together. No product copy component, 41-column boundary, copied label, late stylesheet or overlap
assertion changes; no exception whitelist or automatic retry is introduced.

One bounded source-bound local experiment used the saved actual public document and unchanged released assets.
A direct CDP control collected an unrooted pending promise and returned the same underlying error. A rooted
promise survived forced collection and returned its expected value. The actual corrected consumer passed both
768 px touch and 1366 px mouse in Chromium and WebKit; Chromium forced collection between creating the probe
root and consuming it. A separately planted missing root failed the actual consumer. Both released local variants
also completed: that is nonreproduction, not proof that the old consumer cannot fail. All owned contexts/browser
processes and preview exited; source stayed clean.

Receipt SHA-256: `045e64b45ed98efe52e45dc3c5bee306186ba9501285b273561d851856ea595d`. [Independent source and actual-control review](https://github.com/Valpatel/cad-agent/pull/457#pullrequestreview-5813510723).

**Corrective rule:** Preserve the underlying protocol error before inferring navigation from a wrapper's message.
Give an asynchronous browser probe an explicit lifetime until its result is consumed, verify completion, and
keep cleanup success separate from action success. Preserve failures from the original consumer. These controls
establish this promise-lifetime hazard and the corrected consumer; they do not identify the cause of older
uninstrumented failures or constitute a successful public run. Full current CI and new publication evidence remain
separate requirements.


## Observe asynchronous probe completion through plain state

**Observed, 2026-11-07 17:15 UTC:** The first actual v0.27.1 public run failed at the same Chromium 768 px
probe despite the page promise root. The document was HTTP 200 at main
`c696d311a3ae6f648d4fbd660f9a824629af6374`; its 742,290 bytes hash to
`06c100ce429333092358467a61959d21c8911e6af414e6f6eb047909b309fcdf`.
Released copy/navigation bytes matched, 41 planted blocks remained, and page/request/external errors were empty.
The whole run failed after 30 responses and 12 cases. WebKit, the second domain and final revision checks were
not reached. The owned browser exited and source stayed clean. [Independent actual failure disposition](https://github.com/Valpatel/cad-agent/issues/450#issuecomment-6710551391).

```text
2026-11-07T17:15:22.844Z  id 738: page-root assignment returns undefined successfully
2026-11-07T17:15:22.948Z  id 739: -32000 Promise was collected
id 740: page-root deletion succeeds
```

The installed Playwright 1.56.1 utility's `_promiseAwareJsonValueNoThrow` creates a separate async serialization
promise when the evaluated value is thenable. `CRExecutionContext.evaluateWithArguments` asks CDP to await that
utility result. Keeping the page's input promise rooted therefore did not establish the lifetime of the value
actually awaited by the protocol. The prior direct-CDP control and forced collection **before** the actual
Playwright consume call did not exercise this boundary. Their local passes remain scoped evidence; the real
public recurrence disproves their sufficiency.

The follow-up starts the existing DOM probe once, retains its task and terminal value/error on the page, and
observes only a synchronous plain-state projection through Playwright. A ten-second host deadline rejects late or incomplete
observations; missing state, unknown state, a rejected task, a wrong completion value and expiry fail. Cleanup
still runs and both action/cleanup errors are retained, now including their messages in the aggregate summary.
The 41 columns, copied labels, late stylesheet, geometry and runtime assertions are unchanged. Product copy.js
is unchanged.

One reviewed saved-document experiment at `81f5f0f00950637786329581ffdd365c9c8a2c5f` completed on
2026-11-07 UTC. The actual released consumer failed at Chromium 1366 px: protocol response id 214 at
17:37:45.427 UTC returned `-32000 Promise was collected` while awaiting the rooted probe through the utility.
Its 768 px case and both WebKit cases were quiet. A separate simplified actual Playwright pending-promise control
also stayed quiet under forced collection; that control did **not** reproduce the failure.

The candidate passed all four 768/1366 px Chromium/WebKit cases with unchanged released assets and geometry/runtime
assertions. In Chromium, a temporary animation-frame gate held the real task in `running` state during forced
collection, then released its callbacks. Four scratch mutations of the actual consumer independently rejected a
missing root, asynchronous task error, non-completing task at the ten-second deadline and wrong completion value.
All contexts and three owned processes exited, and source stayed clean. Receipt SHA-256:
`4c42e79606812a5d4d273508b0659725667c3ee9137c1102f3ab5faaee4d2e78`.
[Independent actual diagnostic review](https://github.com/Valpatel/cad-agent/pull/462#issuecomment-6710788556).
This supplies local consumer and rejection evidence, not public delivery or proof that every other short asynchronous
browser evaluation is immune. Current full CI and actual corrective publication remain required.

**Corrective rule:** Test the actual browser-library evaluation boundary while it is pending. A lower-level API
control or a collection event before the awaited wrapper exists cannot prove that wrapper survives collection.
Prefer a plain observable completion record for a long asynchronous probe; reading that record must not rerun
the action or hide a recorded error. Do not retry the failed public action unchanged, infer a navigation from the
wrapper message, or retroactively classify older failures that lack native protocol evidence.
