# Validate every current check instance and the actual topic delta

## Documentation changes still need the release parser

2026-11-12 UTC: PR636 at `ea38ded5720538cbb773b8ae9afad6b45dd27037` passed its focused content checks,
but normal [core 3.12 job 131442108262](https://github.com/Valpatel/cad-agent/actions/runs/43292456383/job/131442108262)
reported 1 failed, 3548 passed and 369 skipped. The failure was `test_this_repo_can_be_released`: the authored
fragment used `### Changed`, while `cut_release.read_fragment` requires `**Changed**`. The exact local command
`PYTHONPATH=software python -m pytest -q tests/repo/test_cut_release.py::test_this_repo_can_be_released`
also failed before correction. The content-test selection omitted the existing release parser; this was an author
error that CI correctly blocked, not a flaky test. Change the fragment, not the parser.

The initial draft's supply-chain job separately rejected a pending report row. Its log named the missing pinned
Anthropic URL; one finalized body edit supplied the completed online row, and replacement job 131442108235 passed.
The [receipt](https://github.com/Valpatel/cad-agent/pull/636#issuecomment-6834091302) preserves that earlier failure
and cancellation. Neither it nor the later parser defect may be counted as a successful superseded run.

**Rule:** even a prose-only change must exercise the actual parser for every new release fragment, alongside its
content checks. Use the existing [fragment format](../../../docs/changelog.d/README.md) and finish required audit
rows before waiting for final CI. Extend the existing publication procedure, not the acceptance rules.

**Limits:** these are release-input and description defects. No upstream plugin execution, compatibility test or
physical CAD claim follows from fixing them. Existing parser tests already cover malformed headings; another
test mirroring this typo would add no coverage. Fresh exact-head review and normal CI remain required.

## Start idle reviewers instead of queueing another message

On 2026-11-08 UTC, a CAD release owner sent a new retirement-review request with `collaboration.send_message`.
The root's `collaboration.list_agents` readback showed the reviewer as `completed`; queuing the message had not
started a turn. `collaboration.followup_task` started the reviewer, and the retirement subsequently received its
[actual acceptance](https://github.com/Valpatel/cad-agent/issues/482#issuecomment-6715190512).

The Gyropup owner then waited for an operator response already available as
[the exact-source clearance](https://github.com/Valpatel/gyropup/issues/8#issuecomment-6715072676). The operator
had not changed. After recognizing that clearance and rerunning the live preconditions, the owner completed
the merge and [one-topic retirement](https://github.com/Valpatel/gyropup/pull/264#issuecomment-6715284286).

**Cause and rule:** message delivery, an active review turn, and an existing review verdict are different states.
Check the agent state before assigning work: start/resume an idle reviewer; use messages for updates to an active
turn. Read the posted exact-source verdict before requesting another. Preserve independent source review and
fresh required merge gates, while routine owner checkpoints/readiness/cancellation need no invented extra layer.

**Limits:** the delay was not timed; there was no demonstrated source/ref loss or CI failure caused by this
dispatch mistake. Starting a reviewer does not establish a pass. A changed artifact or new substantive action
still needs its applicable independent review. This incident is workflow evidence, not a passing runtime test.

## Count required names without dropping duplicate check instances

On 2026-11-07 UTC, the first local merge guard for PR442 stopped before any GitHub mutation because it asserted
exactly ten `statusCheckRollup` entries. The actual `gh pr view 442 --json headRefOid,statusCheckRollup` response at
head `bb17922ba49511b0d66e9ea849e84f124a3481f9` contained eleven successful instances: ten distinct check/status
names, including two successful generic `gates` wrapper runs. Their Actions runs were 42368171070 and 42368488228.

The corrected guard required the complete expected name set and inspected every returned instance for success.
Fresh live gates then passed, and the normal merge reached dev `b39709877a22f78453be1225446d57155f265eed`.
The [checkpoint](https://github.com/Valpatel/cad-agent/issues/440#issuecomment-6706441185) retains the failed local
attempt and correction. The subsequent dev-to-main PR443 also displayed separate dev-push and PR check instances.

**Rule:** identify the expected checks and enumerate all current applicable instances. A fixed total is not the
contract; neither is taking one green row per name while ignoring another running or failing instance. Investigate
non-success and superseded runs under the repository's rules, retain their scope, and run the live review gates
again immediately before a merge. This was a local guard error, not a failing CI test, and no CI result was waived.


On 2026-11-12, a PR #616 body edit at unchanged `fed30ca4` intentionally triggered the workflow's `pull_request: edited` handling: CI run `43272837046` was superseded by normal run `43272914888`. `gh api repos/Valpatel/cad-agent/actions/runs/43272837046/jobs` retained five cancelled instances: mermaid-provenance `131373537135`, core (3.10) `131373537435`, installer-windows `131373537437`, core (3.12) `131373539656`, and full `131373540239`—all **NOT PASS**. The sixth listed job, supply-chain `131373539604`, succeeded and must not be relabelled cancelled. A separate generic gates wrapper job `131373883532` in run `43272915120` was cancelled and superseded by normal dispatch `43272998465`; it is also NOT PASS. The earlier gates workflow `43272830997` was cancelled overall, but its completed job `131373495524` was SUCCESS and retains that result. These are five CI-job cancellations plus one separate gate-wrapper cancellation, not six cancelled CI jobs. The replacement core 3.12 then found a real canonical-shard defect; its core 3.10 peer was fail-fast cancelled. Preserve the supersession and the separate defect, require complete new ordinary checks on the concrete fix, and finish description edits before starting acceptance observation. A body edit is not evidence that a cancelled check passed, nor permission to retry or waive a failure.

## Compare an integration repair to the current accepted base

During PR441's normal merge of that dev into the previously reviewed source-recovery head, `git diff --cached
--check` compared all inherited renderer changes to the old topic head. It reported upstream licence whitespace
and whitespace inside the generated Mermaid bundle. Those exact bytes had already passed the independent
renderer provenance and reproducible-build checks; rewriting them would break their source bindings.

The author instead proved `git diff --cached --exit-code b3970987 -- software/cadagent/webkit/vendor/mermaid`
was empty, required exactly the six intended topic paths to differ from current dev, and ran
`git diff --cached --check b3970987` successfully. All 207 selected registry/health/release/figure/layout/area tests
passed. The actual source-record merge was checked semantically: six recovered records matched the reviewed topic,
and all other core records matched current dev. The generated expert index was rebuilt from that union.

**Rule:** preserve verified upstream/generated bytes. Inspect the actual authored and conflict-resolution delta
against the intended accepted base, and prove inherited files are unchanged rather than excluding unexplained
new changes. This is not permission to waive whitespace in authored code, skip provenance, or substitute targeted
checks for current whole CI and independent composition review.

## Main's live release gate needs a real Git checkout

At the same release's PR443 boundary, running the exact dev gate source from a plain `git archive` directory
failed before merge: `release_fetch()` calls `git rev-parse --is-shallow-repository`, which exited 128 outside a
repository. The dev-only gate had not exercised that release path. The archived source being current did not make
its execution context valid.

A detached, owned Git worktree at exact dev `b39709877a22f78453be1225446d57155f265eed` provided the real context.
`python3 tools/ci_gates.py all --repo Valpatel/cad-agent --pr 443` then passed branch-flow, independent review and
release checks. No gate code or acceptance rule changed. Use a real current-dev checkout for all live gates;
record the failed attempt instead of calling a source archive an equivalent checkout.

## Resolve the existing Wrangler before diagnosing authentication

On 2026-11-07, `npx --no-install wrangler whoami` stopped in npm resolution: it requested an unavailable
`wrangler@4.158.0` and reported `npx canceled due to missing packages and no YES option`. Wrangler had not run, so
this was not an authentication failure. The already installed npm cache contained the previously used 4.86.0.

`npx --offline --no-install wrangler@4.86.0 whoami`, under the existing OS user and inspected Node runtime, completed
normal refresh. Private outputs were mode 0600 and the account identity matched the earlier configured account.
No package was installed and no account, permission or setting changed. Bind an inspected existing CLI when
resuming; do not install a new one, expose credentials or request login merely because an unqualified resolver
selects a different version. Successful refresh does not prove deployment or DNS/cache access.

## Preflight source sizes and rendered assertions before public verification

The first v0.26.0 ordinary publication probe on 2026-11-07 UTC saved eleven actual HTTP responses, then stopped
at `spawnSync git ENOBUFS`. Node's default synchronous child-output limit could not hold the committed
3,626,560-byte Mermaid renderer. Its saved public response was exact SHA-256
`0c594f6da77369c354eadcf8b3ebc083829150571b1d82af3578c53bb3a794b8`; the source-reading harness had failed.
A finite 16 MiB buffer and preflight of every selected source body corrected the local limit without changing
asset equality. The original failed receipt remains distinct from subsequent attempts.

The next attempt saved sixteen responses and completed one browser case before rejecting `tools/mermaid`
in the supply-chain page's visible text. That path was the target of the correctly rendered **Mermaid rebuild**
link, not its label. Offline replay of all five retained pages also caught a lowercase `mechanical` assertion
whose intended visible statement began **Mechanical allowables and FEA**. Raw HTML substrings are not a
rendered-content contract: they can match URLs or hidden markup that a reader never sees.

The corrected verifier retained raw checks and separately required the actual visible labels, an opened native
fold, and the exact visible rebuild link target. Before another public invocation, the same verifier passed
20 retained-page cases across Chromium/WebKit and phone/desktop widths. Sixteen mutations were rejected: wrong
link target, missing link, wrong label, and missing mechanical-scope text. External requests were blocked and
none were attempted in these offline controls. These results validate the verifier, not current deployment;
the complete ordinary response/browser receipt still needs its own independent acceptance in #440.

**Rule:** inspect the sizes of pinned bodies before spawning source readers, with a finite justified buffer.
Preflight the actual rendered contract against retained or locally generated pages. Check a link's label and
target independently, preserve meaningful case and scope, and reject missing or changed destinations. Keep
failed attempts and their real request/case counts; neither source bytes nor an offline positive control may
stand in for a complete public run. Do not loosen overflow, request-error, revision or asset-equality checks
when correcting a harness assumption. These bounded checks do not accept #381's separate cache policies.


## Replay publication checks against current document types

On 2026-11-07 UTC, offline preflight of a v0.23.0 smoke recipe against released v0.28.0 found eleven native kit
candidates where ten were expected: its role glob also selected the new human `.agents/agents/README.md`.
The actual installer reserves that filename and the plugin manifest lists two roles. Correcting the consumer to
agree with those native contracts retained eight skills and two roles, with missing/unlisted-role controls.

The first public attempt of that revised recipe then retained six HTTP bodies and failed before opening a
browser. It required every source and Markdown twin to contain a `# ` heading. The actual reviewer role uses
frontmatter and has no such heading; its served twin was correct. [Independent failure disposition](https://github.com/Valpatel/cad-agent/issues/381#issuecomment-6714553481).
Neither failure established a product or cache-policy defect, and neither was relabelled as a pass.

The next separately reviewed consumer compared complete Markdown bytes with the actual current-source build.
All ten canonical twins were pinned along with the build's current revision. Eleven positives included the
retained public role response without an H1; thirty altered, truncated or appended byte controls failed.
The unchanged complete identity and missing/unlisted-role controls also passed. The changed bounded public run
then completed all 70 ordinary reads and 56 header paint/control cases on both hosts, with stable release markers,
owned cleanup and [independent actual acceptance](https://github.com/Valpatel/cad-agent/issues/381#issuecomment-6714599323).

**Rule:** before replaying an older acceptance script, preflight every selected document type against the actual
native manifest and current built artifact. A human map is not an agent role; role frontmatter is not a promised
H1. Prefer complete canonical bytes to invented generic headings when the publication contract permits an exact
comparison. Keep invalid-script attempts distinct, correct the demonstrated assumption and review the changed
consumer and its negative controls before another bounded run. Retain source/version, browser bounds, identity
and byte equality requirements.

**Limits:** these controls validate the selected consumer and current public route/header scope. They do not
prove fresh-user agent discovery, every browser interaction or physical CAD quality. The ordinary 18-asset cache
policy receipt remains separate from the route/header smoke; no new source/provider behavior was needed to fix
the false H1 assertion.

## A feature matrix must stay a table in the actual Markdown consumer

On 2026-11-10 UTC, independent review of PR #509 source `a259f46c` found a blank line between three new
requirement rows and the retained guide matrix. The source still contained every requirement. The installed
locked Marked 16.4.1 consumer, under Node 22.23.4, emitted only four `<tr>` rows (header plus three new rows);
`Strict guide schema` was instead in a `<p>| ...` pipe-text paragraph. `strictSchemaIsPipeParagraph` was true
and `strictSchemaIsTableCell` false. This was a documentation publication regression, not a viewer failure.

The focused command used `createRequire(.../tools/site/package.json)('marked').marked.parse(...)` on
`docs/practice/assembly-guide-testing.md`, counted emitted rows, and inspected actual table-cell membership.
Removing the blank separator restored one contiguous matrix: the same consumer emitted 20 `<tr>` rows,
`strictSchemaIsPipeParagraph: false`, and `strictSchemaIsTableCell: true`. Orthogonal-plane, hover, playback,
strict-schema, resource-teardown and portable-ZIP requirements all appeared as table cells. The retained old
HTML fails that same membership check; the corrected output passes. No rendering threshold or framework changed.

**Rule:** when extending a GFM matrix, keep its rows contiguous and verify semantic membership through the
repository's locked Markdown consumer. Presence in source and a few surviving rows do not prove the retained
requirements are still cells. **Limits:** this focused parser proof does not establish browser table layout,
responsive overflow, full-page rendering, current CI or product feature acceptance; those keep their own checks.

The same review round caught a broad documentation replacement that retargeted a historical 18-case paragraph
from `cdbee23b` to the newer `a259f46c` 26-case label. The original 18-case attribution was restored; the new
26-case result stays in its separate dated paragraph. Keep counts paired with their actual source receipts;
updating a current coverage matrix must not relabel historical runs.

## Judge CI deferral by the actual event and current checks

On 2026-11-10 UTC, PR #509 deferred draft CI with WIP commit markers. Before its final source push, the owner
read GitHub's [documented skip behavior](https://github.blog/changelog/github-actions-skip-pull-request-and-push-workflows-with-skip-ci/)
and raised an unproved concern about a later normal-merge push. The coordinator checked an actual counterexample:
Gyropup main `6a026434f9002d1aecbcea860983fb322e372158` normally incorporated ancestor
`ea521b0453387a3d6254d121f65dc203b74eca52`, whose subject ends with the skip marker, while that main's ordinary
push workflows ran. `gh api .../compare/ea521b04...6a026434` reported `status: ahead` and the exact ancestor as
merge base; [one actual push workflow](https://github.com/Valpatel/gyropup/actions/runs/42785495381) completed
successfully, while the presentation workflow was still running at the readback.

**Rule:** preserve the WIP history and its exact-source evidence; keep the final head and merge message free of
skip instructions, and inspect actual push/PR events plus every required current check before integration.
Do not rewrite source history or invent a CI waiver from a hypothetical event interpretation. **Limits:** this
normal-merge counterexample does not establish how every direct push behaves, turn a skipped/pending check into
a pass, or permit integration without the repository's current complete CI and live gates.

## Required project changes determine the release level before cutting

2026-11-10 UTC: `tools/cut_release.py --patch` produced candidate `821625fe` with version `0.32.1`,
while its folded #520 fragment explicitly contained **Projects must change**: current flagged slices now make
`check`, `report` and `all` exit 1. Independent PR #530 review `5849100011` blocked the candidate under
CONTRIBUTING's minor-release policy. The initial patch instruction was mistaken; the producer accepted the
requested bump and did not decide semantic release policy. No v0.32.1 tag or production release was created.

Corrective rule: read the complete pending fragments before selecting the bump. Required project changes or a
new feature select minor even when another included change is a model/site fix. Correct a pre-publication
candidate with a normal follow-up commit, preserve its original attempt and all previously released history,
and compare against the existing producer's pure minor result from the exact pre-cut inputs. Do not rerun a cut
on the already dated candidate and manufacture a phantom released version.

The corrected v0.33.0 metadata matches that pure pre-cut minor projection; the folded bullets, v0.32.0 history,
source and five adopted model assets remain unchanged. This comparison and focused release checks do not
replace fresh exact-head CI/review, nor lift the separate accepted-Gyropup-CAD protected-main production hold.

## Enforce retirement boundaries under optimized Python

On 2026-11-11 UTC, independent review rejected the first v0.36.0 retirement operator before any deletion:
its read-only preflight included `git fetch`, which could update local tracking refs/tags, and mandatory
checks used Python `assert`, which optimization can remove. The initial operator SHA-256 was
`c81c831e999180bea59be8c4da93ad99d0c6d3b20831d5ed2907fbff50e3bda7`.
The [preserved incident](https://github.com/Valpatel/cad-agent/issues/575#issuecomment-6804632248)
records the command/output evidence and correction. Only preflight ran; no remote deletion was attempted.

**Cause:** debug assertions stood in for runtime enforcement, and a broad ref refresh crossed the declared
remote-only boundary. Treat fetch as a local ref mutation even when it is routine preparation elsewhere.

**Correction:** use explicit raise-based runtime checks, existing local objects for ancestry and fresh read-only
remote-tip queries. The corrected operator SHA-256 was
`3706174cc37f6f71ff9f70d9be6546a37c85191a1abe2cfc76ae8edcfd7eb2e4`.
`python3 -O <operator>` passed read-only preflight; an optimized wrong-main control raised
`Remote main/tag/tips changed` before creating an attempt marker or making a mutation. Review then
[passed the exact corrected operator](https://github.com/Valpatel/cad-agent/pull/585#issuecomment-6804642460).
A private exclusive-create attempt marker was flushed and fsynced before the single network attempt.
Atomic exact-tip deletion leases used the verified anonymous repository URL to preserve local tracking refs.
The [completed receipt](https://github.com/Valpatel/cad-agent/issues/575#issuecomment-6804679296)
records four retired refs; unrelated refs and every local worktree/provider remained intact.

**Rule:** mandatory operational checks must survive `-O` and `PYTHONOPTIMIZE`. Exercise optimized negative
controls without an operational write path. Declare the mutation boundary, reserve one attempt durably, and
use atomic compare-and-swap leases against the reviewed exact remote tips. An attempted or uncertain result
spends the marker; inspect actual remote state and obtain a fresh disposition rather than blindly retrying.

**Limits:** these controls establish only that operator's preflight and bounded retirement, not a reusable
retirement tool, current remote state or public-site acceptance. Do not rerun the completed operator. No local
cleanup, credential expansion, unrelated branch deletion or later publication follows from that receipt.

## Inspect actual startup annotations before a bounded recovery

2026-11-11 UTC: Gates runs 43096357358 and 43095592509 ended `startup_failure` with zero jobs/check-runs.
`gh run view` suggested a likely workflow-file issue; actual GitHub annotations instead reported internal
platform errors on unchanged dev workflow `958199ca`. That CLI explanation was a heuristic, not a diagnosis.
[Independent review](https://github.com/Valpatel/cad-agent/issues/323#issuecomment-6806750962) authorized one
recovery request per exact existing run. Both requests were accepted at 20:49 UTC. Fresh API and uncached page
reads at 20:55:21 showed startup failure again, updated at 20:53:08 and 20:52:32, with zero jobs. The API still
reported `run_attempt: 1`; an incremented attempt number was not observed. Fresh annotation request IDs were
`EDA8:4FD43:5E98E3:6526A6:6AF4D4D6` and `EDAC:1AB973:5F4BB7:65D6ED:6AF4D4D8`; cached reads showed old IDs.
No further retry occurred. No source tests were retried by this recovery or claimed to have passed.

**Rule:** inspect the actual annotation and exact run/workflow/head identity before classifying a startup
failure. Preserve original and recovery outcomes separately. A bounded infrastructure recovery does not
authorize repeated retries or waive normal checks. Fresh evidence matters when cached annotation IDs lag.

**Limits:** these annotations establish those startup errors, not the cause of all queued workflows or a general
service diagnosis. Later necessary source integrations and their new CI runs were separate work.

## Local live verification must not post Actions-owned statuses

2026-11-11 UTC: all source checks for PR592 passed and local live gates recognized the exact-head independent
review. The coordinator incorrectly ran local `all --post` to refresh a stale review status. GitHub rejected
the merge: required `cad-gates/dev/branch-flow` and `cad-gates/dev/review` were not set by the expected app.
No merge or ruleset change occurred at that rejection. The existing `tools/ci_gates.py` docstring already says
the local just-before-merge invocation runs **without `--post`**; the workflow owns posting.

One normal review-state Actions refresh, run43102319513, passed. The final preflight checked all current
checks, exact remote dev/head, resolved threads and live gates without `--post`; PR592 then merged at
`219766e8`. The rejection and correction are retained in the
[delivery checkpoint](https://github.com/Valpatel/cad-agent/issues/323#issuecomment-6807390375).

**Rule:** run local live verification without `--post`; use the existing Actions review refresh for app-bound
statuses. A locally posted success cannot satisfy that expected-app requirement. Preserve a rejected merge as
a rejection rather than treating later success as proof that the first preflight was sufficient.

**Limits:** this was an operator invocation error. The expected-app rule correctly prevented the merge; no
source defect, new automation feature or policy exception was needed.

## Deployment completion needs structured stage status

2026-11-11 UTC: a v0.36.2 pre-HTTP guard expected the literal `Active` in Wrangler 4.86.0's JSON deployment
table and stopped when it became `10 minutes ago`. No official-domain request had run. Inspection of the
installed CLI showed that `Active` title-cases an active stage; a relative age is returned only for a successful
stage with `ended_on`. The table is a presentation view, not the structured API schema. A read-only request
using the same refreshed credentials confirmed the exact main commit, production environment and completed
`deploy` stage (`success`, ended 22:37:54 UTC) before the approved readback
([checkpoint](https://github.com/Valpatel/cad-agent/issues/323#issuecomment-6809109150)).

**Rule:** bind deployment readiness to structured commit, environment, stage status and completion fields.
Do not infer completion from a presentation label or parse its age as a new status vocabulary.

**Limits:** this corrected a preflight assumption; no failed public verification was waived, and no account,
permission or deployment setting changed. It does not replace normal CI or the actual publication readback.

## Retain reader navigation evidence before closing a failed page

**Evidence, 2026-11-12 UTC, #625 / release #623:** WebKit job 131388834790/run 43277252434 at
`bae1820c` passed 103 component tests, then `site-outline.mjs:149` timed out after 30000 ms in
`page.goto('/docs/toolkit', {waitUntil: 'networkidle'})`. Later reader/layout cases did not run.
Independent inspection of artifact 13971626851 (SHA256
`0590eca06bedce050975bbc444ffc1cb2e23e9513cefa1d1732134da5f81c85a`) found 248 files but no
reader-boundary receipt, trace or network state. The failing viewport, HTTP status, pending requests
and DOM state are unknown. Identical reader/toolkit/runtime source at accepted 616ab and main 6e8 is
not evidence of a transient cause; the failed generated toolkit HTML was not retained.

**Cause and corrective rule:** the reader probe wrote its receipt only after every viewport, while
`finally` closed each failed page first. Preserve bounded observations and partial states before close,
then rethrow the original error. Keep the existing navigation wait/timeout and every readiness/geometry
predicate. The targeted repair records 24 samples per event kind, 300-character redacted URL/text
fields, 12 stylesheet entries, at most a 2 MiB viewport screenshot and 1000 ms per diagnostic capture.
Inert controls exercise success-without-capture, partial receipt before close, truncation/redaction,
failed/stalled capture and unavailable output without replacing the original error. These are simulated
page controls, not a browser reproduction or diagnosis of the old failure. Obtain exact-source review
before a normal diagnostic CI checkpoint; never relabel the original failed job or its skipped parts as passes.
