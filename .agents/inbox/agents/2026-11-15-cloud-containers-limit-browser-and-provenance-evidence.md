# A cloud container limits browser and provenance evidence

On 2026-11-15 UTC the same cloud session ([GitHub route](2026-11-15-cloud-sessions-reach-github-through-mcp.md))
changed browser components in #749, #753 and #756. Durable guidance:
[cad-remote-runs, working from a cloud container](../../skills/cad-remote-runs/SKILL.md#working-from-a-cloud-container).

## "Source changed; regenerate scenario thumbnails" after a SCADA explorer change

**Symptom:** the `scada (chromium)` job fails at "Check SCADA gallery and scenario provenance" with
`AssertionError: Source changed; regenerate scenario thumbnails.`, and the browser suite in that job never runs.
**Cause:** `software/cadagent/webkit/scada/sim/metadata/thumbnails.json` records `source_hashes` of the explorer
sources; #753 changed `explorer/main.mjs` and ran only the browser suite locally. **Evidence:** #753 head `376daa28`
failed, fixed in `5cec5219` ([PR comment](https://github.com/Valpatel/cad-agent/pull/753#issuecomment-6900165254)).
**Action:** run that CI step's `npm run …:check` scripts in `tools/webkit/scada` under Python 3.12 before pushing.
The same pair exists for the inline model viewer: `software/cadagent/webkit/model/model.js` is hashed as
`renderer_sha256` in `tools/site/assets/models/j501-source.json`, enforced by `tests/webkit/webkit-model.test.mjs`
(#749 changed both; #756 must recompute it after #749 merges). **Limits:** confirmed from the PR records.

## "Capture implementation changed" under Python 3.13 only

**Symptom:** `thumbnails:scenarios:check` fails with `Capture implementation changed; regenerate scenario thumbnails.`
although the generator is untouched. **Cause:** `capture_fingerprint()` in
`tools/webkit/scada/explorer/generate-scenario-thumbnails.py` hashes `ast.dump` output, which Python 3.13 prints
differently (empty fields omitted). **Evidence:** recomputed on 2026-11-15 from `dev` at `3bce93a4`: Python 3.12.3
gives `6be498cb…`, equal to the manifest; Python 3.13.18 gives `6adb15f2…`. CI pins 3.12. **Action:** run the check
with `python3.12`; do not regenerate thumbnails or rewrite the hash to satisfy 3.13. **Limits:** confirmed; a
version-independent fingerprint would be a separate change.

## Regenerating thumbnails on another browser build rewrites them

**Symptom:** a recapture changes many committed JPEGs that the source change cannot have affected. **Cause:** the
captures depend on the browser build; CI installs the shell pinned by `tools/webkit/scada/ui/requirements.txt`, while
the container's Chromium is Chrome for Testing 153. **Evidence:** in #753, old and new `main.mjs` captured on the same
local build gave 55 of 62 identical JPEGs and 7 within 12 of 255 levels, so only the hash entry was updated.
**Action:** update the recorded hash with that same-engine comparison as evidence, or recapture on a machine with the
pinned shell. **Limits:** that a full recapture on build 153 would rewrite all 62 images, and the pinned build's
number (151), are stated in #753 but not confirmed by a full recapture.

## Only Chromium is installed for Playwright

**Observed:** `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` holds `chromium-1243` (Chrome for Testing 153.0.8010.12),
its headless shell and ffmpeg, and `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`; there is no WebKit. The pinned
`@playwright/test` 1.56.1 in `tools/site` expects revision 1194, so its default launch does not find a browser: pass
`executablePath` (the suites read `CHROMIUM_EXECUTABLE`). **Action:** do not install WebKit; state WebKit as "not run
locally" and let CI's WebKit job decide. Playwright cannot inject a WebKit touch drag, so a touch-drag change has no
WebKit drag evidence even in CI (#756). **Limits:** the paths and revisions were confirmed on 2026-11-15; images vary.

## Slow steps

- `npm --prefix tools/site run build:site`: about 3 minutes in the session; 5 minutes when re-measured for this
  entry at `210a39e8`, with an empty diagram cache (720 diagram renders, none cached).
- `tests/webkit/webkit-model-touch-browser.mjs`: about 4 minutes, mostly software WebGL (#756).
- `tests/site/toolkit/website-catalog-browser.mjs`: about 4.5 minutes a run; observed once, not confirmed.

[Agent setup incidents](README.md) · [Symptom index](../../SYMPTOM-INDEX.md)
