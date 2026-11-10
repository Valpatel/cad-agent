**Changed**
- Agent and contributor examples keep the canonical checkout and linked worktrees inside one project container,
  preserving existing owners and dependency paths. The read-only `dev` example now updates its detached HEAD
  explicitly rather than relying on an absent pull upstream (#503).
