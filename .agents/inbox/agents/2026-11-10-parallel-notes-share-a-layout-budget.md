# Parallel note additions share the final repository layout budget

Date: 2026-11-10. Two individually green feature branches added distinct incident records and then were combined.
The accepted physics branch and the playback-progress branch kept source/code/tests unchanged during the normal
merge, but together put 21 direct files in `.agents/inbox/`, exceeding its existing 20-file growth limit.

Dated command/output evidence from the combined tree:

```text
python3 -m pytest -q tests/simulation/test_robot.py tests/review/test_gate_assembly.py tests/review/test_gate_subassembly.py tests/publish/test_release_guides.py tests/repo/test_layout.py tests/repo/test_areas.py
2 failed, 288 passed in 55.34s
.agents/inbox/ holds 21 files, over the growth limit of 20
```

Cause: each branch was below the limit against its own base; independent passes did not establish the final
union's inventory. The correction moves the four review-domain incidents with `git mv` into `inbox/review/`,
adds its README/Mermaid map and parent entry, and updates every current link, including the moved numerical
incident's relative docs target. The root inbox falls to 17 direct incident files. No limit/exception is relaxed.

Corrective rule: check the real merged file inventory and all owning consumers after parallel work combines.
When a folder exceeds the existing growth rule, split by actual domain and preserve history, navigation and
references rather than adding an exception or dropping evidence. Existing integration and independent review
still apply to the resulting union.

Limits: this is a repository-structure check; it does not validate geometry, physical assembly or environment
providers. All older worktrees/providers remain untouched; only tracked notes in the owned feature tree move.

After the domain split, the identical combined command passed 290 tests in 54.44 s with only the existing
webkit-folder warning. A separate relative-link check examined 129 local links across the affected maps and
moved records, with zero missing targets. Approved playback and physics code/test bytes remained unchanged.

The first CI run of that split found another owning consumer that the local Python/link checks did not cover:

```text
2026-11-10, PR #518 head 455504c8, browser (chromium), run 42852649686, job 129957194630
not ok 40 - repository map publishes folder details without flooding the catalogue
every source-derived owned map needs its actual detail route: actual Set(107), expected Set(108)
missing: https://cad-agent.valpatel.com/repo/folders/d-.agents/d-inbox/d-review/README
not ok 127 - the actual repository map and generated inventory are current
docs/map.md is stale: run site-repo-map.mjs --write
165 passed, 2 failed, 1 skipped
```

Cause: adding the owned domain folder also changes the generated public inventory, even though moving its
incident notes does not change the toolkit runtime. The original failed run remains visible; it is a source
defect, not a browser startup failure. Run the existing `node tools/site/compiler/site-repo-map.mjs --write`
after adding or moving owned folders, then check its freshness and published-map consumers. The generator
added only the review-folder owner/route and updated the agent-folder count. With the existing Node 22
runtime and unchanged locked dependencies, `node --test tests/site/website-repo-map.test.mjs` then passed
28 tests, skipped its opt-in real-browser diagram test, and reported 1,041 checked folders. The full CI
website build and both browser jobs remain required; this local structural pass does not substitute for them.

## Long reference additions need their published-page checks again

On 2026-11-10, corrected-map head `ba8de8cc` passed all 168 website Node cases (167 passed, one skipped),
then both real browser consumers rejected the extended assembly testing reference page:

```text
run 42854404651, job 129963362700, browser (chromium)
walls /docs/practice/assembly-guide-testing: 1530px, 645-2175px; limit 1200px
run 42854404651, job 129963362158, browser (webkit)
walls /docs/practice/assembly-guide-testing: 1499px, 644-2143px; limit 1200px
```

Cause: the finite-path and progress references extended an already folded testing document with a new continuous
stretch of prose. Existing source, map and Python passes did not establish the rendered reading length. The
correction keeps both section overviews visible and puts their detailed controls/evidence in named native
disclosures, preserving every original instruction. No wall threshold, backlog exception or test changes.

A bounded actual Google Chrome 151.0.7922.71 probe imported the existing `site-walls.mjs` measure at 1366×800.
The immutable pre-correction page measured 1,503 px and failed the unchanged 1,200 px limit; the working-draft
correction measured 729 px, with its actual diagram rendered. Both new named summaries opened by ordinary clicks
and exposed the original BREP-binding and callback/storage-failure text. The probe used the existing Node/browser
and locked dependencies, and explicitly requested client-drawn diagrams; it is a local before/after control,
not the complete pre-rendered CI build or WebKit verdict. Original CI failures and their artifacts remain visible.

Corrective rule: after extending a published reference page, repeat its rendered-page consumers even when the
previous version passed. Keep a concise visible overview and accessible detailed references; verify each fold
opens and retains the engineering limits. Current-head complete browser CI still gates integration.


On2026-11-11, printable-checklist PR573 reconciled reviewed CI/PEM dev0ba1bc70 and pure layout/areas reported2 failures/27 passes: the union put21 files directly in `.agents/inbox/`. The new print-layout incident moved with `git mv` into the existing publication domain (20 files after the move), and its symptom/owner links were updated. No growth limit or exception list changed. Check the resulting union after integration, even when each original branch passed its own layout gate.


## Serial-plan reference extensions reopened both reading walls

On 2026-11-12, PR637 source `27c3b33114602c470a20b9d2e7c674b67b9f698c` failed actual browser
run `43301340964`: Chromium job `131473027065` measured assembly-guide/testing at **1352/2277 px**;
WebKit job `131473026431` measured **1346/2272 px**, against the unchanged **1200 px** limit. Earlier
native, source, map and bounded viewer passes did not cover the published reference pages.

The serial-plan contract and repeated receipt/history paragraphs had extended the visible page after its
last diagram. Keep that complete reference in a named native disclosure with a concise visible overview.
Show the existing source-derived rail/plate/roof illustration where it explains the canonical plan, before
the longer native-preflight chapter; do not add a decorative visual or change the wall predicate/backlog.

A declared working-draft/client-diagram diagnostic imported the existing `site-walls.mjs` measurement at
1366×800 and measured **1070/945 px in Chromium**, **1065/940 px in WebKit**, with loaded source illustration,
rendered diagram, and an ordinary click exposing the original receipt command and physical-build limits.
The first probe asked for the wrong exact phrase (`physical qualification` rather than the retained
`physical build qualification`) inside the disclosure; that probe error was retained and its text oracle
corrected without changing the engineering limit. These are draft diagnostics, not hosted acceptance.

The same hosted WebKit job also reported a shared-reader short-layout containment failure. Independent
artifact comparison found unchanged reader inputs; the suspected resize-readiness race was not demonstrated
as a production defect. Preserve that separate failure and require fresh current-source CI rather than
claiming the documentation correction fixes it. Exact raw-log hashes and scoped reading evidence live in
[`reading-witness.json`](../../../tests/fixtures/assembly-plan/reading-witness.json).
