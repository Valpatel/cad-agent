# Resolve public fleet aliases before selecting a scheduler node

## Observed on 2026-11-07 UTC

The reviewed homepage CAD extraction used a public `cpu-a` label in its issue. Submitting the unchanged command
with `fleet-run submit ... --node cpu-a` returned:

```text
sbatch: error: Batch job submission failed: Invalid node name specified
fleet-run: submit refused or sbatch failed
```

No job ID was created and the CAD command did not execute. Reading the canonical `fleet-run` source showed that
`--node` is forwarded as a literal scheduler node, while aliases are only used for public reporting. The operator
resolved the NODE column belonging to `cpu-a` from a fresh `fleet-run nodes` result. The same reviewed command
and resource bounds then started job 240 on cpu-a. The refusal and correction are recorded in
[issue 422](https://github.com/Valpatel/cad-agent/issues/422#issuecomment-6704446293).

## Corrective rule

Before a pinned-node submission, inspect the CLI's current option contract and resolve the selected public alias
through its fresh node inventory. Require exactly one match. Keep the actual node value private; issue records
use only the job ID and public alias. A submission without a job ID is not a failed CAD run. Preserve its error,
verify the cause, and make one corrected submission without changing reviewed computation inputs.

## Limits

This records the observed CLI contract, not a promise that future wrappers handle aliases the same way. Successful
submission proves neither extraction nor artifact acceptance. Scheduler completion, source-preservation guards,
geometry checks and independent artifact review remain separate requirements.
