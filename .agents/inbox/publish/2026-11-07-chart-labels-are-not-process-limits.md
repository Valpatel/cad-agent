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
