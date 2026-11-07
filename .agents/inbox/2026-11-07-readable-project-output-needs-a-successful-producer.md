# A readable project file does not make a failed producer successful

## Observed on 2026-11-07 UTC

At released `e662a1ce`, `manufacturing.slicer.project_settings` read a fresh native-settings ZIP without first
checking the external command's return code. The existing project-settings test was parameterized at the external
boundary: the controlled command writes the same plausible ZIP for exits 0 and 7.

```text
PYTHONPATH=software:. python -m pytest -q tests/manufacturing/test_slicer.py -k project_settings_fit
old producer: 1 failed, 1 passed, 42 deselected
exit 7: Failed: DID NOT RAISE <class 'RuntimeError'>
```

The fake command is deliberate fault injection, not a real Bambu failure or successful GUI-open claim. The first
system-Python invocation lacked pytest; the measured command used an existing environment with this checkout
selected explicitly through `PYTHONPATH`.

## Why the original guard missed it

Parsing `Metadata/project_settings.config` established readable output, not successful execution. Separately,
the legacy plates exporter intentionally warns and succeeds without native settings, leaving a geometry-only
file that Bambu can collapse onto one plate. That fallback is useful compatibility behavior but insufficient for
a required project handoff.

## Corrective rule

Require command exit 0 before accepting its settings. Use `export-3mf --require-project-settings` for a handoff
that requires embedded native settings identities. Stage and validate strict plate outputs before publication;
reject settings/layout/read-back failures before per-part updates, preserving prior output bytes. The existing
consumer checks fresh valid output paired with exit 7, invalid/missing settings, actual CLI dispatch, final output
names and interrupted-publication rollback. Legacy default warnings remain available.

```text
PYTHONPATH=software:. python -m pytest -q tests/manufacturing/test_slicer.py tests/manufacturing/test_plates.py \
  -k 'not test_slices_a_cube and not test_bambu_studio_slices_each_plate_as_laid_out'
125 passed, 2 deselected in 1.70s
```

## Limits

These commands controlled the external boundary; neither real integration case ran. Required embedded settings
are not proof of the correct user-selected printer/material, Bambu GUI open/save/reopen, successful slicing or
physical fit/durability. Strict settings/layout rejection is protected before publication; this is not a general
transaction guarantee for subsequent per-part mesh export failures. The earlier cube-smoke lesson is indexed
under the same command-status failure class in `SYMPTOM-INDEX.md`.
