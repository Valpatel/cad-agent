# Validate source partition identities before a map can erase duplicates

2026-11-12, #542 / PR637. Independent Astra review BLOCK on
`9b819b9a69f49bc37a6692dd3e00b0e081109a83`:
[verified finding](https://github.com/Valpatel/cad-agent/pull/637#discussion_r4555742929),
[review](https://github.com/Valpatel/cad-agent/pull/637#pullrequestreview-5881299370).
Existing finite/source-binding guidance and rendered-motion notes were searched first; they did not require
validation of the original mesh partition list before converting it into a name-keyed map.

**Command/output evidence, 2026-11-12:** the reviewer probes were read, then independently rerun before edits:

```text
PYTHONPATH=software <existing CAD Python> /tmp/pr637-astra-pack-probe.py
{"accepted": true, "source_instances": 5, "packed_parts": 6,
 "names": ["plate", "base", "rail", "plate", "fastener", "lid"]}
<existing Node22> /tmp/pr637-astra-browser-probe.mjs
{"state":"ready","parts":6,"error":null}
```

The mutation prepended a copied rail partition renamed `plate`, retaining the genuine later plate entry and
original plan/bin bytes. The original exporter and actual Chromium accepted six entries against five source
instances. The reviewed failure, source revision and probe hashes are preserved in
[`partition-failure-9b819b9a.json`](../../../tests/fixtures/assembly-plan/partition-failure-9b819b9a.json).
The original rendered/native acceptance remains a historical snapshot of that blocked head, not current proof.

**Cause:** the exporter's dict comprehension and mini loader's `Object.fromEntries` discarded the earlier
wrong duplicate before exact mesh hash/membership validation. Packing/rendering still processed the original
list, so the validated map and actual six-part scene described different populations.

**Corrective rule:** validate every original entry and require unique, nonempty exact instance IDs before any
hash/pose lookup map is built. Matching final keys, hashes or counts after normalization cannot recover lost
identity evidence. Reject same-mesh duplicates too; never choose a winner by list order. Keep exporter refusal
transactional and plan-enabled browser rejection before geometry allocation, with no radial fallback.

Existing exporter and actual Chromium/WebKit harnesses now retain both same-mesh and different-mesh duplicate
controls. Each keeps valid original plan/bin identities and expects refusal, no canvas/control/explode API,
and no output replacement. Pure Node coverage exercises the original-list boundary as well.

**Limits:** this addresses duplicate instance partitions. It does not establish source-to-mesh physical truth,
correct manufacturing intent, continuous clearance, internal module assembly, support, retention or hardware
fit. Fresh current-head tests, actual-renderer receipts and independent review remain required.
