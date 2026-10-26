# Contributing

Several projects build on cad-agent at the same time (the J501 enclosure, Gyropup, the AGX Thor CAN boards, and
others), often with AI agents working in parallel. A change to cad-agent can break all of them, so every change
goes through a branch, a pull request, CI and a review.

## Branches
| Branch | What it is | Who writes to it |
|---|---|---|
| `main` | Released toolkit. Projects pin to it (or to a tag). | Only by merging a release PR from `dev`. |
| `dev` | Integration. Everything merged here has passed CI and review. | Only by merging a reviewed PR. |
| `feat/<topic>`, `fix/<topic>`, `ci/<topic>` | One piece of work. | Its author, in its own worktree. |

Both `main` and `dev` are protected: no direct pushes, CI must pass, and review conversations must be resolved.

## Workflow
1. **Worktree from `dev`**, never edit the main checkout another session may be using:
   ```bash
   git fetch origin
   git worktree add ../cad-agent-<topic> -b feat/<topic> origin/dev
   ```
2. **Commit** small, focused changes with tests (`tests/`). Keep the package generic: anything specific to one
   product stays in that product's repository.
3. **Open a PR into `dev`** with the template filled in, including what projects using cad-agent must change.
4. **CI** (`.github/workflows/ci.yml`) runs `core` (only the required dependency; optional features must skip
   cleanly) and `full` (CAD, FEA and site extras). Both must pass.
5. **Review.** A person, or a separate review agent that did not write the change, reviews the diff and leaves
   comments on the PR. The author answers or fixes each one; all conversations must be resolved before merging.
6. **Merge** into `dev` (squash or merge commit), then remove the worktree: `git worktree remove ../cad-agent-<topic>`.

## Releases
A release is a PR from `dev` into `main` titled `Release vX.Y.Z`, listing the merged PRs and any changes projects
must make. After it merges, tag `main` (`git tag -a vX.Y.Z`) and bump `version` in `pyproject.toml` on `dev`.

## Projects that use cad-agent
Install it editable from a checkout of `main` (or a tag), not from a feature worktree, unless you are testing that
feature. A project that needs a new toolkit feature opens a cad-agent PR for it; it does not patch its local copy.
