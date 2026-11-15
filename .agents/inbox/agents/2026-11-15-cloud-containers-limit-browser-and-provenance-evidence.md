# A cloud container limits browser and provenance evidence

On 2026-11-15 UTC the same cloud session ([GitHub route](2026-11-15-cloud-sessions-reach-github-through-mcp.md))
changed browser components in #749, #753, #756 and #763. Durable guidance:
[cad-remote-runs, working from a cloud container](../../skills/cad-remote-runs/SKILL.md#working-from-a-cloud-container).

## "Source changed; regenerate scenario thumbnails" after a SCADA explorer change

**Symptom:** the `scada (chromium)` job fails at "Check SCADA gallery and scenario provenance" with
`AssertionError: Source changed; regenerate scenario thumbnails.`, and the browser suite in that job never runs.
**Cause:** `software/cadagent/webkit/scada/sim/metadata/thumbnails.json` records `source_hashes` of the explorer
sources; #753 changed `explorer/main.mjs` and ran only the browser suite locally. **Evidence:** #753 head `376daa28`
failed ([PR comment](https://github.com/Valpatel/cad-agent/pull/753#issuecomment-6900165254)). Its follow-up
`5cec5219` edited the `main.mjs` entry in `source_hashes` by hand; that commit is under a block verdict (review
5912667437) and unmerged. **Action:** never edit a recorded hash.
[`tools/webkit/scada/README.md`](../../../tools/webkit/scada/README.md) forbids editing capture hashes to make a
check pass and names the generator for each changed input: for explorer sources it is
`npm --prefix tools/webkit/scada run thumbnails:scenarios` on the pinned shell. A cloud container does not have that
shell, so stop and ask the owner; a same-build comparison of old and new source is evidence to attach to that
request, not a licence to edit. Before pushing, run that CI step's `npm run …:check` scripts under Python 3.12 (next
section). **Limits:** confirmed from the PR records and the README.

The inline model viewer has the same pairing: `software/cadagent/webkit/model/model.js` is hashed as
`renderer_sha256` in `tools/site/assets/models/j501-source.json`, enforced by `tests/webkit/webkit-model.test.mjs`.
#749 (open) regenerated it with `node tools/site/figures/site-model-poster.mjs --model j501`, which re-renders the
poster and writes the receipt; the poster came out byte-identical, so only `renderer_sha256` changed (its commit
`6e0a654a` says so). #756 (open draft) changes `model.js` too and must rerun that generator after #749 merges.

### A CI route is proposed, not merged

[#762](https://github.com/Valpatel/cad-agent/issues/762) / PR #763 (open, draft on 2026-11-15) makes the
`scada (chromium)` job, when its provenance step fails, recapture on the job's pinned shell and upload the result as
an artifact for the author to commit unchanged. It was demonstrated once, in run 43757747789: 61 scenarios, 63 files,
about 9.4 MB, 77 s. That run also showed that none of the 62 committed thumbnails is byte-identical to the CI
recapture; in the one image examined the differences were confined to text rendering, so the committed images were
made where fonts differ from CI's. **Limits:** observed once; run-to-run determinism on CI is not yet established.
Until #763 merges, the route is the owner.

## "Capture implementation changed" unless the check runs on Python 3.12

**Symptom:** `thumbnails:scenarios:check` fails with `Capture implementation changed; regenerate scenario thumbnails.`
although the generator is untouched. **Cause:** `capture_fingerprint()` in
`tools/webkit/scada/explorer/generate-scenario-thumbnails.py` hashes `ast.dump` output, which differs between Python
versions. **Evidence:** recomputed on 2026-11-15 from `dev` at `3bce93a4`: only Python 3.12.3 gives `6be498cb…`, the
manifest's value; 3.11.18 gives `c91038c8…` and 3.13.18 gives `6adb15f2…`. CI pins 3.12. **Action:** the npm scripts
call `python3`, which is 3.13 in the container, so put a 3.12 venv first on `PATH`
(`python3.12 -m venv <dir>`, install `tools/webkit/scada/ui/requirements.txt`, then `PATH=<dir>/bin:$PATH npm …`).
Do not regenerate thumbnails or rewrite the hash to satisfy another version. **Limits:** confirmed; a
version-independent fingerprint would be a separate change.

## Recapturing on another browser build changes images

**Symptom:** a recapture changes committed JPEGs that the source change cannot have affected. **Cause:** captures
depend on the browser build and fonts; CI installs the shell pinned by `tools/webkit/scada/ui/requirements.txt`, while
the container's Chromium is Chrome for Testing 153. **Evidence:** in #753, old and new `main.mjs` captured on the same
local build gave 55 of 62 identical JPEGs and 7 within 12 of 255 levels; the #763 demonstration above found no
committed image byte-identical to a CI recapture. **Action:** do not commit captures from the container; use the
pinned shell (or, once merged, #763's artifact). **Limits:** the pinned build's number (151) is stated in #753 only.

## Only Chromium is installed for Playwright

**Observed:** `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` holds `chromium-1243` (Chrome for Testing 153.0.8010.12),
its headless shell and ffmpeg, and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`; there is no WebKit. The pinned
`@playwright/test` 1.56.1 in `tools/site` expects revision 1194, so a default `chromium.launch()` finds no browser.
How each suite takes a browser (read from the test files on `dev`):

- `tests/webkit/{assembly,host,simulation}/browser.mjs`, `webkit-fea-browser.mjs` and `webkit-stage-browser.mjs`
  read `CHROMIUM_EXECUTABLE`.
- `tests/webkit/scada/explorer/browser.mjs` reads `PLAYWRIGHT_EXECUTABLE_PATH`.
- The `tests/site` browser suites take only `PLAYWRIGHT_CHANNEL`; unset, they launch channel `chrome`, which here
  resolves through `/opt/google/chrome/chrome` to a `/usr/bin/google-chrome` wrapper that runs
  `/opt/pw-browsers/chromium`. That is how they ran in this container, and why the site build reports "Google
  Chrome 153".

**Action:** do not install WebKit; report WebKit as "not run locally" and let CI's WebKit job decide. **Limits:** the
paths and revisions were confirmed on 2026-11-15; images vary. That Playwright cannot inject a WebKit touch drag rests
on #756's description only.

## Site checks that fail only in the browser job

- **A folder README must list every file in it,** including a new `__init__.py`, or
  `tests/site/website-repo-map.test.mjs` fails in the browser job (seen on #763).
- **Added prose can push a rendered page past the 1200 px wall-of-text limit,** failing
  `tests/site/website-browser.mjs` (seen on #763 for `tools/webkit/scada/README.md` and the `scada-system-authoring`
  skill page). Build the site and run that check for any page you lengthen; fold reference detail into `<details>`.

Both observed once, on #763's CI; not confirmed here.

## Slow steps

- `npm --prefix tools/site run build:site`: about 3 minutes in the session; 5 minutes when re-measured for this
  entry at `210a39e8`, with an empty diagram cache (720 diagram renders, none cached).
- `tests/webkit/webkit-model-touch-browser.mjs` (in #756, an open draft; not on `dev`): about 4 minutes, mostly
  software WebGL.
- `tests/site/toolkit/website-catalog-browser.mjs`: about 4.5 minutes a run; observed once, not confirmed.

[Agent setup incidents](README.md) · [Symptom index](../../SYMPTOM-INDEX.md)
