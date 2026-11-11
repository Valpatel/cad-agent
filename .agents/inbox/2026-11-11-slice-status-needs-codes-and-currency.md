# Slice measurements cannot replace producer status or current evidence

On 2026-11-11 UTC, issues #534 and #535 shared two status losses: `slice_project` discarded Bambu's codes before
the report's grams fallback, and `current_report` collapsed stale persisted data into the same None as no report.
A rebuild could therefore hide a previously flagged slice behind the optional "slicer not run" message.

Retained J501 CLI artifacts were inspected read-only; no new native slice ran. Selected output:

```text
python3 <read retained result.json and result-summary.json; print only codes, text, grams>
base: exit_code=0 return_code=0 error="Success." grams=188.33
base_stl: exit_code=239 return_code=-17 grams=0.0
```

The successful raw JSON has SHA-256 `4a97c363e687cfbb50b5716df41017a725add836751da3fdae45fd5bcd35f7b6`;
its summary has `b5013478baca9c8d50a3bd911e7826659c25ecabeb8da73960d823c8d0835654`.
The failed raw JSON has `a1b82a6679c2c29f2ce1aad5604743aa7cd58c6c20d0d39b71ed3b540ea4a7a4`;
its summary has `304abc9c7fa8a476d13f5832e56b2a694b4e4f12c73ec5b7a536faffcee13ecd`.
The native failure has no grams, so it is not a reproduction of failed-but-grams output.

Official producer source at BambuStudio revision `930fe93851afbc76b1c64dd37d8728b6a9afc89c` confirms
[integer zero for success](https://github.com/bambulab/BambuStudio/blob/930fe93851afbc76b1c64dd37d8728b6a9afc89c/src/libslic3r/Utils.hpp#L22),
["Success." in its message table](https://github.com/bambulab/BambuStudio/blob/930fe93851afbc76b1c64dd37d8728b6a9afc89c/src/BambuStudio.cpp#L124),
[integer code and text written separately](https://github.com/bambulab/BambuStudio/blob/930fe93851afbc76b1c64dd37d8728b6a9afc89c/src/BambuStudio.cpp#L489),
and [zero recorded on successful completion](https://github.com/bambulab/BambuStudio/blob/930fe93851afbc76b1c64dd37d8728b6a9afc89c/src/BambuStudio.cpp#L8836).
New success therefore needs grams, process exit zero and an integer result code zero; missing/invalid fresh codes
do not establish success. Genuine historical persisted rows without `ok` or either code field retain the
compatibility fallback.

Before the fix, controlled subprocess tests and persisted report mutations exercised the existing parser,
project report, collection and standalone JSON/HTML consumers:

```text
python -m pytest -q tests/manufacturing/test_slicer.py tests/publish/test_report.py \
  -k 'bambu_codes or stale_or_invalid or slicer_run_only'
20 failed, 64 deselected
```

Failures included `pass: true` with nonzero exit/result codes and stale reports turning a prior failure green.
Invalid top-level/parts shapes and unreadable report paths also raised instead of reporting a visible failure.
The implementation uses the existing current-report reader plus a problem reason, without a new report framework.
Verification fails on retained stale/invalid data and keeps genuinely absent reports optional; `slicer_run` still
means current. Existing release callers retain the current-only `current_report` contract.

After the fix, using the existing isolated Python dependency provider and Node 22 on the command path:

```text
python -m pytest -q tests/manufacturing/test_slicer.py tests/publish/test_report.py \
  tests/publish/test_release.py tests/cli/test_cli.py -k 'not slices_a_cube'
186 passed, 6 skipped, 1 deselected
python -m pytest -q tests/repo/test_layout.py tests/repo/test_areas.py tests/repo/test_cut_release.py
69 passed, 1 warning
```

The warning is the pre-existing webkit folder growth advisory. CLI checks cover `check`, `report` and `all`;
the last keeps real report collection but replaces unrelated build/native/package steps with controlled no-ops.

**Corrective rule:** preserve producer status alongside measurements, and distinguish absent optional evidence from
present evidence that no longer describes the source. Carry rerun actions into the existing report consumers.

## Independent review found two remaining persisted-consumer gaps

Review `5857857140` blocked the initial `e804489d39c34b2a5f8caf19cc4141b6298d60d3` head on 2026-11-11 UTC.
Its originally passing focused checks did not cover missing/non-string `slicer` metadata, malformed warning lists,
or contradictory persisted status. The reviewer reproduced crashes, passing malformed metadata, and `ok: true`
overriding exit 239/result -17/null. Removing `ok` while leaving failure codes also reached the old grams fallback.

Regressions added before the correction reproduced these exact consumer failures:

```text
python -m pytest -q tests/publish/test_report.py tests/cli/test_cli.py \
  -k 'stale_or_invalid or persisted_bambu_status or persisted_invalid_slice'
34 failed, 17 passed, 52 deselected
```

The reader now checks a nonempty slicer label and list-of-string warning/error/stability fields before formatting.
The Bambu row-status check independently requires explicit true plus integer-zero codes whenever any status/code
field is present, with visible reasons for missing, nonzero or invalid codes. It retains the untouched raw report,
including codes and producer text. Genuine old rows without all three fields keep the grams fallback; Prusa's
separate explicit-status contract remains unchanged. Source-current failed rows remain source-current, with
`slicer_run: true`, while their failure counts determine the result.

Final correction checks with the same explicit runtimes/provider:

```text
python -m pytest -q tests/manufacturing/test_slicer.py tests/publish/test_report.py \
  tests/publish/test_release.py tests/cli/test_cli.py tests/repo/test_layout.py \
  tests/repo/test_areas.py tests/repo/test_cut_release.py tests/repo/test_private_names.py \
  -k 'not slices_a_cube'
295 passed, 6 skipped, 1 deselected, 1 existing folder-growth warning
```

**Additional corrective rule:** validate the persisted fields the real consumer reads, and reconcile retained
status fields together. An omitted success flag is not historical compatibility when failure codes remain.
Earlier-head CI and this independent review remain separate evidence; a new source head requires fresh review/CI.

**Limits:** failed-but-grams cases are controlled regressions, not observed native Bambu failures. Retained native
artifacts and current upstream source characterize the code/text contract, not every Bambu version or output shape.
No printer, cloud service, camera, desktop app or heavy job was used. Report currency and slicer success do not prove
physical fit, print quality, strength or that an unchecked stability diagnostic ran.
