# Publication consumers need explicit existing runtimes

Search found [nonempty source selection and import origin](../2026-11-06-source-selection-must-not-pass-empty.md): a declared path is not proof of the consumer actually used. This is the corresponding JavaScript/browser incident from #424.

**Evidence, 2026-11-07 UTC:** the first v0.25.0 publication probe used ambient Node20.20.2 and Playwright's default browser selection. It failed before browser launch because the expected Playwright1194 executable was absent. Its retained receipt has zero HTTP readbacks and zero browser contexts; it is not a failed public page or a deployment result. An independent review accepted a corrected command binding existing Node22.23.4 and existing x86 Chrome151 explicitly. That one complete run then passed publication checks at main `eaf19a14b98832c4cb1fd7c2734c252f418cf8ce` ([acceptance](https://github.com/Valpatel/cad-agent/issues/424#issuecomment-6704558363)). No browser or dependency was installed in another session's environment.

**Cause:** an ambient executable and a package's default browser cache did not identify the reviewed consumer. A different installed browser was for another architecture and was not substituted.

**Recorded command/output:** the path-redacted corrected invocation was `<existing-Node22> /tmp/ca0250-public-chrome.mjs <retained-source-checkout> eaf19a14b98832c4cb1fd7c2734c252f418cf8ce`. Its receipt records Node22.23.4, explicit Chrome151, both stable released domains and `pass:true`. The original missing-browser attempt remains a separate failure rather than a successful runtime preflight.

**Rule:** inspect existing executable versions, architecture and required capabilities before public calls; bind the actual executable in the reviewed recipe. Preserve provisioning failures with their zero-call scope. A corrected runtime command needs its own complete retained run rather than relabeling the failed attempt. Do not modify shared environments or install a new browser merely to rescue an assumed cache path.

**Limits:** these receipts establish the named Node/Chrome consumer and actual tested pages. They do not establish every browser, platform or future cache contents. The subsequent production build used its own separately recorded Chrome156 runtime.
