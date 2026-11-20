# Exercise optional-import boundaries outside a CAD-enabled environment

2026-11-12, #542/PR637, source `e9b5faf949274b27748f932c2a32d749bff1993f`. Existing rendered-motion,
core/optional dependency and map-freshness guidance was searched. Local CAD-enabled tests passed, but they
could not establish behavior when CadQuery was absent.

**Dated command/output evidence:** GitHub job logs were downloaded through the jobs API before correction.
`core (3.12)` job [131464983949](https://github.com/Valpatel/cad-agent/actions/runs/43299002793/job/131464983949)
reported:

```text
tests/review/test_gate_assembly.py:1201: ModuleNotFoundError
FAILED test_native_serial_tool_approach_obstruction_and_stale_source_controls
ModuleNotFoundError: No module named 'cadquery'
1 failed, 3625 passed, 378 skipped, 1 warning, 39 subtests passed in 246.44s
```

The test imported `cadquery` before calling the guarded native fixture. Move the optional dependency boundary
to its first use (`pytest.importorskip`) so core absence is an explicit skip, while the installed native run
still executes the real geometry/tool control. Validate both modes in separate processes; native passes alone
cannot verify optional absence. This changes neither runtime dependencies nor a failed mechanical predicate.

The same head's actual Chromium job [131464443703](https://github.com/Valpatel/cad-agent/actions/runs/43298895294/job/131464443703)
failed `the actual repository map and generated inventory are current`: `docs/map.md is stale`. Regenerate it
with the existing `site-repo-map.mjs --write`; do not loosen its freshness assertion or classify it as an
intentional fixture error. The existing [map-freshness incident](../agents/2026-11-10-parallel-notes-share-a-layout-budget.md)
already owns that corrective procedure.

**Outcome provenance:** initial CI run `43298895192` at 20:17:55Z was cancelled after the single final body edit
at 20:18:31Z triggered replacement same-head run `43299002793` at 20:18:35Z. The only ready event was 20:03:26Z.
No author rerun/dispatch/cancel was issued. Original cancelled instances remain **NOT PASS**, and the replacement
core failure remains a real failure; core (3.10) matrix failfast cancellation is not success. The exact job
snapshot, errors and downloaded log hashes are preserved in
[`ci-failure-e9b5faf9.json`](../../../tests/fixtures/assembly-plan/ci-failure-e9b5faf9.json).

**Limits:** a simulated unavailable module validates the selected absence boundary, not a complete core install.
Current hosted core/full/browser checks and independent exact-head review remain required. Neither a corrected
test guard nor a fresh repository map qualifies product geometry, assembly paths, support or physical fit.


Corrected local checks, 2026-11-12: isolated unavailable-CadQuery process
(`sys.modules['cadquery']=None`, then pytest `tests/review/test_gate_assembly.py -k serial`) returned
`15 passed, 2 skipped, 85 deselected`; the installed native provider ran the same selection and returned
`17 passed, 85 deselected`. Canonical map regeneration reports 1051 folders; the unchanged owner/freshness
suite returned `28 passed, 1 skipped` (the separately owned CI-only diagram-render case). These bounded
results do not replace the required hosted core/full/browser suite.
