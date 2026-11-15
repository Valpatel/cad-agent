# A cloud session needs its own worktrees, venvs and fresh reviewers

On 2026-11-15 UTC one orchestrating cloud session ran several changes in parallel (#749, #752, #753, #755, #756).
Durable guidance: [cad-remote-runs, working from a cloud container](../../skills/cad-remote-runs/SKILL.md#working-from-a-cloud-container).

## The container does not have the `repo/` + `worktrees/` layout

**Observed:** the canonical checkout is the session's clone (`/home/user/cad-agent`), on a session-designated branch
(`claude/…`) rather than a `feat/` or `fix/` branch; topic worktrees sit beside it in `/home/user/worktrees/<topic>`.
`git worktree list` on 2026-11-15 confirmed this layout. **Action:** leave the clone's working tree untouched, create
each topic worktree with `git worktree add --no-track` on a `feat/`, `fix/` or `docs/` branch from `origin/dev`, and
push only that branch. **Limits:** that pushing topic branches instead of the designated branch needed the owner's
say-so is observed once, not confirmed; no GitHub record keeps it.

## A shared scratch virtualenv imports another worktree's code

**Symptom:** tests pass or fail for code that is not in the worktree under test. **Cause:** a scratch venv with an
editable install points at whichever worktree ran `pip install -e` last. **Action:** give each worktree its own venv
and check `python -c "import cadagent; print(cadagent.__file__)"` before trusting a run. **Limits:** observed once,
not confirmed; the editable-install behaviour itself is standard pip.

## Orchestration that worked

One orchestrating session; implementer agents each in its own worktree and branch; a cheaper checker agent for CI
logs and issue reading; and a freshly started reviewer given only the PR, not the author's conclusions. Review
findings that were nits were answered on the thread and carried to the next change of the same lines instead of being
pushed, so the reviewed head stayed reviewed. **Evidence:** #749's review left three nits; #756 carries them (a `dt`
lower bound and the browser-command docs), as its description states. **Limits:** one session's experience; the
pattern is not measured against alternatives.

[Agent setup incidents](README.md) · [Symptom index](../../SYMPTOM-INDEX.md)
