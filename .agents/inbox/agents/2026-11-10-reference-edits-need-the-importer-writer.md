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


## Re-read imported claims against the exact current source before promotion

2026-11-11, [#589](https://github.com/Valpatel/cad-agent/issues/589): full reads of two SendCutSend articles and the Protolabs CNC-hole article exposed unsupported imported claim fragments. The live step-by-step bending guide defers flange limits to material/thickness data; it does not state the imported `max(0.500 inch, 4t)` limit. The current hole article says depth beyond roughly six diameters deserves review; it does not give the imported two-sided-machining recommendation. Dated full-read/visual/digest receipts are recorded in #323 comments6805460913 and6805534112.

Evidence: exact primary URLs returned200 on2026-11-11, and the saved HTML SHA-256 values are `29d55858f6814ef608ff7aeb6e4c1c66702d7012446ff12f55dbb40b09c4d478` (step-by-step) and `639cef92ba4b07ab4c626831cc0f19ec0430c3d5d6c2a4b48fea4a77760282c7` (hole article). Reading and source-table/diagram inspection support the qualified guidance, not the extra imported fragments. The regression harness exercises original convention/containment examples and rejects reintroducing claims into these three promoted records.

Cause: source snippets and other publishers' summaries were attached to an identity without establishing that each assertion occurs in that exact article. A same-publisher article is not independent corroboration.

Corrective rule: on promotion, compare each inherited claim to the exact read URL/edition. Remove absent assertions or locate and separately verify their actual source; never carry them forward as verified just because the record changes from catalogued to read. Retain the dated reading boundary, original identity/provenance and advisory language. Do not convert review triggers into universal numerical gates.

Limits: absence from the current article does not prove the assertion never appeared historically or is universally false. These reads do not qualify FDM parts, strength, supplier acceptance or current external specifications. No duplicate identity or physical/encoded evidence is added by reading alone.

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

## Bind signed table headers to the exact fastener family before deriving a window

On 2026-11-11, independent source review [5864880242](https://github.com/Valpatel/cad-agent/pull/588#pullrequestreview-5864880242)
blocked unpublished PR588 at `6d2a81fb`. The exact PEM CE PDF (SHA256
`396c9d3c1172c2d0bda54e2ac9fc452798febaa5551b28aa37030f8db4c1c2f7`), printed p.15/PDF p.8, has
TKA/TK4 top-sheet hole nominal 1.3 mm **±0.05** and base-panel hole nominal 1.0 mm **−0.05** only.
The encoded windows were instead 1.30–1.35 and 1.00–1.025 mm. Thus valid lower corners were rejected and an
oversize base hole was accepted. The review's [base](https://github.com/Valpatel/cad-agent/pull/588#discussion_r4542827663)
and [top](https://github.com/Valpatel/cad-agent/pull/588#discussion_r4542828374) findings retain the evidence.
A new magnified render of that exact table confirmed the signed headers. No erroneous window was published to main.

**Cause:** nominal cells were not bound carefully enough to their own signed header and family. A tolerance from
the neighboring TS4 table was carried into TackSert, and the top-hole minus side was omitted. The test goldens
copied those derived intervals, so the focused tests passed the same wrong transcription. Reading a full PDF,
viewing a small spread, passing tests and an intended evidence class did not establish source fidelity.

**Correction and rule:** record the exact family, nominal cell and signed tolerance before deriving endpoints;
retain those words in `as_printed`. The existing applied test now derives its independent expectation from the
nominal/plus/minus header fixture, accepts base/top lower corners 0.95/1.25 and upper corners 1.00/1.35,
rejects just-outside values and the former 1.025 mm base hole, and rejects the adjacent TS4 upper corner 1.015 mm.
Use both source-bound positive boundaries and wrong-family negatives. An independent source comparison still
matters: matching goldens alone can repeat the author's mistaken reading.

**Limits:** this is a correction to two geometry windows, not a universal signed-tolerance parser or a new approval
system. The source's other family-specific footnotes, installation conditions and application qualification remain
separate. The CE encoded claim must be judged on corrected source-bound software proof; no strength or physical
validation is created by correcting a transcription. Existing failed review/CI and old passing-but-insufficient
receipts remain distinct from the corrected-head checks.

## Preserve printed conflicts before deriving a clean rule

2026-11-11, #595: full readings of the two already-catalogued Stratasys PDFs exposed details absent from their snippets. The FDM July 2025 guide p.5 generally says four-times slice thickness, but its 0.020-inch row prints 0.100-inch wall. Page 8 visibly pairs 0.013-inch layers with 0.13-inch clearance. The SLS April 2023 guide p.3 prints a 0.002 inch/inch tolerance slope; p.10 instead prints 0.003 inch/inch and 0.1 mm/mm. The numerical pages/footnotes were visually checked; exact URLs/hashes and scope are preserved in #323 comment 6807874352 and the related process-profile review notes.

Cause: a clean multiplier, fixed tolerance floor or inferred decimal repair would hide source exceptions, proportional terms or unresolved units. Arithmetic alone cannot establish which supplier specification applies.

Corrective rule: preserve as-printed values, units, pages and unresolved status before deriving examples. Use the selected table row rather than extrapolating a general multiplier; a matching small-part floor does not resolve conflicting slopes. Supplier/process/material qualifiers stay attached. The existing process-profile test harness exercises the published examples with multiplier, decimal, unit and process-substitution controls. Canonical importer writing and all-real-shards round-trip remain required.

Limits: no supplier clarification, current application qualification or manufactured specimen was obtained. Reading and example arithmetic promote neither physical evidence nor a blanket encoded rule. SLS observations do not rewrite MJF, other suppliers' profiles or desktop-printer settings.

## Include the shard editing contract in the source-change check selection

On 2026-11-12, PR #616 at `fed30ca4de8ad2c70549aaec44368af442935612` reproduced the same writer mismatch. Hosted core 3.12 job `131373890676` failed `test_every_real_shard_is_editable` for `guides-cnc.yaml`; the paired core 3.10 job was fail-fast cancelled, not independently failed. Local Python 3.12.3 / PyYAML 6.0.3 reproduced the failure with `pytest -q tests/repo/test_references_health_apply.py::test_every_real_shard_is_editable`. The earlier 334-check selection omitted that suite entirely; its passes did not establish shard updater compatibility.

Diffing complete parsed strings and the canonical dump found only width-110 versus importer width-120 line wrapping in the two authored source blocks (`guides-cnc.yaml` and `guides-sheet.yaml`); neither had a changed embedded-newline value. The second shard was also noncanonical but the all-shard assertion stopped at the first. Rewriting through the existing `references_health_apply.ir.dump`, retaining each header, proved parsed-data equality and byte equality of every unrelated raw record block. Include health-apply **and** importer round-trip tests with registry and source-example tests for every shard edit. This is a formatting repair, not a provider-version diagnosis, new source promotion or reason to relax the canonical writer guard.

After the repair, the complete health-apply/importer/registry/source-example selection passed 195 tests in 46.67 seconds. A redundant local invocation overlapped that selection and exited 139 inside `yaml._yaml`/`CSafeLoader` while running `test_an_edit_that_would_fail_the_registry_check_is_left_out`; its cause is unknown, and overlap is only an observation, not a diagnosis. A subsequent serial check of that exact case, the all-real-shard round trip, Markdown images and layout passed 32 tests. No loader, dependency, threshold or test was changed to conceal the crash. Hosted new-head CI remains independent required evidence.

## Credit named people even when their organisation is recorded

On 2026-11-12, the accepted `c3010e61` public loader held 814 records, including 65 with both authors and organisation. The `recordRow`, `areaMd` and citation renderer selected `org || authors`, hiding the people in every such credit; discovery search also used organisation without authors. Examples include Stefan Hermann / CNC Kitchen, Chul Lee / BASF and Niko Mroncz / Xometry. This was a renderer projection defect, not missing source research or a reason to rewrite/promote registry records.

Use recorded people **and** organisation with whitespace/case deduplication, preserve safe original URLs and required vendor query parameters, and expose original-work links without implying commercial relationships. Fixture controls cover both metadata fields, each alone, missing/malformed metadata, escaping/unsafe URLs, author search and legacy outside-tool groups. Existing project identities are credits when no further author metadata is recorded; do not guess people from a hostname. Original sources retain their licences, scope and evidence state. Discoverability checks prove projection/search/navigation, not creator identity verification, relationship/endorsement, permission to copy or engineering validation.

The compact Explore prototype measured 941750 raw bytes / 147813 gzip versus baseline 856890 / 132119, with direct original destinations now present. Reference rows average599.60bytes, under the existing700 limit; 7503tags remain under9000. The raw absolute ceiling moves from900000to1000000bytes for those destinations; per-reference/per-item, gzip and DOM guards remain unchanged. Retain measured browser/mobile/keyboard/no-JS validation rather than replace content with an unrelated loading/minification system.
