# Source selection must not pass empty or import a different checkout

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
