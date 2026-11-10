# Checkout cleanup must preserve every path consumer

On 2026-11-10 UTC, the owner requested consolidation of project-name-prefixed checkout siblings. The reviewed
inventory found 151 registered worktrees, active feature branches, dirty source and real editable/symlink providers.
A clean Git status alone could not establish that a checkout was disposable.

The exact finite migration in [#502](https://github.com/Valpatel/cad-agent/issues/502) ran once after writer/test
quiescence and independent review. It moved 121 retained linked worktrees plus one review-artifact directory,
retired only eight clean incorporated inactive non-provider trees, and preserved all local branch refs. Actual
readback verified the 143 remaining worktrees (108 toolkit, 35 product), HEAD/index/config/source status,
dirty/untracked bytes and ignored-directory identities. It repaired 54 symlinks and 101 environment metadata/
entrypoint paths without installation, checkout/reset or user-process termination.

Receipt SHA-256: `0f2b02d126e0770df0e93934f924d631ea63be7e42260b3f9c1e4fcace39a89b`.
[Independent final readback](https://github.com/Valpatel/cad-agent/issues/502#issuecomment-6759473764) confirmed
295 completed actions and no pending/error entry. Both project containers contain only `repo/` and `worktrees/`.

Cause: live workflow examples encouraged new project-name-prefixed siblings, while retained worktrees also
served as environments' source/dependency providers. The [contributor workflow](../../../.github/CONTRIBUTING.md#workflow)
now owns the contained layout and explicit starting directory. An isolated actual Git fixture validated owned
feature upstreams and detached integration fast-forwards; a detached HEAD cannot rely on an implicit pull upstream.

Rule: inventory refs, dirty/untracked/ignored content, ownership, process paths, symlinks and editable imports
before retirement or relocation. Preserve ambiguous trees intact, repair exact known consumers and verify the
post-state. Keep current source/runtime identities unchanged during a path move. Historical dirty main checkouts
remain historical; organization alone does not update or qualify their source. This finite reviewed migration
does not authorize unrelated deletion or establish browser, CI, release or physical-build acceptance.

## A cross-worktree browser probe needs one Playwright installation

On 2026-11-10 UTC, the first combined publication probe for PRs #504 and
Valpatel/gyropup#273 imported Playwright through both projects' retained dependency
providers in one Node process. Startup failed with `Requiring @playwright/test
second time` before any requested page was rendered. Both providers used the same
version; version equality did not make two module installations a singleton.
The failed packet remains a harness failure, not a product-render result.

The corrected probe imported only the toolkit's existing installation and used
that browser API for both products' owned ephemeral servers. The focused toolkit
packet completed eight actual Chromium/WebKit, desktop/phone, light/dark cases;
the changed map measured 276 px with no document overflow or page errors. The
separate favicon packet also completed its eight real cases. Both owned processes
closed their browsers/listeners; the shared user preview stayed in place. These
focused packets do not replace either PR's full current CI.

Rule: when a probe spans retained checkout/dependency providers, load Playwright
from one chosen installation per Node process. Reuse its browser API or run separate
processes; do not reinstall, flatten or delete another worktree's provider to hide
a module-identity collision. Preserve the first error and distinguish failure to
start the harness from failure of the application under test.
