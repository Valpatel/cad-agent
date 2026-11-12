# Camera setters must update matrices before projection and picking

On 2026-11-10 UTC, the first shared assembly-guide component run at `65d7dcd9` passed Chromium but failed the
WebKit picking assertion after assembled reset. The failure is retained; it did not establish a cause by itself.
Inspection of the phone image also showed the upper model occluded by the page header. Source dimensions alone
were insufficient to prove that instructions and geometry were usable together.

The changed framing run at `5fe0132d` retained the projected click target before input. It was outside the viewport
at x=-278.71, y=786.96, with no element under it, although the later screenshot showed the reset scene. The camera
position/target setters had changed scene state without synchronously updating `matrixWorldInverse`. Projection
and raycasting could read the previous camera matrix until the next render frame.

Correction: fit against the real header/panel insets, and update camera/world matrices before synchronous
projection or picking. Do not add a sleep or converge geometry until it passes. `tests/webkit/assembly/browser.mjs`
asserts the projected click is actually over the canvas, checks geometry stays outside the phone header/panel,
and exercises the unchanged actual picking path. The changed `3c4dbe21` WebKit run passed its component cases;
Chromium framing had also passed at `c01c0ecd`. These are component outcomes, not product or release acceptance.

The same implementation keeps caller-owned panel controls separate from its own wrapper, aborts pending asset
reads and disposes its own mesh/material resources. Its cleanup regression must prove an unrelated panel control
survives disposal. A stage's renderer cleanup alone does not establish ownership of every surrounding DOM node.

Commands (existing Node 22 and installed browser context, no dependency installation):

```sh
node --test tests/webkit/assembly/guide.test.mjs
PLAYWRIGHT_BROWSER=chromium npm --prefix tools/site run test:assembly-guide
PLAYWRIGHT_BROWSER=webkit npm --prefix tools/site run test:assembly-guide
```

The guide browser checks contain independent +25 mm CAD-Z → +0.025 m stage-Y expectations and reject wrong-axis,
1000x-unit and doubled-offset controls. A readable screenshot does not prove the CAD order, insertion path,
physical fit or build qualification. The initial failure and changed diagnostic must not be rewritten as passes.

## A reset must reset its controls as well as its meshes

The portable release browser run at `a25ecf71` produced usable model views, but inspection of its retained
Chromium v1 and WebKit v2 images showed an assembled solid model alongside a Wireframe selector and a checked
Show authored explosion control. The prior assertions inspected mesh properties but omitted these displayed
values. That limited component result did not establish a coherent user-facing reset.

The shared mount now selects an explicit assembled overview, sets Solid, clears explosion, and disables
instruction-only display controls until another instruction is chosen. Its component suite checks the actual
DOM values as well as the real mesh state. Programmatic Explode and Section calls also update their existing
slider readouts, matching the product viewer's original behavior. Ready includes an actual render and a frame;
loading text does not disappear before the first usable scene. These corrective browser assertions were added
before the next run; the old images remain evidence of the mismatch, not a passing reset acceptance.

On 2026-11-10 UTC the changed portable test at `3b7d4f7f` then timed out at
`Previous` because reset correctly selected the new assembled overview. The test
had assumed it still occupied the final instruction. Source inspection showed
the overview deliberately disables Previous and enables Next to start the first
instruction. Corrective source `47b07508` checks those displayed values, chooses
an instruction explicitly, then verifies backward navigation and selected-part
appearance restoration. The actual `test:assembly-release` runs reported
`{"engine":"chromium","cases":7,"errors":0,"foreign":0}` and the same counts
for WebKit. Both owned services terminated and their listeners closed.

Rule: tests must assert a reset's navigation identity along with its material and
control values. Do not make a deliberate overview behave like an instruction to
rescue a test. This portable synthetic-fixture result remains separate from
real product content, touch controls and physical build acceptance.

## Authored camera directions must survive orbit constraints

On 2026-11-10 UTC, the product's actual turret step 06 requested CAD camera direction `[0.6, -1, -0.35]`,
which looks up from below the assembly. The preserved stage set `controls.maxPolarAngle = 1.5`; its
`fitView` calls `controls.update`, so the requested negative stage-Y direction was clamped above horizontal.
Checking only framed bounds or a readable screenshot did not check the authored view.

Guide-bound viewers now permit the full polar range while ordinary viewers retain their prior limit. The
component fixture requests that same underside direction, compares the actual camera-minus-target vector to
the independent normalized stage vector `[0.6, -0.35, 1]`, reinstates the old clamp as a rejecting control, and
asserts the ordinary viewer still has its original limit. Both existing browser suites passed 19 case rows
each with zero page errors after the correction. The initial local user-service command failed before test
startup because it used a relative script path from the service home; the corrected invocation pins both the
working directory and absolute test path. That setup failure remains separate from the actual test outcomes;
this presentation correction does not prove tool access or a feasible physical insertion path.


## Readiness must wait through a document without a body

