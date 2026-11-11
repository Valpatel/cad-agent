# Reading batches need the real release and whole-page consumers

Date: 2026-11-10 Pacific / 2026-11-11 UTC. This repeats the existing
[release and reading regression lesson](../2026-11-07-security-inventory-does-not-prove-settings.md#existing-ci-also-caught-release-and-reading-regressions),
not a new check or exemption.

PR #555 at `6e023f6c9d4112a30f4f7d1c05430f9b3794cd8d` added a bounded source reading, its planning prose and a
changelog fragment. The author's selected registry/importer/health/layout checks passed 272 tests; 15 fresh-head
site-reference tests also passed. Neither selection exercised the actual release parser or measured the full page.

Dated command/output evidence (2026-11-11 UTC):

```text
CI core (3.12), run 42959050782, job 130320993054
tests/repo/test_cut_release.py::test_this_repo_can_be_released
ValueError: 552-smoothon-reading.md: text before the first section heading (**New**, **Fixed**, ...)
1 failed, 3251 passed, 368 skipped

CI node tests/site/website-browser.mjs, run 42958836277
Chromium job 130320276849:
walls /research/process-profiles: 1327px, 29787-31114px, after "Tolerances"; limit 1200px
WebKit job 130320276559:
walls /research/process-profiles: 1325px, 29837-31162px, after "Tolerances"; limit 1200px
```

Cause: the author omitted the documented fragment heading and the already-prescribed cut-release suite, then
extended a continuous text stretch without the whole-page consumer. Passing registry and site-reference checks
did not establish either separate contract. Original failures remain in the
[PR checkpoint](https://github.com/Valpatel/cad-agent/pull/555#issuecomment-6787164314).

Correction: use the documented `**New**` section for the new source readings, and place the added planning detail
inside the page's existing native disclosure pattern. Source records, citations, prose, numerical claims, parser
rules and page thresholds remain unchanged.

Corrective rule: read `docs/changelog.d/README.md` and run all of `tests/repo/test_cut_release.py` whenever adding
a fragment. Select verification by every changed consumer, including published reading length when adding prose;
site-reference tests alone do not measure that length. Build and pure checks come first. Preserve the original
failure, and obtain current whole-page results through the repository's reviewed browser/CI workflow rather than
starting an unreviewed browser campaign.

Limits: the corrected source and local release/site checks do not themselves prove the new rendered length. The
corrected head still needs current CI and independent re-review. This recurrence changes no source-reading scope,
physical qualification, release level or protected branch.

After correction, the full cut-release suite plus registry/importer/health/health-apply/layout/area/skill checks
passed **312 tests** with the existing webkit-folder warning. The actual fragment parser accepts the `New`
section, repository-map freshness passes, and experts remain current. Source-byte comparisons retain the
reviewed registry and every planning sentence; only the disclosure wrapper is added.
