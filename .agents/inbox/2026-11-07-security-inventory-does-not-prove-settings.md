# Missing security inventory does not prove a disabled protection

## Missing package metadata does not establish a missing archive licence

On 2026-11-07, the finite issue322 follow-up found that the exact `tools/mermaid` lock entry for Khroma2.1.0
omits `license`, while its integrity-verified archive contains the full MIT licence. The existing renderer
`BUILD.json` records `node_modules/khroma/license`, SHA256
`66b333b0f66759a0b710459e03f7029abe17f4358114a128d2c972e642961b49`, and the full text is already retained
in `THIRD-PARTY-LICENSES.txt`. Reading registry metadata alone would confuse an omitted declaration with
the absence of an actual licence.

The old missing-licence finding identified only a package name. An exception for that identity could silently
cover a different archive, version or production context. Bind the finding and any acceptance to the owning
manifest, version, resolved URL and integrity, and require its fingerprint. The actual-policy controls accept
only the exact read archive and reject another context, version, archive URL or integrity value.

The same principle applies to retaining a stale shipped parser: its age acceptance now includes recorded
package versions and all component file hashes. An updated version or legitimately re-recorded different byte
must trigger review again. Historical URL-age identities remain separate from the shipped-runtime decision.

```text
sha256sum <integrity-verified Khroma archive>/license
66b333b0f66759a0b710459e03f7029abe17f4358114a128d2c972e642961b49
python -m pytest -q tests/repo/test_resource_audit.py
128 passed
```

This is archive- and context-bound evidence, not a legal review, a new security assessment of all bundled
native code, or permission to accept advisories. No package, parser or renderer bytes changed in this repair.

## Observed on 2026-11-07 UTC

Issue 153's existing audit checked secret scanning but never independently checked push protection. It also treated
missing setting values as disabled and asserted that zero GraphQL manifests meant dependency alerts could not fire.
The real repository readback confirmed three disabled protections and enabled alerts; GraphQL returned zero
manifests and both the old and current SBOM export endpoints returned 404. These are distinct observations.

```text
gh api repos/Valpatel/cad-agent --jq '.security_and_analysis'
secret_scanning: disabled; secret_scanning_push_protection: disabled; dependabot_security_updates: disabled
GET repos/Valpatel/cad-agent/vulnerability-alerts: 204
GraphQL dependencyGraphManifests: totalCount 0, nodes []
GET dependency-graph/sbom and dependency-graph/sbom/generate-report: 404
```

Only setting names/statuses are retained here; no credentials or secret-alert contents were requested or recorded.
GitHub's general settings guide described public dependency graphs as permanently enabled, while its specific
enable-graph guide allowed enabling/disabling regardless of visibility. The UI tool had no available browser.
Neither that documentation conflict nor an API 404 established the actual setting or why discovery was empty.

The existing audit test file now injects independently enabled, disabled, missing and unknown protection values;
successful empty/nonempty graphs; denied, missing and partial GraphQL responses. Against pre-fix `20ced16f`:

```text
PYTHONPATH=software:. python -m pytest -q tests/repo/test_resource_audit.py \
  -k 'repo_protections or repo_graph_evidence or repo_settings_need'
12 failed, 7 passed, 90 deselected
```

After the fix, the complete audit test file passed: **109 passed in 5.46s**. These are controlled API responses,
not evidence that any live setting changed or that real dependency discovery succeeded.

## Corrective rule

Check each requested protection independently. Only explicit `disabled` means off; unavailable or unknown values
remain unverified. Validate the query response before accepting its graph inventory. Zero manifests means that
query observed none; inspect the default-branch manifests and actual service state before inferring a cause.
Keep unavailable observations in the audit's existing unverified set so historical findings cannot silently resolve.

The durable interpretation belongs in the existing [supply-chain guide](../../docs/practice/supply-chain.md).
Operational setting changes require their own authorization, independent review and actual readback. Issue 153
tracks those separately; this source fix does not establish their completion.

## Limits

The regression suite checks reporting semantics, not GitHub's internal discovery or the completeness of advisory
databases. No setting mutation, dependency submission or permission change is part of the audit implementation.

