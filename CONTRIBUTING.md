# Contributing

Several projects build on cad-agent at the same time (the J501 enclosure, Gyropup, the AGX Thor CAN boards, and
others), often with AI agents working in parallel. A change to cad-agent can break all of them, so every change
goes through a branch, a pull request, CI and a review.

## Branches
| Branch | What it is | Who writes to it |
|---|---|---|
| `main` | Released toolkit, tagged `vX.Y.Z`. | Only by merging a release PR from `dev`. |
| `dev` | Integration, and the repository's default branch. Everything here passed CI and review. | Only by merging a reviewed PR. |
| `feat/<topic>`, `fix/<topic>`, `ci/<topic>` | One piece of work. | Its author, in its own worktree. |

`main` and `dev` are protected: no direct pushes (admins included), no force pushes, both CI jobs must pass and
every review conversation must be resolved.

## Workflow
1. **Worktree from `dev`.** Never edit a checkout another session may be using:
   ```bash
   git fetch origin
   git worktree add --no-track ../cad-agent-<topic> -b feat/<topic> origin/dev
   cd ../cad-agent-<topic> && git push -u origin feat/<topic>     # the branch tracks itself, not dev
   ```
2. **Commit** small, focused changes with tests (`tests/`). Keep the package generic: anything specific to one
   product stays in that product's repository.
3. **Open a PR into `dev`** (`gh pr create --base dev`) and fill in the template, including what projects using
   cad-agent must change.
4. **CI** (`.github/workflows/ci.yml`) runs `core` on Python 3.10 and 3.12 (required dependencies only; optional
   features must skip cleanly) and `full` (CAD, FEA, robot and site extras, imported loudly before the tests).
5. **Review.** Every PR gets a review from a person or from a separate review agent that did not write the change,
   posted as PR comments. GitHub cannot enforce this here (one owner account cannot approve its own PRs), so the
   merger checks that a review exists. The author answers or fixes each comment and resolves it.
6. **Merge** into `dev` (squash or merge commit). Then, before removing the worktree, repoint anything installed
   from it: `pip show -f cad-agent` (or the `direct_url.json` it lists) in each project venv tells you where
   `cadagent` comes from. Reinstall those from the `dev` checkout below, then `git worktree remove ../cad-agent-<topic>`.

## Using cad-agent from a project
- **Released:** a checkout of `main` (or a tag), installed editable: `pip install -e "<checkout>[cad,fea]"`.
- **Latest reviewed:** a dedicated worktree that only tracks `origin/dev` (`git worktree add ../cad-agent-dev origin/dev`,
  updated with `git -C ../cad-agent-dev pull --ff-only`). Never edit in it.
- **A feature under test:** that feature's worktree, while its PR is open. Say so in the PR.

A project that needs a new toolkit feature opens a cad-agent PR for it; it does not patch its local copy.

## Releases
Releases are cut when the user asks for one.
1. On a `release/vX.Y.Z` branch from `dev`, bump `version` in `pyproject.toml`; PR it into `dev` and merge.
2. Open a PR from `dev` into `main` titled `Release vX.Y.Z`, listing the merged PRs and what projects must change.
   Merge it with a **merge commit** (not squash or rebase), so `main` and `dev` keep a common history.
3. Tag the merge commit on `main` and push the tag: `git tag -a vX.Y.Z -m "..." origin/main && git push origin vX.Y.Z`.
