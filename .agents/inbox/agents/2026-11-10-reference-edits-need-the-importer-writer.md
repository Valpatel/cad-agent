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