On 2026-11-10 UTC, both main-promotion WebKit jobs for PR #506 failed in
`tests/webkit/assembly/release-browser.mjs:47`: `TypeError: null is not an object (evaluating 'document.body.dataset')`.
The jobs were 129668309116 (run 42767803019) and 129668005951 (run 42767708398). All preceding suites passed.
After clicking the interactive reader link, the test polled `document.body.dataset.ready === '1'`; a document
without its body cannot satisfy readiness, but dereferencing it threw instead of continuing to wait. This is a
readiness-predicate defect, not evidence that the reader had become ready or that its model was invalid.

The predicate now returns false when the body is absent, and still requires the exact ready value `1`. The
original 20-second ready wait, geometry/material/hash assertions and corruption negatives remain. An actual
browser control removes a document's body, proves the old predicate throws, verifies both absence and ready `0`
are false, then delivers a ready `1` body and requires the real wait to resolve. It uses no sleep or geometry
retry. Reader/runtime/data bytes are unchanged; the failed promotion receipts remain failures and fresh current
CI is still required. Both corrected local engines passed eight cases with zero page errors/foreign requests,
including the absent/unready/ready body control. The source release's earlier passing browser jobs did not cover
every navigation timing.

Evidence: [promotion WebKit job](https://github.com/Valpatel/cad-agent/actions/runs/42767803019/job/129668309116),
[dev-push WebKit job](https://github.com/Valpatel/cad-agent/actions/runs/42767708398/job/129668005951).

## Clipping pixels need a lighting-independent visibility signal

On 2026-11-10 UTC, PR #509 source `8fefeeff` ran the real shared Chromium component suite under a bounded
180-second, two-CPU, 3 GiB user service. Actual playback world poses passed for two frozen fixtures and WIP,
and hidden-future framing passed its omitted-member negative. The run then failed its Y-plane flip observer:
a retained blue face changed from `[55,136,186]` to `[125,183,217]`, while a clipped landmark showed floor color
`[43,78,81]`. The observer required RGB closeness to a shaded baseline. That result does not establish a wrong
plane or a root cause for the lighting change; later hover/legacy cases and WebKit were unrun. Owned browser,
server and cgroup processes were gone at exit; the failed receipt and screenshot remain retained.

Corrective rule: a clipping visibility fixture must separate geometry retention from brightness/shadow changes.
Keep the real physical material, renderer, geometry and clipping planes, but give its landmarks distinct emissive
signals with diffuse/specular contributions disabled for that diagnostic. Keep the same strict pixel-distance
threshold. Exercise off-centre cuts, all three source CAD axes, a flip that preserves plane location, and actual
wrong-axis and normal-only-flip mutants; a midpoint alone cannot detect a missing constant negation. Save the
whole pixel table before assertions. This fixture tests clipping visibility, not the product's material lighting.
The ordinary material/appearance and full legacy tests remain separate; no complete feature or physical
acceptance follows until actual corrected two-engine suites pass.

## Retry must roll back the whole failed rendering attempt

On 2026-11-12 UTC, independent review of homepage #606 injected a first GPU draw
exception into the actual shared model component, after canvas, controls and observers
were allocated. The tiny valid packed fixture reported `error: 1 canvas / 1 controls`,
then `retry ready: 2 canvases / 2 controls`; the unrelated viewer remained `1 / ready`.
[Review evidence](https://github.com/Valpatel/cad-agent/pull/606#discussion_r4546711636)
retains the failed result. A fetch-only retry check had passed but never reached this
allocation boundary.

Register disposal as each resource is acquired, roll back the failed attempt before
showing its poster/retry, and give every retry a fresh readiness promise. Cancel frames,
disconnect observers/listeners, dispose renderer/geometry/material resources, and
remove only that attempt's canvas/controls. The homepage browser regression injects
the late draw failure into a tiny real packed model, requires zero failed-attempt
canvases/controls and exactly one after recovery, and checks the other viewer's canvas
identity survives. A resize and visibility change expose abandoned callbacks.

This is an attempted correction pending its actual-browser recheck and independent
review; no current homepage art, physical design or publication acceptance follows.

## A source material value must match the renderer's color schema

The 2026-11-12 J501 homepage poster check first showed the fitted lid but hid both
negative-X WiFi antennas behind the enclosure at the inherited +35° view. A second,
negative-X view exposed both original context shapes, but rendered them white:
the source manifest's normalized RGB array `[0.06, 0.065, 0.075]` had been passed
unchanged to a material constructor that consumes a CSS color. Geometry/hash
checks alone had not exercised this consumer boundary. Both unsuccessful posters
and their stopped-run logs remain retained with #605; neither establishes visual
acceptance.

Preserve the source RGB values in provenance, validate exactly three finite numeric
channels in [0,1], and convert only the display material to CSS `#0f1113`. The
packed-model contract rejects the original array defect; the existing view tests
reject malformed channels, NaN, infinity, booleans and out-of-range values. Inspect
the actual matching opening-view poster as well as numerical geometry. This is
render-only context, not a new color measurement, physical-fit or RF qualification.
