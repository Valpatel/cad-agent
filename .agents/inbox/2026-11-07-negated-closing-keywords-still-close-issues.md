# Negating a GitHub closing keyword does not prevent issue closure

## Observed on 2026-11-07 UTC

Release-preparation PR #406 contained this negated instruction in its body:

> do not close #84/#139 for their broader remaining work.

After its merge into `dev` (this repository’s default branch), #84 was CLOSED even though its broader acceptance remained incomplete. A read-only retirement preflight required the intended OPEN state and stopped before any branch action.

Actual GitHub event query:

```text
gh api graphql -f query='query { repository(owner:"Valpatel",name:"cad-agent") { issue(number:84) { timelineItems(last:5,itemTypes:[CLOSED_EVENT,REOPENED_EVENT]) { nodes { __typename ... on ClosedEvent { createdAt closer { __typename ... on PullRequest { number url } } } ... on ReopenedEvent { createdAt } } } } } }'
ClosedEvent: createdAt=2026-11-07T04:34:58Z
closer: PullRequest number=406 url=https://github.com/Valpatel/cad-agent/pull/406
```

The author restored #84 with `gh issue reopen 84 --repo Valpatel/cad-agent`; readback returned `state=OPEN, closedAt=null`. The original merged PR body and ClosedEvent remain unchanged as evidence. [Public correction and remaining scope](https://github.com/Valpatel/cad-agent/issues/84#issuecomment-6702548031).

## Why the prose guard failed

The human sentence prohibited closure, but its raw text still contained a closing keyword directly followed by an issue reference. GitHub recognized that sequence, without interpreting the negation. The close was a tracking error, not evidence that overrides, per-plate results or remaining GUI/physical acceptance had passed. #139 remained OPEN.

## Corrective rule

For partial work on a broad issue, use `Refs #N` or “#N remains open”. Do not put a closing-keyword-plus-issue sequence into a negated sentence, quote or example in PR/commit text. Reserve automatic-closing syntax for a bounded acceptance scope that is actually complete. Verify issue state after merge against that scope.

Keep the exact trigger quote in this repository lesson, not copied into a future PR description where it could trigger again. This incident concerns an observed PR-body/default-branch merge; it does not establish identical parsing for issue comments or every GitHub surface. No source, test, release or branch was changed merely to repair the mistaken issue state.
