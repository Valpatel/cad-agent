# Source selection must not pass empty or import a different checkout

## Verify the installer at every actual entrance

On 2026-11-07, issue322's real report flagged two instructions that pipe a mutable download into a shell.
Reading their consumers found the same shortcut independently copied into the homepage card, agent prompt
and quickstart evaluator, with tests requiring the unsafe command literally. Editing only the two reported
pages would leave actual advice and the evaluator inconsistent.

Keep one immutable download/checksum/execution block per platform in the existing installation guide. Route
the README, homepage and agent instructions there; make the evaluator extract the exact block and reject
missing or duplicate markers. A hash mismatch or failed download must reach no shell or child process.
Test the actual documented block, not a separately implemented checksum helper. Compare Git blob bytes,
which the immutable URL serves, rather than possible Windows checkout CRLF conversion.

```text
python -m pytest -q tests/cli/test_installer.py tests/repo/test_agent_prompt.py \
  tests/repo/test_resource_audit.py tests/repo/test_cut_release.py \
  tests/repo/test_layout.py tests/repo/test_areas.py
217 passed, 5 skipped (local PowerShell unavailable), 1 existing folder warning
```

Both POSIX hashing paths accepted exact downloaded bytes and handed off to the real installer's safe
`--help` parser; corrupted bytes and failed downloads reached no shell, with temporary files removed.
The Windows job must actually run the PowerShell guard, hash, failed child and cleanup controls with inert
fixtures. Local skips are not Windows acceptance; full CI and whole-page consumers remain required.
These checks do not perform a real uv/CAD installation, certify PowerShell 5.1 on every Windows setup,
or authenticate every transitive download. The guide states that remaining trust explicitly.


### Check generated preambles as well as embedded guides

