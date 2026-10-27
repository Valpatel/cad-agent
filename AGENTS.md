# Rules for AI agents working in this repo

Read [CONTRIBUTING.md](CONTRIBUTING.md). Other agent sessions use and change this repo at the same time, so:

- **Never push to `main` or `dev`**, and never force-push a branch you did not create. Both are protected.
- **Work in your own worktree** on a `feat/`, `fix/` or `ci/` branch from `origin/dev`
  (`git worktree add --no-track ../cad-agent-<topic> -b feat/<topic> origin/dev`, then `git push -u origin feat/<topic>`).
  Do not edit or commit in another session's worktree, the `dev` worktree or the main checkout's working tree.
- **Open a PR into `dev`** (`gh pr create --base dev`), fill in the template, and wait for CI. Ask for a review by a
  separate agent or the user; answer every review comment on the PR, then resolve it. Merge only when CI passes,
  a review exists and its conversations are resolved, and only when the user has asked you to merge.
- **Before removing a worktree**, check no project venv still imports `cadagent` from it (see CONTRIBUTING.md).
- **Keep cad-agent generic** (housings, robots, boards, any 3D model). Product-specific code stays in the product repo.
- **State limits honestly** in code and reports: what a check or simulation assumes, and that CAD and simulation do
  not prove physical fit or strength.
