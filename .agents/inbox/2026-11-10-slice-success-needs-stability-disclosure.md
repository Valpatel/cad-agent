# A successful slice must retain an unchecked stability limit in the visible report

On 2026-11-10 UTC, the maintainer integration of #525 at
`f95941b519d9f41c93e6dede202bb4a9eaaa3cbb` preserved the author's reviewed
`2bb7ebac327caf3e70010d6267ed44966e34c688` implementation. That producer records
`stability_checked: false` and a reason for Prusa slices whose stability check is not known to have run.
The existing verification report displayed only grams and minutes for an otherwise successful row.
The follow-up was explicitly tracked in #522; no native slicer was run for this report change.

Evidence from the existing report test harness, with the regression added before the fix:

```text
python -m pytest -q tests/publish/test_report.py -k prusa_report
4 failed, 4 passed, 12 deselected
AssertionError: 'stability not checked' absent from '4 g · 12.5 min'
```

Both successful and flagged unchecked rows lost the disclosure. Checked rows and older rows without the
field passed the negative controls. After adding the label and the producer's recorded reason to the
existing row message:

```text
python -m pytest -q tests/publish/test_report.py
20 passed
```

The regression writes a source-current slice report, then exercises collection, serialized JSON and the
standalone HTML. It checks explicit false with/without a reason, checked and absent fields, and slicer
failures. Flagged rows still fail; otherwise successful slices still pass. Missing or stale slice reports
remain governed by the existing optional-slicing policy.

**Corrective rule:** carry a producer's explicit unchecked state and reason through every visible report
consumer. A successful operation does not mean every diagnostic ran. Do not invent a reason when none was
recorded, infer checked state for historical rows, or silently change exit policy while adding disclosure.

**Limits:** these are report/serialization regressions, not native slicing or physical-print evidence.
The author's native measurements remain their original #525 records. Stale-slice policy (#535) is separate.