## Independent review extended the failure boundary

Review of PR430 reproduced an HTTP 200 with a JSON null body causing `AttributeError` before the new graph guard.
The final guard now checks the response type before accessing it; added null, list and string response controls keep
those outcomes unverified. The complete audit suite after this correction passed **112 tests**. Successful transport
alone does not establish a usable response body. The review and fix remain on the PR rather than being treated as
an unexplained retry of an external service.

## Existing CI also caught release and reading regressions

PR430 at `abeb60cd` failed the existing fragment parser: `153-repository-security-evidence.md` used `### Fixed`
instead of the documented `**Fixed**` section. Both actual browser engines also rejected the supply-chain page's
new unfolded guidance as a wall of text (Chromium measured 1213 px against the unchanged 1200 px limit).
The fragment now uses the existing format and the interpretation detail is in a closed `<details>` section.
No parser or visual threshold changed. Local release/layout/area checks then passed **69 tests**; fresh full CI
remains required. Keep these genuine failures on the PR rather than retrying the same source or calling them flaky.

The same boundaries recurred in #432 at `b6c7b166` on2026-11-07. Full CI passed3537 tests with20 skips and rejected
the322 fragment's missing section; independent parser calls also rejected427. Run the existing
`tests/repo/test_cut_release.py` for every new fragment: it parses every real fragment and simulates a cut. Its
supported `**Fixed**` heading preserves the intended bullets without weakening the producer.

That head's actual WebKit whole-site consumer also measured1262px (page693–1955) against the same1200px prose-wall
limit on `/docs/supply-chain`. Fold the optional maintainer explanation under a purpose-named disclosure, keeping
the npm/check table visible. Preserve its content, the actual whole-site gate and original failure; component/math
success and generated diagrams do not establish the entire guide's layout. Corrected-head CI remains required.

## Bind an accepted install hook to its owning package context

Independent review of #432 reproduced a real exception leak ([finding](https://github.com/Valpatel/cad-agent/pull/432#discussion_r4501363452)).
The new esbuild0.28.2 rationale said maintainer-only, but both npm contexts used `npm:esbuild` plus version as the
fingerprint key. An actual offline fixture with only `tools/site` received fp59651950683e8b3f and was accepted even
though that context runs ordinary installs. A manifest field on an inventory row did not constrain the acceptance.

Include the non-site owning manifest in the hook fingerprint together with its version. The corrected
`tools/mermaid/package.json:0.28.2` key gives fp30e8057fdbba6aa6; deliberately preserve legacy site's version-only
identity. With the actual committed policy and production matcher, `pytest -q tests/repo/test_resource_audit.py -k real_esbuild_hook_exception`
passed2 cases: same-version site-only remains unaccepted, and both contexts retain an unaccepted site finding plus
the intended accepted producer finding. These controls must not substitute a duplicated test acceptance.

This establishes the checked exception's owner/version boundary. It does not prove that every future command
disables hooks: retain the actual `--ignore-scripts` CI/producer evidence and review workflow changes. No advisory,
registry drift or binary mismatch is waived by this exception.
## Select the release producer, not only project release checks

On 2026-11-07 UTC, PR438 at `958ae5b7` repeated the `### Fixed` fragment mistake. The author's 198 selected
tests included `tests/publish/test_release.py`, which checks project release packaging, but omitted
`tests/repo/test_cut_release.py`, the repository release producer's consumer. Independent review
[5811778041](https://github.com/Valpatel/cad-agent/pull/438#pullrequestreview-5811778041) rejected the actual new
fragment. Running the omitted suite on that unchanged source exited 1 with the same Markdown-heading error.

The corrective rule is to read `docs/changelog.d/README.md` and include `tests/repo/test_cut_release.py` whenever
adding or editing a fragment. Its existing real-fragment loop already detects this defect; adding a duplicate
test or loosening the parser would not fix the selection mistake. The existing `tests/publish/test_release.py`
suite remains useful for its different packaging contract. Neither local suite replaces current whole-head CI.
