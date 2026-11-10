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
