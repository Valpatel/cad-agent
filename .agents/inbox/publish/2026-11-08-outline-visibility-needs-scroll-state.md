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
