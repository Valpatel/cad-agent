# Keep artifact collection failures separate from the consumer result

On 2026-11-07, cad-agent #409 fleet234 at `06d491fc` built the real numbered example successfully (two specimens,
14.12 s). The selected native tests reported `F.`: the two-batch preservation consumer passed, but the envelope
consumer stopped at `import cadquery.importers` with `ModuleNotFoundError` before its geometry assertions.
CadQuery exposes `cq.importers`; that attribute is not a separately importable `cadquery.importers` module.

The collector's finalizer then attempted to archive the whole pytest temporary tree. Its strict regular-file
inventory rejected pytest's `test_labelled_coupon_real_geomcurrent` symlink. That collection exception masked the
original consumer failure and prevented the final source guard from running. The job remained **FAILED**;
the no-op engraving control was unreached. Complete producer/registry archives had already been sealed (14/5
files). A separate read-only frozen-clone check recovered the exact source SHA, empty tracked status and all
5,821 unchanged tracked hashes; it did not rerun geometry or turn the job into a pass.

**Corrective rule:** archive declared regular deliverables, not test-runner navigation aliases. Keep the strict
file-membership guard for actual products. Attempt final source/status guards even when diagnostic archival
fails; preserve the original consumer exception and report collection/cleanup errors separately. Verify the
actual library entry point before scheduling its native consumer. Reuse completed component evidence only at
its immutable source and state exactly which assertion/control never ran.

**Limits:** this was a test import and collector-finalizer failure, not a demonstrated coupon geometry defect,
provisioning timeout, Bambu acceptance or physical result. The corrected missing-scope native check requires its
own reviewed run. [Tracking and original recipe](https://github.com/Valpatel/cad-agent/issues/409#issuecomment-6702963460).

## Execute the predependency check, not only its syntax

Continuation235 at `165b52a7` was allocated but refused its own preflight before dependencies or native work
(exit1, command0s/total4s). Removing the bad import alone had left the actual call as `cadquery.importers`;
the promised `cq.importers.importStep` accessor was absent. Syntax compilation did not establish that semantic
precondition. The author and procedure review missed it before submission; no geometry assertion was reached.
Execute the exact standard-library preflight against the immutable candidate in a fresh output directory before
submitting. Check the actual call as well as the removed import, and retain the refused run.

The submit client's first status read also mistook the recipe's bare `node=` line for cached node metadata while
an assignment was pending. Read-only controller lookup recovered the already allocated235 rather than submitting
a duplicate. Use task-specific recipe variable names and treat an uncertain submission as uncertain until its
actual job is identified; this observation does not authorize a fleet-tool/configuration change.
