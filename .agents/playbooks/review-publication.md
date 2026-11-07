# Publishing review evidence without repeatedly restarting CI

1. Inspect workflow triggers and concurrency before diagnosing cancelled checks.
2. Finish the implementation, validation evidence and PR description, then push the final source checkpoint.
3. While final checks run, append status receipts as comments. In this repo, description edits restart Python CI because `edited` also covers base-branch retargeting.
4. If a description correction or retarget is needed, make it once and wait for the replacement run. Never treat the cancelled predecessor as a passing result.
5. Merge only under the repository rules, with independent review, resolved conversations and current-head checks complete.
6. Reference unfinished broader work with `Refs #N` or “#N remains open”. Reserve automatic-closing syntax for completed acceptance; negating the sentence does not disable GitHub's keyword parser. Check the actual default branch and verify issue state after merge ([observed mistaken closure](../inbox/2026-11-07-negated-closing-keywords-still-close-issues.md)).
7. Before public calls, bind the inspected existing runtime/browser and derive each ordinary asset or immutable source-record route from the pinned producer, not its repository path ([runtime incident](../inbox/publish/2026-11-07-publication-consumers-need-explicit-runtimes.md), [namespace incident](../inbox/publish/2026-11-07-source-records-need-their-actual-namespace.md)). Save raw responses before assertions and keep failed attempts distinct from corrected complete runs.
8. Preserve unexplained browser failures and diagnose their actual request/CSP evidence before any continuation. A reviewed finite classifier may separately retain an exact enforced provider block, with negative controls and zero external responses; all other errors stay blocking. Such acceptance does not fix provider injection or authorize CSP/settings changes ([diagnostic and limits](../inbox/publish/2026-11-07-provider-failures-need-matching-csp-evidence.md)).

Observed evidence and scope: [2026-10-29 incident](../inbox/2026-10-29-pr-description-edits-restart-ci.md).
