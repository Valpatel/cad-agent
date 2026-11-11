# Publication consumers need explicit existing runtimes

Search found [nonempty source selection and import origin](../2026-11-06-source-selection-must-not-pass-empty.md): a declared path is not proof of the consumer actually used. This is the corresponding JavaScript/browser incident from #424.

**Evidence, 2026-11-07 UTC:** the first v0.25.0 publication probe used ambient Node20.20.2 and Playwright's default browser selection. It failed before browser launch because the expected Playwright1194 executable was absent. Its retained receipt has zero HTTP readbacks and zero browser contexts; it is not a failed public page or a deployment result. An independent review accepted a corrected command binding existing Node22.23.4 and existing x86 Chrome151 explicitly. That one complete run then passed publication checks at main `eaf19a14b98832c4cb1fd7c2734c252f418cf8ce` ([acceptance](https://github.com/Valpatel/cad-agent/issues/424#issuecomment-6704558363)). No browser or dependency was installed in another session's environment.

**Cause:** an ambient executable and a package's default browser cache did not identify the reviewed consumer. A different installed browser was for another architecture and was not substituted.

**Recorded command/output:** the path-redacted corrected invocation was `<existing-Node22> /tmp/ca0250-public-chrome.mjs <retained-source-checkout> eaf19a14b98832c4cb1fd7c2734c252f418cf8ce`. Its receipt records Node22.23.4, explicit Chrome151, both stable released domains and `pass:true`. The original missing-browser attempt remains a separate failure rather than a successful runtime preflight.

**Rule:** inspect existing executable versions, architecture and required capabilities before public calls; bind the actual executable in the reviewed recipe. Preserve provisioning failures with their zero-call scope. A corrected runtime command needs its own complete retained run rather than relabeling the failed attempt. Do not modify shared environments or install a new browser merely to rescue an assumed cache path.

**Limits:** these receipts establish the named Node/Chrome consumer and actual tested pages. They do not establish every browser, platform or future cache contents. The subsequent production build used its own separately recorded Chrome156 runtime.

## Site checks also need an explicit runtime

**Recurrence, 2026-11-10 local date (#557):** integration head
`0d1a1e20e4b6bb427f56d613a91c527348b505ad` initially used ambient Node20.20.2 for
`node tools/site/compiler/site-repo-map.mjs --check`. The existing guard returned
`repo-map needs the existing Node 22 site runtime`. The combined pure reference/repo-map suite on that runtime
finished with 42 passed, 1 failed and 1 explicit opt-in browser-diagram skip. This was a runtime-selection failure,
not a source-record or owner-map defect.

Binding the already installed Node22.23.4, without installation or guard changes, made the standalone check report
1041 folders with owners and relative destinations checked. The complete corrected pure suite then passed
43 tests with the same one opt-in browser skip on that head. The invocation was
`CAD_AGENT_REPO_MAP_DIAGRAMS=0 <existing-Node22> --test tests/site/website-references.test.mjs tests/site/website-repo-map.test.mjs`,
with the same existing runtime directory first on `PATH` for child processes.

**Rule and limits:** apply the explicit-runtime preflight to local site consumers too. Preserve the failed attempt
separately, and rerun the complete affected command with the required existing runtime. These pure checks do not
measure a rendered page's reading budget or replace the repository's browser CI. No local browser campaign ran.

## Count browser worker tasks before removing the cgroup

**Evidence, 2026-11-07 UTC (#463):** a local study ran the unchanged README motion and header parts together in their original two lanes, under a four-CPU quota, 2 GiB memory cap and 256-task cap. Both initial pages reported `Page crashed`. At 19:25:11.862 UTC the kernel recorded a fork rejection by the pids controller in that exact owned unit, before the page-crash events. The original 16-file failure receipt and native protocol records remain retained ([independent failure disposition](https://github.com/Valpatel/cad-agent/issues/463#issuecomment-6712030363)). This was a local fixture limit, not evidence of the earlier CI README networkidle timeout's cause.

**Correction and observed result:** an independently reviewed, separately recorded one-run correction kept the same source, four-CPU quota, 2 GiB cap, 180-second lifetime, original two parts and all navigation/geometry assertions. It changed only the fixture's task cap to 512 and added native browser output plus before-launch/before-cleanup/after-cleanup own-cgroup counters. That run passed six exact document checks, 74 header cases and six motion controls. Its task peak was 350, with no pids rejection or memory OOM event; memory peaked at 1,118,048,256 bytes. All owned processes exited, and source/build hashes remained exact ([independent result](https://github.com/Valpatel/cad-agent/issues/463#issuecomment-6712166668)). GTK/default-session and Mesa warnings were retained, so this is not a warning-free or exact-host-parity claim.

**Rule:** inspect the actual owned cgroup's `pids.max`, `pids.current`, `pids.peak` when available and `pids.events`, alongside memory events, before cleanup removes it. Confirm the producer PID belongs to that unit. A CPU quota and memory cap do not establish sufficient task headroom; systemd task accounting includes individual threads ([primary documentation](https://github.com/systemd/systemd/blob/main/man/systemd.resource-control.xml)). Preserve the original failure and obtain an exact reviewed resource correction rather than relabelling it or increasing limits blindly.

**Limits:** 512 was sufficient for this specific two-part local WebKit26 workload on a 24-logical-CPU host. It is not a universal browser default. The original main `81b9fdc2` post-main 30-second README timeout remains unexplained; neither this pass nor native warnings identify or fix it, and the other 14 website parts were not run.
