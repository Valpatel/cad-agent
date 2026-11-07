# Provider request failures need matching enforced CSP evidence

Search found [actual image consumers](2026-11-07-image-motion-needs-the-image-consumer.md) and the [publication review procedure](../../playbooks/review-publication.md). Neither a provider URL nor a generic HTTP response established why this browser request failed.

**Evidence, 2026-11-07 UTC:** a corrected v0.25.1 probe retained35 raw readbacks/22 final contexts, then rejected a provider request on the second domain's390px/light homepage. The first domain had completed its four homepage cases. The request collector initially saved only the URL, so the cause remained unknown. Generic HTTP homepage bodies and released Git lacked the provider script; that alone did not prove a CSP block.

A separately reviewed single affected-host browser diagnostic at stable main `a32c1e6700ab3c64f08c1f5441f01303498e103d` retained actual navigation bytes/headers, DOM scripts, CDP initiators/failures, structured Playwright failures, console and CSP events before interpreting the error. Browser navigation and DOM contained the injected script. Exactly `https://static.cloudflareinsights.com/beacon.min.js/vce701823e78c4301a35b7e07294d87301792088814092` had GET/script/`errorText=csp`, CDP `blockedReason=csp` with parser initiator, and a same-URI `script-src-elem` event with disposition `enforce`. There were zero provider responses/page errors and the actual model reached ready, exploded and restored ([independent diagnostic acceptance](https://github.com/Valpatel/cad-agent/issues/427#issuecomment-6705186968)).

**Cause:** this observed failure was enforced CSP blocking a script injected into the deployed browser navigation. The generic-GET/browser difference does not identify which provider setting or delivery stage inserted it.

**Recorded command/output:** path-redacted `<existing-Node22> /tmp/ca0251-beacon-diagnostic.mjs a32c1e6700ab3c64f08c1f5441f01303498e103d` produced diagnostic receipt SHA256 `36e881a915a0e3765da1d1e2e66d59a4e100ca4be5de493b1ec0976cc58dc2ad`. The structured failure was `{method:"GET",resourceType:"script",errorText:"csp"}`; matching CSP disposition was `enforce`, and provider response count was0. Raw headers/DOM/CDP data were retained privately with0700/0600 modes; no account credentials or injection tokens belong in the public record.

**Rule:** keep unexplained errors blocking until the actual browser evidence identifies them. Any finite verifier classification must require the affected document host, exact URI, method/type/failure and a matching enforced same-context CSP event; require zero external responses. Retain classified failures separately. All first-party/model/page/unknown request failures and unclassified CSP events remain blocking. Do not wildcard-ignore a provider or broaden CSP to make a check pass.

The exact reviewed classifier had one positive and12 negative controls, including wrong host/origin/URI/method/type/failure, missing/report-only/wrong-directive/wrong-URI CSP and provider/other external responses. One full continuation passed both domains with36 raw readbacks/28 contexts/eight ready viewer cases, retaining four exact enforced CSP blocks and zero external responses ([recipe review](https://github.com/Valpatel/cad-agent/issues/427#issuecomment-6705214715), [actual acceptance](https://github.com/Valpatel/cad-agent/issues/427#issuecomment-6705278005)). The earlier failed attempts and single diagnostic were preserved; the successful API audit was not replayed.

**Limits:** the provider script remained injected but blocked in these observations. No provider setting, source, CSP policy, route or cache was changed or claimed fixed. Removing injection needs separately reviewed scoped evidence/action. This does not establish broader cache-policy acceptance, physical CAD qualification or untested browsers.

## WebKit can report an enforced block without requestfailed

On 2026-11-07 UTC, the finite #141/#322 verification completed 45 responses and 16 browser contexts on
both domains. The last second-domain WebKit catalogue interaction completed its filter actions and screenshot,
then the verifier rejected an enforcing `script-src-elem` event for the same exact injected beacon URI. There
was no `requestfailed` callback, external response or page error. The original receipt remains **failed**,
SHA-256 `67928e4cb7a5b697d74a6bd59593d87650ade31a87afa29b1660f251e2295dd3`.

Native WebKit protocol evidence at 17:59:24.221 UTC recorded a security-source error explicitly refusing the
exact script because it was absent from the CSP `script-src` directive. The actual navigation HTML contained
that URI, and both same-context CSP events had disposition `enforce`. The generated catalogue state and saved
1366×900 screenshot showed the requested area, kind switch and exact visible IDs. An independent reviewer
inspected the screenshot; its SHA-256 is `8907bf71b1b0408f2113a618b2bca75963f2e555730a41b0e7a91662f1175f24`.

A separately reviewed continuation rehashed the unchanged original source, receipt, all response bodies and
screenshot; checked the exact host, WebKit engine, catalogue route, URI, directives, enforcement, native security
message and injected HTML; and rejected 16 altered cases. It performed only the missing final second-domain
version read at 18:04:47 UTC, which returned main `c696d311a3ae6f648d4fbd660f9a824629af6374` with 90 pages and
220 catalogue entries. It did not replay browser actions or rewrite the original failed result. Continuation
SHA-256: `0c9bf3166aed03b4425d49bd17ab07c6b01eeb404bf344ccc3e01d430f80b17b`.
[Independent finite acceptance](https://github.com/Valpatel/cad-agent/issues/141#issuecomment-6711079606).

**Rule:** absence of Playwright `requestfailed` is not absence of an enforced CSP block. A separate WebKit
signature needs the actual native security message, same-context enforced event and injected-document evidence;
do not manufacture the Chromium failure fields or broaden an existing classifier to a hostname alone.

**Scope:** #141's accepted catalogue alternative and #322's dated report criteria were independently satisfied.
The wider #450/#446 public campaign remained failed and open. Match issue closeout to its actual criteria;
an optional wider campaign is neither a new global merge gate nor permission to discard its failures. No
settings or CSP change, provider-injection fix, current security re-audit or general browser acceptance is claimed.

## Script resource errors can accompany an enforced block

**Evidence, 2026-11-07 UTC:** the first v0.27.3 public campaign at main
`1463c144507f36aa9373cbb9407141d5a67a6b40` retained 73 raw readbacks and 37 contexts.
All 26 first-domain contexts passed, including the formerly failing WebKit navigation and copy cases.
The second domain's Chromium navigation actions completed, but finalization rejected one capture-phase
`window.error`: `Error event on SCRIPT`, targeting the exact beacon URI already recorded above. The original
receipt remains **FAILED**, SHA-256 `f577f18f51929a53d5b99126f2c198cc289086671c0f668feec8c979acdf369d`.
Fifteen contexts and the final revision reads had not run.

Independent review matched the same Chromium session's parser-initiated GET/script request, native
`loadingFailed` with `blockedReason=csp`, security-source console entry, injected navigation HTML and
identical response-header/enforced CSP policy. There was no external response or native runtime exception.
The captured event was a script resource-loading event, not the historical ResizeObserver runtime error.
[Actual failure classification](https://github.com/Valpatel/cad-agent/issues/450#issuecomment-6712875565).

**Recorded command/output:** one separately reviewed invocation of `<retained-continuation-owner> 1463c144507f36aa9373cbb9407141d5a67a6b40`
repeated the failed navigation context and ran the 15 missing contexts. Its 70 raw readbacks included both
ordinary domains' revisions and eight source-pinned assets before and after the browser actions. All 16
contexts and both real planted-window-error controls passed; owned browsers and the cgroup stopped cleanly.
The 36 earlier passed contexts plus these 16 form a finite composite, not an unchanged full-campaign retry.
[Independent actual continuation/composite acceptance](https://github.com/Valpatel/cad-agent/issues/450#issuecomment-6712983557). Earlier failed receipts
remain unchanged. Raw evidence is retained privately with 0700/0600 permissions; provider tokens and private
paths are excluded from public text.

**Rule:** collecting capture-phase window errors adds resource events as well as runtime ErrorEvents. Keep
both raw channels. An exception for an inert script resource event must require exactly one window event in
the context, exact script target/resource/document identities, absent runtime-error fields, matching enforced
CSP/header and native security evidence, and zero external responses or other errors. Retain the explicit
WebKit evidence path when `requestfailed` is absent; do not invent Chromium fields. The reviewed consumer
rejected 28 altered resource-event cases, including duplicates, runtime messages, wrong identities,
report-only/mismatched policy, missing native evidence and transport failures.

**Limits:** this does not remove provider injection or change CSP, cache policy or settings. It does not prove
the historical public ResizeObserver warning's timing/cause, explain the earlier README timeout, or qualify
untested browsers, installers or physical CAD. A revised, independently reviewed consumer must preserve the
failed run and bound its continuation; a quiet frame or a hostname-only filter cannot erase a failure.
