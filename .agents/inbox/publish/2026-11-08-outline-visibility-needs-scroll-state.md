# A marked outline entry can leave view without changing its heading

On 2026-11-08 UTC, PR496 at `bcc506d3` failed Chromium run 42437947429/job 128600760451:
`1366px /docs/toolkit: the marked outline entry is out of the panel's view`. Full and WebKit passed.
The original artifact retained header/README evidence but no outline rectangles. The original Chromium cause
remains unknown; a prior source-head pass does not override this composed-head failure.

## Actual state and bounded controls

One reviewed local study built the current source and used the unchanged navigation JS/CSS with Chrome 151 and
WebKit 26. It retained geometry before a later screenshot. The actual toolkit passed the original bound in Chrome.
WebKit had no active entry at measurement, then delivered its scroll/mark after the later capture. That is evidence
of readiness arriving after measurement in this instrumented case, not an explanation of the original Chromium run.

Both engines rejected a real-component long-section control: the reader reset the panel to zero, then moved the
page from 3000 to 4000 while heading `#same` stayed active. Scroll/mark events arrived but the entry remained below
the panel. In Chrome its y 1307..1331 was outside panel 96..812; WebKit showed y 1286..1309. The reader's panel-only
scroll remained intact; manually bringing the entry into view passed and hiding it failed the same predicate.
All four contexts had no HTTP/runtime errors, the bounded owner exited 0/quiescent, and source remained unchanged
([independent actual disposition](https://github.com/Valpatel/cad-agent/pull/496#issuecomment-6716329721)).

## Cause and correction

The proven component defect was the `active !== shown` guard: it skipped the existing visibility operation when
page scrolling kept the same heading after a reader moved the panel. Apply that operation on every scheduled
mark. Panel-only scrolling still belongs to the reader, and the existing filter/hidden-link guards remain.

The geometry consumer must observe delivered reader input. It now waits for the commanded page scroll and one
following frame, with a hard 2000 ms bound; it never waits for geometry to become acceptable. The same strict
entry-within-panel predicate follows, including a hidden-entry negative. Record its readiness/rectangles before
any later screenshot. No longer sleep an arbitrary 300 ms and assume the page's scroll callback has run.

The same-section regression and current full browser CI remain required for the corrected source. This component
control does not establish the exact timing cause of the original Chromium failure or waive any current check.

## Keep sidebar controls reachable when wheel input reaches the tree edge

On 2026-11-12, the user reported that the toolkit reader's left side could not scroll back to its filters. A bounded actual Chrome probe at 1440×900 and article Y=6000 found the active `print-files` section, panel Y=1305. An upward wheel returned the panel to zero; the next upward wheel chained into the article (Y=5700), and correct section tracking pulled the panel back to Y=1283. At 1600 px the left outline is absent, so the same trap did not occur. Initial current-page reveal also moved the global search above view. The prior DOM/rect checks had not tested this input boundary.

A second screenshot showed an independent layering defect: the old one-filter sticky pseudo-element painted over the newly prepended global search label/input. Viewport geometry alone did not prove the control was usable.

Contain desktop panel overscroll so wheel/touch input at its edge does not chain into an article scroll. Preserve current-section tracking, including the strict same-section regression. Give the global search and tree filter one optional sticky controls block with its own background; suppress the legacy single-filter cover only for that block. Keep the mobile panel static with native page scrolling. The related browser regression uses actual wheel input at 1440/short desktop/1600, hit-tests and clicks the search, exercises mobile script/no-script layout, and plants the former wheel-chain and opaque-cover CSS as independent negative controls. No physical/CAD or full-suite claims follow from the focused evidence.

### A sticky controls block also needs a native scroll-into-view inset

The first wheel-boundary fix at `67f1804b` passed focused Chrome wheel/hit-test controls but failed the hosted WebKit ordinary outline-link click sequence (PR #608): after the last two smooth jumps, the middle “Mating connectors” link auto-scrolled underneath `data-nav-controls`, which intercepted the real click for 30 seconds. The same sequence passed locally in Chrome, so that local engine result did not invalidate the observed WebKit failure.

Measure the actual sticky controls height into the panel's `scroll-padding-top`, including the existing link inset. Recompute on viewport and controls-size changes, and clear it for the static mobile panel. Native scroll-into-view and the component's own marked-entry tracking need the same unobscured reading area. Keep ordinary clicks and all existing limits; add a native start-alignment hit test and reject a planted zero-inset state. The focused Chrome proof is not a WebKit pass; new normal hosted WebKit coverage remains required.

Independent review also identified a stale simulated-input assumption in `jumpProblems`: a synthetic sidebar wheel was followed by forcibly scrolling the article −800 px, although desktop containment now prevents that native scroll chain. Remove only that invented tree-to-parent case. Preserve the rail interruption, sidebar-internal jump, 300 ms stalled-jump and strict same-section checks; the actual wheel boundary plus its old-CSS negative lives in `readerBoundaryProblems`. This is a test-contract correction, not a product relaxation or a claim that an unseen CI failure was observed.
