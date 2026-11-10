# Assembly guide feature tests

This document accompanies the [design and API](assembly-guide.md). It distinguishes checks actually executed
from planned feature acceptance. CAD illustrations and browser presentation are not physical qualification.

## Requirement-to-test matrix

| Requirement | Test owner / concrete case | Status at this source checkpoint |
|---|---|---|
| Strict guide schema, snapshot identity, explicit mm/z-up and per-instance mesh hashes | `tests/webkit/assembly/guide.test.mjs`: legacy versus guide manifest; invalid guide cases; duplicate mesh/frame/hash cases | 25 Node tests passed locally on Node 22; browser results pending |
| Required model members, repeated screws, unknown/duplicate instances, prerequisites and finite vectors | Same file: invalid guide cases and absolute-state test | Passed in the above Node run |
| HTTP/body deadline, wrong hash, byte cap, abort, missing/corrupt version | Same file: download failure controls and loadGuide binding | Passed in the above Node run |
| Absolute direct/backward states, previous/future membership and unchanged source pose | `tests/webkit/assembly/browser.mjs`: each v1/v2/WIP Previous/direct step; assembled reset | Authored, not yet executed |
| Real highlighted/ghost/wireframe/solid states and visible multipart output | Browser suite: real materials/visibility plus retained screenshots | Authored, not yet executed |
| CAD units/frame applied exactly once | Browser suite: independently hard-coded +25 mm CAD-Z→+0.025 m stage-Y delta, plus wrong 1000x, wrong-axis and doubled-offset fault controls | Authored, not yet executed; expectations do not read guide offsets |
| Picking, selection and explicit isolation | Browser suite: actual projected canvas click plus two repeated screw identities | Authored, not yet executed |
| Framing, reset and legacy `?manifest=&explode=&section=` behavior | Browser suite: existing route and API round trip | Authored, not yet executed |
| Resource teardown and cancelled load | Browser suite: geometry/material dispose events, repeated dispose, no canvas, aborted creation | Authored, not yet executed |
| Two frozen versions and exact-commit WIP use independent scenes/instructions | Browser suite: differing dimensions, steps, hashes, UUIDs and snapshot IDs | Authored, not yet executed; product selector/deep links/progress are Gyropup #266 acceptance |
| Phone portrait/landscape and keyboard navigation | Browser suite: actual previous/next controls and overflow checks | Authored, not yet executed |
| Runtime and complete asset closure in release ZIP; preserve old output on rejection | Separate release integration PR / `tests/publish/test_release.py` | Root-owned, pending |
| Current recipe/neutral transforms/posters and static/Markdown fallback | Gyropup #266 producer and product tests | Product-owned, pending; no stale turret illustration accepted here |
| Rapid switch race, progress isolation, no-WebGL fallback, touch/reduced motion, complete requirement UI | Gyropup #266 tests, with shared abort/dispose primitives | Product acceptance still pending; not implied by this shared module |

## Commands and CI

Use installed Node 22 and the existing `tools/site` npm context:

```sh
node --test tests/webkit/assembly/guide.test.mjs
npm --prefix tools/site run test:webkit-unit
PLAYWRIGHT_BROWSER=chromium npm --prefix tools/site run test:assembly-guide
PLAYWRIGHT_BROWSER=webkit npm --prefix tools/site run test:assembly-guide
```

The existing `webkit.yml` runs the new browser suite in both engines; it does not waive the existing site,
file-viewer, part-table or diagram suites. Browser reports and screenshots use `TEST_OUTPUT`, defaulting to a
private temporary output directory. Failure receipts remain failures; a corrected source needs a fresh run.

Existing `tests/publish/test_view.py` checks exporter/packing/frame metadata and Python↔JavaScript decoding.
`tests/review/test_packet.py` checks source hashes, staleness and step-derived offsets. Existing rigid-subassembly
and assembly gates remain separate. Release tests already check deterministic ZIPs, source/dirty state, rewritten
links, stale print sets and destination collisions; extending guide packaging must retain those controls.
