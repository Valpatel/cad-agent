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


## Search source identity before counting another document

On 2026-11-11 Pacific, the read-only follow-up to PR #574 at `35bf1477` found that its added overview record duplicated an existing core source. Earlier registry checks passed with 839 internal entries and 517 catalogued records, while public membership was reported as 810 records / 293 read / 517 catalogued. Those counts correctly counted IDs but overcounted one document.

Dated command/output evidence (2026-11-11; no vendor files copied):

```text
Complete PDF-URL inventory over refs.load().entries (urlsplit(url).path ends with .pdf):
https://www.pemnet.com/wp-content/uploads/sites/2/2022/09/Fastener-Guide_9-02-22.pdf
  pem-fastener-guide (source, core)
  pem-design-engineers-fastener-guide-2022 (source, guides-sheet.yaml)
Only this exact PDF URL was duplicated in the current registry.

Core record reading evidence:
2026-11-01: downloaded the 20-page PDF and skimmed it; no rule taken from it.
New reading evidence:
2026-11-11: all 20 PDF pages read; industry overview, not a universal numerical design table.
```

**Cause.** The author relied on a truncated publisher/keyword search and did not complete an exact-URL search across core and shards. The validator enforced unique IDs and aliases, not unique PDF locators. A deeper reading was therefore incorrectly represented as a new document, and the public-ID membership test did not catch the semantic duplication.

**Correction and rule.** Keep `pem-fastener-guide` canonical, preserve both dated scopes, and retain the newer long/short names as aliases. Merge the schema-2 metadata through the existing extension mechanism. Before adding a document, search the complete URL/title/alias inventory without truncating the relevant matches. The registry now rejects two effective read/catalogued records sharing an exact PDF URL, with a seeded core/shard duplicate and successful one-source extension control in `tests/review/test_references.py`. A real-registry regression verifies both aliases, both reading scopes and a single source identity. Record source-depth improvement separately from new-document or validated-evidence counts.

**Corrected scope.** Against baseline `295bac01`, this batch adds only the CE guide as a new document: internal 837→838; public 808→809; read 291→292; catalogued 517 unchanged. The overview receives a deeper reading, not another source or independent corroboration. No whole-family B guide is promoted from a BS-440-2 part page.

**Limits.** Exact URL equality does not discover redirects, mirror URLs, alternate query strings, same-content copies or edition changes. Different URLs are not proof of distinct documents. The guard makes no network requests and does not normalize URLs; edition and reading-scope reconciliation still requires human/source review. Source identity and reading depth do not establish physical qualification. Prior erroneous counts remain in PR/checkpoint history with this correction, not silently rewritten as successful knowledge gain.

## Short display aliases preserve source identity on narrow pages

On 2026-11-11, the existing reference/card/site checks passed for the next joint-interface batch, but a targeted
installed-Chrome check at 320 px found `document: 423` and rejected `page overflow`. Its DOM receipt identified
three `.ref-cite` badges: the OMW, NSK and General Bearing canonical source keys. The longest badge reached
423.25 px. The checker used the existing preview server, diagram bounds and `site-walls.mjs`; this was actual
rendered overflow, not a source-text estimate. The failed screenshot/receipt remains with PR588's validation history.

**Cause:** long canonical IDs were used as unbreakable displayed citation badges. A passing link/identity test and
an otherwise responsive table/diagram did not bound the rendered badge. The first full local site receipt also used
`--client-diagrams` output with tests requiring normal drawn output; its three producer-policy failures were retained.
The identical source head then passed 84 site checks with one explicit browser skip under the normal producer policy.
That source pass did not establish phone layout.

**Correction and rule:** preserve each exact document ID and URL; give a long visible citation a short alias on that
same record, and use it in prose. Do not add another record or rename the source to fix its badge. The existing
reference harness must check alias resolution, one canonical document and the actual rendered short label/link.
Check the real narrow page, disclosures and both themes; do not weaken overflow or reading-wall thresholds.

**Limits:** the three aliases change display and discovery only, not source count, evidence, dimensions or physical
qualification. The targeted Chrome receipt and normal new-head CI cover their stated viewports/engines; they do not
claim every reference page, browser or viewport has been examined. Licensed source PDFs remain outside the repo.
