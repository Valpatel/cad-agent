# Read specimen labels separately from manufacturing limits

Search found the general rule in [Verify from source](../../../docs/lessons/process/verify-from-source.md).
This incident concerns a published manufacturing claim, not CAD or printer qualification.

**Evidence, 2026-11-07 UTC:** #163 left `sls-gap-vs-wall-eos` unverified. Downloaded EOS-authored
Franz-Josef Kerl, *Design Rules Overview LS*, 2011, from the registered reseller URL. PDF SHA256:
`7f5848e9f6e1222d6e177986b1e4a87395de2342455cd9e5f966f57ca8ef9967`.
`pdftoppm -f 10 -l 11 -scale-to 2000 -png` produced the inspected slides. Slide 10 varies gap specimens
across walls 0.30, 3.00 and 6.00 mm; slide 11 varies hole specimens across 0.30 and 0.60 mm. Images show
incomplete openings and measured dimensions unlike nominal labels. The combined minimum-gap/hole row was unsupported.
Source PDF and rendered pages are private scratch evidence under `/tmp/cad163-sources/`, not repository assets.

**Cause:** text extraction flattened chart labels into a plausible numeric range and conflated separate experiments.
The existing `u` guard prevented enforcement, but two tests depended on that particular incorrect production row.

**Correction:** remove the unsupported row, retain the interpretation with its source, and test the `u` rejection
with a planted unverified copy of a real profile. Compare the DFM result with that rule excluded to prove the
unverified value cannot decide the verdict. Keep HP cleaning dimensions separate from moving-part clearance.

**Validation:** the first scoped run retained four failures (230 passed): missing explicit wiggle-room metadata and
an outdated generated escape-hole chart. Added `wiggle: unstated` rather than guessing tolerances, regenerated the
chart through its existing tool, and the same 234 tests passed. Later source additions require fresh registry and CI checks.

**Rule:** render charts before promoting their numbers. Distinguish nominal input, measured output, failed specimen
and recommended limit. A readable source can justify dropping a row; it need not become a new numerical rule.
Use controlled test fixtures to retain rejection behavior when production data is corrected.

**Limits:** these are readings of historical supplier documents, not new physical tests. The retrieved HP chapters
and Xometry regional guides do not establish universal fit, fatigue or cleaning guarantees. The old Materialise
Standard Resin page was not recovered; current named-resin guidance is not evidence of a formal replacement.


## Keep source records editable by their health consumer

**Evidence, 2026-11-07 UTC:** PR434 core CI failed
`tests/repo/test_references_health_apply.py::test_every_real_shard_is_editable` on
`guides-print.yaml` at `90e6a342`. The scoped 342-test run had omitted this existing
consumer. The source records parsed and re-imported correctly, but the health updater
requires the importer's canonical YAML layout before it may rewrite a shard.

**Cause:** manually authored flow maps and folded scalars were valid YAML but failed
the updater's byte-preservation contract. It would leave the whole shard for manual work.

**Correction:** serialize only that shard through the existing writer, retaining its
header and asserting identical parsed values and unchanged hashes for all other shards.
The actual `editable` predicate changes from false to true; keep its existing regression
test and hand-styled-shard rejection unchanged. Run the health-update module alongside
the registry/importer controls and original-map check.

**Rule and limits:** source verification must exercise the readers that maintain the
records, as well as the rule-card and website consumers. Valid YAML alone does not prove
maintenance compatibility. A formatting repair does not re-read or re-qualify sources.

## Preserve material editions in detached figures

**Evidence, 2026-11-07 UTC:** #157's thermal follow-up reread the official Bambu PLA/PETG Basic V3.0 physical
tables and specimen conditions. PETG's Tg/HDT values differ from the old V2.0 row; PLA's do not. The existing
thermal figure producer stripped every parenthetical row suffix, so the detached SVG lost all three material
editions even when the Markdown table named them. A before-control using the original producer against the
updated table reproduced all three omissions.

**Correction and rule:** preserve each table label in this scientific figure and extend its existing regression
check to require the edition-bearing labels. Regenerate through the producer. Retain the older edition's
conditions in the guide and the source digest/read scope in the existing registry records; do not replace
mechanical allowables merely because a thermal table changed.

**Limits:** ISO 75 HDT and DSC Tg are typical specimen measurements, not continuous-use or clamp-creep
qualification. Reading a revised sheet does not identify a user's spool or supply the outstanding physical coupon.
