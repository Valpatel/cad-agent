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
