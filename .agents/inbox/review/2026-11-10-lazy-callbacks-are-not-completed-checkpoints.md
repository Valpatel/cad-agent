# A lazy callback result is not a completed checkpoint

Date: 2026-11-10. Scope: recoverable progress in the existing native playback gate (#517 / PR518).

## Evidence

Independent GPT-6 review at source `c9144a7d4276a9a21079f9a6ab159eb22f0bbff4` ran all 227 baseline tests
successfully, then used the existing clear-order box fixture with:

```python
def checkpoint(event):
    written.append(event)
    yield "saved"
```

The gate ran nine geometry queries, wrote zero events, returned complete=true and reported no failures. The
function call returned an unexecuted generator. The prior `isawaitable` guard correctly rejected coroutine
results but did not cover ordinary or async generators. See the actual
[inline finding](https://github.com/Valpatel/cad-agent/pull/518#discussion_r4527198217); the original native
preflight, shifted-frame and lazy-callback evidence remains in the independent review packet.

## Cause and corrective rule

Calling a callback does not prove its body ran if it returns deferred work. A synchronous checkpoint contract
must reject awaitable, generator and async-generator results before native work proceeds. The gate does not
iterate or await callback bodies. Close ordinary generator/coroutine objects without executing their work;
require the caller to complete writes, flushes and durability handling synchronously. Preserve a failing progress
check and stop, rather than calling an unexecuted callback successful.

The actual ordinary/async-generator regressions require zero geometry queries, zero written events, a failing
progress check and complete=false. Full-gate controls reject before native load. Ordinary synchronous callbacks,
JSON-safe nested mutation isolation, known collision witnesses and explicit remaining unchecked pairs remain
regressions in the existing harness.

## Limits

A synchronous return cannot prove a caller's chosen storage is durable; the product owns fresh output paths,
flush/fsync policy, process receipts and external runtime caps. Progress is not automatic resumption or a
clearance certificate. A killed process may leave only a valid event prefix, and uncompleted work stays unchecked.
No new callback execution model, planner or geometry engine is introduced.
