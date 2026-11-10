# Assembly guide feature tests

This document accompanies the [design and API](assembly-guide.md). It distinguishes checks actually executed
from planned feature acceptance. CAD illustrations and browser presentation are not physical qualification.

## Requirement-to-test matrix

| Requirement | Test owner / concrete case | Status at this source checkpoint |
|---|---|---|
| Strict guide schema, snapshot identity, explicit mm/z-up and per-instance mesh hashes | `tests/webkit/assembly/guide.test.mjs`: legacy versus guide manifest; invalid guide cases; duplicate mesh/frame/hash cases | 29 Node contract tests passed on Node 22; final entry-hash counterexample is included |
| Required model members, repeated screws, unknown/duplicate instances, prerequisites and finite vectors | Same file: invalid guide cases and absolute-state test | Passed in the above Node run |
| HTTP/body deadline, wrong hash, byte cap, abort, missing/corrupt version | Same file: download failure controls and loadGuide binding | Passed in the above Node run |
| Absolute direct/backward states, previous/future membership and unchanged source pose | `tests/webkit/assembly/browser.mjs`: each v1/v2/WIP Previous/direct step; assembled reset | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| Real highlighted/ghost/wireframe/solid states and visible multipart output | Browser suite: real materials/visibility plus retained screenshots | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| CAD units/frame applied exactly once | Browser suite: independently hard-coded +25 mm CAD-Z→+0.025 m stage-Y delta, plus wrong 1000x, wrong-axis and doubled-offset fault controls | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI; expectations do not read guide offsets |
| Picking, selection and explicit isolation | Browser suite: actual projected canvas click plus two repeated screw identities | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| Framing, reset and legacy `?manifest=&explode=&section=` behavior, spaced filenames, CSS colours, absolute/root/CORS URLs and ordinary redirects | Browser suite: existing route and API round trip | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| Resource teardown and cancelled load | Browser suite: geometry/material dispose events, repeated dispose, no canvas, aborted creation | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| Two frozen versions and exact-commit WIP use independent scenes/instructions | Browser suite: differing dimensions, steps, hashes, UUIDs and snapshot IDs | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI; product selector/deep links/progress are Gyropup #266 acceptance |
| Phone portrait/landscape and keyboard navigation | Browser suite: actual previous/next controls and overflow checks | Chromium and WebKit component suites passed at `e219d2ac`; final portable entry binding awaits release/CI |
| Runtime and complete asset closure in release ZIP; preserve old output on rejection | Separate release integration PR / `tests/publish/test_release.py` | Root-owned, pending |
| Current recipe/neutral transforms/posters and static/Markdown fallback | Gyropup #266 producer and product tests | Product-owned, pending; no stale turret illustration accepted here |
| Rapid switch race, progress isolation, no-WebGL fallback, touch/reduced motion, complete requirement UI | Gyropup #266 tests, with shared abort/dispose primitives | Product acceptance still pending; not implied by this shared module |

The product's existing ordinary-viewer fixtures also exposed a legacy absolute/root URL regression. Ordinary
HTTP(S) URL resolution and external CORS/redirect behavior are retained separately from strict guide paths;
new pure cases pass and real browser cases are authored for current CI. The held ordinary load uses an absolute
mesh URL. Programmatic slider readouts and first-usable-frame readiness are reconciled with the existing product
viewer. The portable reader's assembled reset now synchronizes mode/explosion/section labels, with actual DOM
assertions in the component suite; current browser verification of this corrective delta remains pending.

The first current-head Chromium CI stopped before component execution on missing parent README links and a
fixture row outside its ownership table. After those fixes, the local structural suite also exposed a stale
`docs/map.md`; the unchanged generator refreshed its inventory from 1034 to 1039 folders. The final structural
map suite passed 28 tests with one explicit CI-only drawing skip. These failures remain classified separately
from browser interaction evidence; actual themed map rendering still belongs to current CI.

## Commands and CI

Use installed Node 22 and the existing `tools/site` npm context:

```sh
node --test tests/webkit/assembly/guide.test.mjs
npm --prefix tools/site run test:webkit-unit
PLAYWRIGHT_BROWSER=chromium npm --prefix tools/site run test:assembly-guide
PLAYWRIGHT_BROWSER=webkit npm --prefix tools/site run test:assembly-guide
```

The full multipart suites at `e219d2ac` recorded 13 case rows per engine, zero page errors, and terminal owned
service cleanup. The earlier `65d7dcd9` WebKit picking failure and changed `5fe0132d` offscreen-projection failure
remain retained failures; camera matrices and overlay fitting were corrected with strict projected-bound checks.
The final top-guide hash forwarding changes only the portable entry binding; its explicit Node corruption control
passes, while actual extracted-ZIP valid/corrupt-entry browser acceptance belongs to the release integration.
The focused existing and new Node suites passed 35 tests; exporter/render/layout/area/packaging checks passed
138 tests with two optional-extra skips. These counts do not substitute for current-head CI or product acceptance.

The existing `webkit.yml` runs the new browser suite in both engines; it does not waive the existing site,
file-viewer, part-table or diagram suites. Browser reports and screenshots use `TEST_OUTPUT`, defaulting to a
private temporary output directory. Failure receipts remain failures; a corrected source needs a fresh run.

Existing `tests/publish/test_view.py` checks exporter/packing/frame metadata and Python↔JavaScript decoding.
`tests/review/test_packet.py` checks source hashes, staleness and step-derived offsets. Existing rigid-subassembly
and assembly gates remain separate. Release tests already check deterministic ZIPs, source/dirty state, rewritten
links, stale print sets and destination collisions; extending guide packaging must retain those controls.
