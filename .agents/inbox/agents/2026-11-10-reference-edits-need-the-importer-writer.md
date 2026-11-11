# Reference edits must preserve the health updater's canonical layout

On 2026-11-10 (local date; CI log 2026-11-11T03:48:18Z), PR #546 at
`15c559492901f563b234b7ab11d1a19d8371833f` passed registry validation but failed
`tests/repo/test_references_health_apply.py::test_every_real_shard_is_editable` for `projects-wheel.yaml`.
Core Python 3.12 reported **1 failed, 3251 passed, 368 skipped** in
[CI run 42954774146](https://github.com/Valpatel/cad-agent/actions/runs/42954774146).

**Evidence.** `python -m cadagent.review.references --check` returned 805 entries, 521 catalogued,
0 problems and 0 warnings. A direct call to `references_health_apply.editable(text)` returned `False`.
Diffing the YAML body against `import_refmap.dump(refs._yaml(body))` showed line-wrap differences only in
the two promoted records. The edit script had used `yaml.safe_dump(..., width=110)`; the importer uses
its own string representer and `width=120`.

**Cause.** The health updater deliberately refuses a shard outside the importer's exact layout, protecting
hand-styled content from a whole-file rewrite. Semantic registry checks do not test this editing contract.

**Corrective rule.** Serialize shard data with the existing importer writer, preserve the header, prove parsed-data
identity for a formatting repair, and run the existing health-apply suite alongside registry/import checks.
Do not weaken `editable` to accept the author's new layout. The promotion procedure in
[`docs/research/references/README.md`](../../../docs/research/references/README.md) carries this requirement.

**Limits.** A canonical round-trip proves updater compatibility, not source accuracy, licence permission or
reading depth. The formatting repair must not promote more sources or change the recorded reading scope.

## Derive public reference membership before comparing publication counts

On 2026-11-11 UTC, the v0.34.2 publication readback at main
`221d29d714972eab9a05ad83cbf8731b13572625` stopped at 05:03:33 UTC with
`AssertionError()`. Its count assertion was:

```python
assert {k: index['totals'][k] for k in ['records', 'sources', 'catalogued']} == {
    'records': 805, 'sources': 286, 'catalogued': 519}
```

The retained failed receipt has `pass: false`; this was a validation expectation error, not a product-data defect.
The exact committed core had 220 `sources`, 26 `unverified` and four `uncited` entries. The public loader includes
core `sources` plus non-extension shard records: 775 public records, 256 read sources and 519 catalogued records.
The internal loader's 805 entries included the 30 core entries deliberately excluded from public reference pages.

**Corrective evidence.** The corrected readback derived membership and status from the exact Git revision, then
compared the complete public ID set, counts and every source field of the four promoted records on both ordinary
public domains. At 05:05 UTC both domains passed with stable before/after release identity. The dated
[publication checkpoint](https://github.com/Valpatel/cad-agent/pull/556#issuecomment-6787581054) links the
[successful receipt](https://github.com/Valpatel/cad-agent/releases/download/v0.34.2/cad-agent-v0.34.2-publication-receipt.json),
SHA-256 `e812c84cb73063a9a77e68afee6d2958fb528d161909566020d707192bed4ff4`.
The failed script and receipt were preserved privately; no tracked source data changed to satisfy the assertion.

**Cause and rule.** The initial check substituted the internal registry size for the public membership contract.
For each release, derive the expected public IDs from committed core `sources` and non-extension shard records;
classify core sources as read and shards by the evidence ladder. Compare the complete ID set as well as counts,
then verify changed records' fields. Keep core `unverified` and `uncited` entries separate, as
`loadReferences().others` does. The existing `tests/site/website-references.test.mjs` already checks this loader
boundary and independently derives public records and totals from committed YAML; reuse it.

**Limits.** Historical counts describe this exact revision, not a fixed target for later releases. Publication
readback proves delivered membership and source fields, not reading depth, browser interaction, physical
qualification or the inclusion of internal-only records. Do not weaken those checks or promote a source to make
a public count match an internal one.
