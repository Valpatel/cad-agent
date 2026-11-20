# Reading batches need the real release and whole-page consumers

## Published reading counts need their visible figures

2026-11-11 UTC: the first v0.36.2 publication verifier checked 19 JSON/document routes but omitted the actual
References and Experts pages. Independent review then found that a semantic-only graph comparator accepted
an SVG with `display:none`. The corrected finite verifier covered 21 routes per domain and rejected 29
planted identity, stale-label, hidden-figure, missing-path, zero-size and cropped-graph cases. Both domains
matched the fresh actual-main producer at `b30ee4b2`; the visible graphs showed 302 read and 507 catalogued
records ([public proof](https://github.com/Valpatel/cad-agent/pull/594#issuecomment-6809038090),
[review finding](https://github.com/Valpatel/cad-agent/issues/323#issuecomment-6808260828)).

**Rule:** verify the published figures and data against the actual producer. Preserve visibility and drawing
markup in the comparison; labels alone cannot establish that a graph remains drawn. Full figure/SVG byte
equality was appropriate for this controlled render. A future renderer or font change needs an explicitly
justified comparison with negative controls; it does not justify broadly discarding styles, shapes or size.
Keep a dated historical coverage figure distinct from live reading counters.

**Limits:** these checks establish served markup and source identity, not universal browser paint behavior,
physical manufacturing qualification or an unconditional byte-equality rule for every future renderer.

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

## Skill entrances need the whole workflow reading check

2026-11-11 UTC, #590 integrated source `c0b678ca`: normal WebKit run43103204961/job130799702528 passed100 pure checks, then its actual whole-page consumer reported:

```text
website-browser.mjs:723
walls /skills/sheet-metal-hardware/SKILL: 1208px with nothing to look at,
977-2186px, after "Bent sheet with clinch hardware and rivets"; limit1200px
```

This proves a reading-wall regression on that exact integrated route, not that the merge operation caused it. The skill's source-reading entrance preceded a long existing six-step workflow; selected source tests did not measure their combined rendered stretch.

Correction: retain the entrance and a visible ordered-action summary, and put the complete original workflow in a named native disclosure. Every step, source citation, call specimen, verdict warning and physical limit stays available. The existing1200px threshold and global styles remain unchanged. Measure the actual affected route, including phone containment and opened disclosures, rather than shaving a few pixels from the wording.

Local Chromium route evidence and its source digest are checkpointed with the correction; the existing local WebKit executable was absent, so Chromium cannot claim the hosted WebKit criterion has passed. Preserve the observed failure and require fresh normal exact-head WebKit CI plus independent review. No installed runtime, source-reading scope or physical qualification changes follow from this presentation correction.
