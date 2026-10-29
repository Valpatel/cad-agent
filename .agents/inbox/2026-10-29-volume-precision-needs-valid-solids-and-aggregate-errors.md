# Volume precision needs valid solids and aggregate error estimates

2026-10-29, draft PR #71 / issue #70. Independent review: https://github.com/Valpatel/cad-agent/pull/71#pullrequestreview-5696024332.

**Evidence.** A private supplier screw/insert fixture had default conservation residuals -14.11652803 and -4.58890513 mm³. Holding its Boolean results fixed and refining only integration reduced residuals to approximately 0.00027 and 0.000064 mm³. That finding justified investigation, not a larger collision tolerance. Exact OCCT 7.9.3 source inspection then showed the draft's Gauss error estimator was face-relative, making multiplication by net volume unsound for cancellation.

Public negative controls found an open box shell wrapped as a solid could measure 6.4 mm³ and be accepted by the assembly. A reversed 2 mm cube was topologically valid, classified infinity as `IN`, and received a broad-phase `apart` result against a distant cube without a volume check. New regressions reject both before they can become passes.

**Correction.** Validate topology, exact surfaces and bounded interior first. Use the GK routine's summed absolute face-error estimate with its documented return-unit branch, plus refinement agreement. Spend uncertainty inside existing conservation tolerances; leave thresholds unchanged and retain `unknown` for unresolved decisions. Invalidate earlier cached algorithm results. Keep optional centroid evidence separate from mass decisions.

**Performance evidence.** Bounded independent public probes found full-sphere GK centroid moments cost 3.8–5.7 seconds per refinement, versus 0.0003–0.0007 seconds for mass only. A synthetic-suite attempt was terminated by its exact PID after roughly two minutes; no shared jobs or environments were changed. The fix disables GK moment computation and uses an optional separately refined centroid, omitted when unreliable. Do not call the uncomputed mass-only centroid a witness.

**Reproduce.** `PYTHONPATH=src python -m pytest tests/test_volume_precision.py tests/test_gate_relations.py -q`; `tools/volume_probe.py` holds private Boolean BREPs fixed and emits source/runtime/hash-bound numerical receipts. Private supplier geometry must not enter the repo.

**Follow-through.** Independent review at `773477b` caught two downstream omissions: containment support discarded the estimate while subtracting volumes, and its separate cache did not include the measurement policy. A controlled `0.0015 ± 0.002 mm³` pushed-volume estimate passed a 0.001 mm³ threshold. Support now carries summed errors, refuses uncertain decisions without a probe override, and invalidates old policy caches. Regression tests cover both the pushed and already-outside thresholds.

**Remote result.** The exact-head fixed-BREP rerun completed: GK residuals 0.00012211 / 0.00002023 mm³, total budget consumption 0.00021169 / 0.00002909 mm³, below the unchanged 0.01009256 mm³ limit. Common volume remains 3.288196 mm³, requiring a separate mating-geometry explanation. Sanitized numerical receipts are committed; supplier BREPs remain private.

**Limits.** Estimated integration errors are not rigorous bounds. Numerical consistency does not establish mechanical fit, thread strength, printability, harness access or physical safety. See [the detailed method, receipts and source links](../../docs/volume-precision.md). Review and current CI must cover the downstream correction before merge.
