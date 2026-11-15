**New**
- `cad-pr-review` skill: one review-criteria page (severities, checks for every PR and by change type, the evidence
  each needs, what a pass verdict does not mean), independence rules for the reviewer, and "Merging without the
  owner": when an agent merges into `dev`, which PRs need the owner's go-ahead recorded on the PR first (it never
  replaces a gate), and a post-merge checklist
  (#750).
- `cad-pr-review` and `cad-pr-reviewer` give the GitHub MCP tool beside each `gh` command, including the gate re-run
  and the merge, and a stated substitute for the local `tools/ci_gates.py` run in a session without `gh`. A verdict
  posted through a route that appends a footer after the marker turns the review gate green only once #751 is fixed
  (#750).

**Changed**
- `cad-agent agents install` reports `cad-pr-review` and `cad-pr-reviewer` as needing GitHub access through `gh` or
  the GitHub MCP tools, which it cannot check from here, instead of `gh` alone (#750).
