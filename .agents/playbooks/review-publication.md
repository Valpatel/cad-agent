# Publishing review evidence without repeatedly restarting CI

1. Inspect workflow triggers and concurrency before diagnosing cancelled checks.
2. Finish the implementation, validation evidence and PR description, then push the final source checkpoint.
3. While final checks run, append status receipts as comments. In this repo, description edits restart Python CI because `edited` also covers base-branch retargeting.
4. If a description correction or retarget is needed, make it once and wait for the replacement run. Never treat the cancelled predecessor as a passing result.
5. Merge only under the repository rules, with independent review, resolved conversations and current-head checks complete.

Observed evidence and scope: [2026-10-29 incident](../inbox/2026-10-29-pr-description-edits-restart-ci.md).
