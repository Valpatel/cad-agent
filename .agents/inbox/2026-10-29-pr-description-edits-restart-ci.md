# Finalize the PR description before waiting for final CI

On 2026-10-29 UTC, updating PR63's description to include completed viewer evidence restarted the Python workflow even though its source head stayed `e283ff3ec841468a5e5bd6769a200f754ba82fbc`. The previous full job was cancelled while the browser workflow remained successful.

Evidence from `gh run list --branch feat/web-parts` and `gh run view`:

```text
40823965184  CI                 e283ff3  cancelled
40824243581  CI                 e283ff3  started 2026-10-29T05:35:09Z
40823965169  Webkit components  e283ff3  success
```

Cause: `.github/workflows/ci.yml` includes `pull_request: edited` so retargeting a PR reruns validation. Its per-PR concurrency group cancels the prior run. A body edit is also an edited event. This is workflow behavior, not a test failure or authentication problem.

Corrective rule: finalize the title/body before the final CI wait. During that wait, put incremental status receipts in issue or PR comments. Do not repeatedly edit the body to narrate individual jobs. If retargeting or correcting the description is necessary, do it deliberately and wait for the replacement run. Check both head SHA and the newest applicable checks before merging.

Limits: this applies to workflows subscribing to edited events and cancellation concurrency; other repositories can differ. Keep the intentional retargeting coverage. No workflow code changed, so no new regression test is appropriate. See [review publication procedure](../playbooks/review-publication.md).
