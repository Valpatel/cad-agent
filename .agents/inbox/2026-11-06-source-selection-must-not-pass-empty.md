# Source selection must not pass empty or import a different checkout

Search found the general procedure in [Exercise moved consumers](../../docs/lessons/process/verify-from-source.md#exercise-moved-consumers-instead-of-checking-path-declarations). These are concrete source-selection controls for that rule, recorded with the ownership migration in #387.

**Evidence, 2026-11-06 UTC:** independent review at `ee8f3e3a438403a3ac7d4846de3b9d5fc468f932` reproduced two false positives ([review](https://github.com/Valpatel/cad-agent/pull/387#pullrequestreview-5799130099)). The HTTP checker still enumerated `src` and `tools`: a planted bare `urlopen` under `software/cadagent` was not selected. The generated-site browser test set `PYTHONPATH=src`; with a foreign editable environment, its child imported that other checkout instead of the code under review.

- `pytest -q tests/repo/test_fetch_user_agent.py tests/cli/test_installer.py`: 10 passed, one existing optional PowerShell-parser check skipped. Current nested package/tool faults are rejected by the actual HTTP validator. Imported vendor trees and a stale `src` file stay excluded. Removing the current package cannot produce an empty pass.
- Replacing only the current enumerator with its actual prior body makes the same current validator fail with `no current toolkit package files were selected`; the corrected enumerator passes.
- The actual Python program embedded in `site-diagrams-browser.mjs`, run with the foreign editable interpreter, rejects the old missing-`src` binding at the new import-origin assertion before writing a README. The absolute `software` binding generates the real light and HUD products. The first local positive attempt lacked the existing Markdown extra; supplying that dependency from an isolated cache made it pass without modifying the foreign environment.

**Cause:** a path declaration is not proof of what a collector selects, and a successful import is not proof of its origin. An installed editable package can silently rescue a wrong source path.

**Rule:** exercise the actual collector with current, missing, stale and excluded paths. Require nonempty expected package coverage and plant a fault in a nested current module. Before generating a product, assert both the package and generator files resolve inside the intended checkout. Keep the real parser/render consumer; test the source binding rather than matching its implementation text.

**Limits:** the HTTP test is a static heuristic over named calls and headers, not a network execution or complete semantic proof. The import controls establish the tested Python source binding and generated fixtures, not all environments or physical CAD qualification. Fleet 216 remains scoped to its own immutable source and commands; a later test-only correction does not relabel that run as a new build.