On 2026-11-07, the one actual current Opus trial for #282 installed and used the toolkit but failed its existing
report-contract grade, 7/12 ([independent result](https://github.com/Valpatel/cad-agent/issues/282#issuecomment-6709824302)).
Its retained WebFetch result also repeated unchecked installer shortcuts from the `llms.txt` preamble before
following the checked guide. Reading the actual builder found those shortcuts at `tools/site/build-site.mjs`,
then copied into `index.md`. The prior site consumer checked that both outputs included the safe embedded
guide, while its no-pipe assertion covered only the HTML entrance and guide. Safe content later in an output
did not establish that its earlier advice was safe.

Route the generated preamble to the same canonical checked guide. Check the entire actual `llms.txt` and
`index.md` output, not just the embedded agent-guide substring, and plant each old platform shortcut in a
preamble to prove it is rejected. Keep the eight-word prompt, installer bytes and checksum procedure unchanged.
This correction does not turn the failed agent report grade, unknown freshness, disabled native discovery or
unproved Windows denied-symlink trigger into acceptance. No second model invocation is part of this fix.

Search found the general procedure in [Exercise moved consumers](../../docs/lessons/process/verify-from-source.md#exercise-moved-consumers-instead-of-checking-path-declarations). These are concrete source-selection controls for that rule, recorded with the ownership migration in #387.

**Evidence, 2026-11-06 UTC:** independent review at `ee8f3e3a438403a3ac7d4846de3b9d5fc468f932` reproduced two false positives ([review](https://github.com/Valpatel/cad-agent/pull/387#pullrequestreview-5799130099)). The HTTP checker still enumerated `src` and `tools`: a planted bare `urlopen` under `software/cadagent` was not selected. The generated-site browser test set `PYTHONPATH=src`; with a foreign editable environment, its child imported that other checkout instead of the code under review.

- `pytest -q tests/repo/test_fetch_user_agent.py tests/cli/test_installer.py`: 10 passed, one existing optional PowerShell-parser check skipped. Current nested package/tool faults are rejected by the actual HTTP validator. Imported vendor trees and a stale `src` file stay excluded. Removing the current package cannot produce an empty pass.
- Replacing only the current enumerator with its actual prior body makes the same current validator fail with `no current toolkit package files were selected`; the corrected enumerator passes.
- The actual Python program embedded in `site-diagrams-browser.mjs`, run with the foreign editable interpreter, rejects the old missing-`src` binding at the new import-origin assertion before writing a README. The absolute `software` binding generates the real light and HUD products. The first local positive attempt lacked the existing Markdown extra; supplying that dependency from an isolated cache made it pass without modifying the foreign environment.

**Cause:** a path declaration is not proof of what a collector selects, and a successful import is not proof of its origin. An installed editable package can silently rescue a wrong source path.

**Rule:** exercise the actual collector with current, missing, stale and excluded paths. Require nonempty expected package coverage and plant a fault in a nested current module. Before generating a product, assert both the package and generator files resolve inside the intended checkout. Keep the real parser/render consumer; test the source binding rather than matching its implementation text.

**Limits:** the HTTP test is a static heuristic over named calls and headers, not a network execution or complete semantic proof. The import controls establish the tested Python source binding and generated fixtures, not all environments or physical CAD qualification. Fleet 216 remains scoped to its own immutable source and commands; a later test-only correction does not relabel that run as a new build.

## Keep repository ownership separate from served namespaces

On 2026-11-06, the exact `6bea336a` full CI run failed two `tests/publish/test_site.py` assertions after 3,372 passed / 19 skipped in 629.93 seconds. The migration had incorrectly prefixed preserved SDK-relative expectations with `software/`: copied `site/assets/software/vendor/mermaid/...` did not exist, and `/_cadagent/kit/software/vendor/three/...` returned 404. The producer still correctly used `assets/vendor/` and `/_cadagent/kit/vendor/`; repository `software/vendor/` is a different owner.

Both original assertions were replayed with the declared Markdown extra and failed for those same file/HTTP causes. The corrected entire project-site test module passed 14 tests with one existing optional CAD check skipped. It compares actual copied Mermaid bytes with `KIT_DIR`, fetches the real STL loader over HTTP, refuses the wrong `software/vendor` endpoint with 404, and asserts no second copied namespace appears.

**Rule:** classify physical repository paths, packaged SDK-relative paths and served URLs separately. Run the actual publication consumer with its declared optional extra before claiming coverage. The core jobs were green because Markdown was absent and this module was skipped; that was not a passing path check. Required full CI correctly caught the mistakes. Do not relabel this application assertion failure as provisioning or retry unchanged source.

## Check the complete publication identity

A release-probe review on 2026-11-06 found a separate false pass: matching only URL pathnames accepted a changed catalogue ID or an unrelated origin with the same route. The rejected operator recipe is preserved with SHA-256 `fc2b58aaef2466284d9a2dcacfa53413fecdb18271cf69f99f2253c8e0bcd339`; the corrected recipe is `d02693d76fea44ce44d2573e6476ee70e1db452fee2d334698dc9d0f758b1e4a`.

The corrected actual consumer checks the reviewed expected ID and exact canonical HTML, Markdown and source URLs. Its retained-catalogue controls accepted all 10 correct kit identities and rejected 30 wrong-origin/changed-ID faults without public calls; [independent release-probe review](https://github.com/Valpatel/cad-agent/issues/389#issuecomment-6683686983) exercised further faults. These were pre-publication verifier controls, not evidence that an incorrect deployment had been accepted.

**Rule:** derive expected identities from the reviewed release contract, then compare every identity field in the response. A matching pathname or a current version endpoint cannot establish the origin, catalogue ID or exact linked resource. Preserve the rejected recipe/hash and make the same consumer reject faults before using it for publication acceptance. This rule supplements actual deployment, asset and no-script checks; it does not replace them.

## Verify a suggested producer move against the actual source

On 2026-11-06, the coordinator inferred that `readme_anim.py` was among the eight moved figure scripts and suggested `tools/figures/readme_anim.py`. The author applied that suggestion at `daf8a755334ef54a8594e0fdc0c8d1ce56df52a6` without checking the tree. The original `tools/readme_anim.py` caption was already correct. A preview repeated the guessed URL as its expected value and falsely passed it.

Independent review ran `git cat-file -e HEAD:tools/figures/readme_anim.py`: exit 128. The actual `HEAD:tools/readme_anim.py` returned 0; the imported producer, tools map and `docs/pages.yaml` agreed. The href and display were restored while preserving the compact disclosure and all credits. The existing README hero consumer now checks the credit against the actual imported producer and that producer's declared hero output. The same consumer rejects both the guessed missing path and an existing but unrelated tracked script; the preview also preflights the tracked producer before rendering.

**Rule:** a suggested move is an assumption until the tracked source and real producer agree. Compare provenance against the producer actually loaded and its output, not a second copy of the proposed string. A successful visual rendering cannot establish that an attribution link names a real source file. The custom-directory runtime proof from fleet 218 remains scoped to its exact component; this caption correction does not rerun or relabel it.

## Check current navigation outside released history

On 2026-11-06, independent release review of #391 at `2f380b52b006203931e06f6a46e1ae18ca99c04a` found that the CHANGELOG introduction still linked to `changelog.d/README.md`. `git cat-file -e HEAD:changelog.d/README.md` returned 128; `git cat-file -e HEAD:docs/changelog.d/README.md` returned 0. The hierarchy migration had moved the guide, while source and metadata review missed this current navigation link. Release publication was held for the correction.

**Cause:** preserving dated release notes and reproducing the release producer do not validate the current introduction's links. The producer intentionally carries that introduction through unchanged.

**Rule:** separate current navigation from dated evidence when checking a move. Resolve the current links against the actual tracked tree; keep released notes byte-identical unless a separately reviewed correction requires otherwise. This repair changes only the introduction's fragment-guide label and destination. It does not claim a new link checker, broader publication coverage, or any change to historical release behavior.

## Execute the canonical technique, not only its underlying APIs

On 2026-11-06, the #283 routing audit found an existing six-step Python example in `sheet-metal-hardware`, but no design-process route and no consumer executing that canonical block. A disposable edit changed only its clinch selector's sheet to `unlisted-sheet`: the original `pytest -q tests/mechanical/test_sheet_hardware.py` still passed all 14 tests, while executing the actual block raised `ValueError: unknown sheet`. The source was restored in `finally`; no catalogue or solver data changed.

The refined existing test module executes that trusted, committed block through its real APIs and inspects the returned step results. It retains the source-derived numbers, WARN/FAIL distinctions, unpriced rivet, dated price and model limits. Changed geometry produces WARN and FAIL; an unknown sheet rejects, and the same consumer rejects missing steps, a no-op price call/output and a forced PASS on the warning case. The existing API/data checks remain in place.

**Rule:** routing to an existing technique should make its canonical example a real consumer of the current implementation. Do not substitute another copy of its inputs or assert only that API names exist. Use real bad inputs and no-op results to check that the consumer cannot pass empty. This is a deterministic model/example check, not evidence of physical fit, joint capacity, current supplier prices or every possible user design. The test executes only the repository's reviewed example, not arbitrary external Markdown.


## Keep original import inputs when testing repository migrations

**Evidence, 2026-11-07 UTC (#163):** `tools/import_refmap.py <original-reference-map>/data.json --check`
failed on both the research worktree and the unchanged security-audit baseline: only `coverage.yaml` would change.
The retained original map's SHA256 prefix was `5d33252ef56f2048`. Its generated diff restored `src/cadagent/`,
`research/` and `docs/design-process-plan.md` paths that the repository had moved. All promoted and hand-added
source records were correctly preserved. No importing write was run before examining this diff.

**Cause:** the migration updated committed coverage and the test fixture's input to current paths, while the importer
still received historical paths from the actual external data. A green fixture did not exercise that boundary.

**Correction:** translate only the known repository moves at the coverage-import boundary. Preserve the historical
observation date, line numbers, claims, unposted drafts, current paths and external URLs. The new actual-import
fixture fails against the old implementation on the `where` path. Its corrected run also checks source text, gap
text, draft bodies, input-file preservation and idempotence. Do not rewrite the original map to make the check pass.

**Validation:** the new original-input test failed before the fix; all 28 importer tests pass afterward. The real
map still required four YAML line-wrap changes, with parsed coverage exactly equal and every other shard hash
unchanged. After adopting only that deterministic formatting, the full original-map `--check` passes.

**Limits:** this is path correspondence, not a fresh evaluation of the map's historical capability claims or line
positions. Unrecognized or product-relative paths remain untouched; no draft issue is posted by the importer.
