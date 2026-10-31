---
name: cad-pr-review
description: Use when a pull request in a cad-agent or product repo is ready for review, or when asked to review one. The author gets an independent review from a separate agent (the cad-pr-reviewer subagent, or a fresh Codex session) that did not write the change, answers every comment on the PR, fixes or explains, resolves the threads, and merges only under the repo's rules. Covers code, CAD geometry and simulation evidence.
---

# Pull request review

An author cannot review their own change: they read what they meant, not what they wrote. Every PR gets a review
by an agent or person that did not write it, and the review lives on the PR, where anyone can see it later.

## As the author

1. **Make the PR reviewable.** Description: what and why, how it was checked (commands and their results, the real
   project it was tried on, renders or reports), effect on other projects, and `Closes #<issue>`. For geometry
   changes, run `cad-agent all` first. Every row passes, "Holes clear" included, and you have walked
   [docs/common-issues.md](../../docs/common-issues.md). Push everything;
   the reviewer reads GitHub and the branch, not your session.
2. **Ask for the review.** In Claude Code, spawn the `cad-pr-reviewer` subagent with the PR URL and the checkout
   path. In Codex, start a separate session with the `cad-pr-reviewer` skill. Give it the PR, not your conclusions:
   a reviewer told what to find tends to find it.
3. **Answer every comment on the PR.** Fix it and reply with the commit (`Fixed in <sha>: ...`), or explain why not.
   Then resolve the thread:

   ```bash
   gh api repos/<owner>/<repo>/pulls/<n>/comments/<comment_id>/replies -f body="Fixed in <sha>: ..."
   gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:"<thread id>"}){thread{isResolved}}}'
   # thread ids: gh api graphql -f query='query{repository(owner:"<o>",name:"<r>"){pullRequest(number:<n>)
   #   {reviewThreads(first:50){nodes{id isResolved comments(first:1){nodes{databaseId body}}}}}}}'
   ```

4. **Merge only under the repo's rules**: CI green, a review exists, every thread resolved, and the user's go-ahead
   where the repo requires it (cad-agent: its required checks and gates; product repos say in their AGENTS.md). Where the repo has
   merge gates (cad-agent: the `cad-gates/...` statuses), they are required checks, and only an independent
   reviewer's pass verdict turns the review gate green. Merge commits, not
   squash, unless the repo says otherwise. After the merge, check that the linked issues closed and tick the
   tracking issue (`cad-work-tracking`).

## As the reviewer

- Read the diff (`git diff origin/<base>...HEAD` in a checkout of the branch, or `gh pr diff <n>`), the PR text and
  the linked issue. Do not edit, commit or push to the branch.
- **Verify before you post.** Run the tests that cover the change; for a claimed bug, reproduce it with a small
  script. Report only what you checked. Mark severity: blocking, minor, nit.
- For CAD and simulation changes, check the evidence, not only the code:
  - geometry: does the exported STEP/STL match the claim (bounds, volume, clearance numbers in the reports)?
  - physical assumptions stated and sourced: directions (fan flow, gravity, load), units, datum and orientation of
    any photo or drawing fit, which values are measured and which assumed;
  - simulations: converged and steady, energy or force balance closed, mesh dependence acknowledged;
  - nothing claims more than CAD can show (fit, strength and temperature are predictions until tested);
  - the [common-issues index](../../docs/common-issues.md), every row: each automatic check (for example "Holes
    clear") present in the report, passing and current. If one is missing, run it yourself without writing into the
    checkout (`cad-agent holes --out /tmp/<scratch>/holes.json`). Each
    review-only row is checked by looking at the model and named in the summary. A mistake the index does not list
    is a finding, and it is added to the index.
- Post inline comments on the exact lines (`gh api repos/<o>/<r>/pulls/<n>/comments` with `commit_id`, `path`,
  `line`, `side=RIGHT`), then one summary review (`gh pr review <n> --comment --body ...`) that says plainly whether
  anything is blocking. Its last line is the verdict marker for the head commit you reviewed:
  `<!-- cad-review verdict=pass sha=<full 40-character head sha> -->` when nothing blocking is left, otherwise
  `verdict=block`. A re-review after fixes posts a new summary with a new marker. Where the repo has merge gates,
  re-run them so they read it: `gh workflow run gates.yml -R <owner>/<repo> -f pr=<n>`. Do not approve or merge unless the repo's rules give
  the reviewer that role.
- Finish with a list of findings (file:line, severity, one sentence) for the author.
