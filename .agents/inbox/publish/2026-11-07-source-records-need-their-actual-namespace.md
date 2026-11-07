# Source records need their actual published namespace

Search found [repository ownership and served namespaces](../2026-11-06-source-selection-must-not-pass-empty.md#keep-repository-ownership-separate-from-served-namespaces). This records a new concrete verifier mistake from #427.

**Evidence, 2026-11-07 UTC:** the first v0.25.1 public probe fetched `/docs/img/gyropup/SOURCE.json` from the website and received404 after11 retained raw responses, with zero view/context acceptance. The released builder at main `a32c1e6700ab3c64f08c1f5441f01303498e103d` copies only SVG/PNG/JPEG/GIF/WebP from `docs/img`; it never promised a website JSON route. The four ordinary model/card assets already matched released Git. Independent review accepted the exact namespace correction: obtain SOURCE through immutable `raw.githubusercontent.com/Valpatel/cad-agent/<actual-main>/docs/img/gyropup/SOURCE.json`, asserting exact final URL, no redirect and released Git bytes. The four actual website assets and all source/model/banner bindings stayed unchanged ([review](https://github.com/Valpatel/cad-agent/issues/427#issuecomment-6705108925)).

**Cause:** the verifier inferred a public route from repository ownership instead of reading the pinned producer's copy contract. The404 was a verifier namespace error, not evidence of a product, cache or deployment failure.

**Recorded request/output:** `GET https://cad-agent.valpatel.com/docs/img/gyropup/SOURCE.json` →404; corrected `GET https://raw.githubusercontent.com/Valpatel/cad-agent/a32c1e6700ab3c64f08c1f5441f01303498e103d/docs/img/gyropup/SOURCE.json` →200,1308 bytes, SHA256 `12e50e9bc8ddb85f1293692a51e95d2638e283d5d1da26fd65018d12c090568e`. Both were retained by the actual Node HTTP consumer before assertions, not inferred from URL strings.

**Rule:** derive each expected artifact location from the released producer. Distinguish ordinary served assets from immutable source metadata; record both hosts/routes explicitly. Keep source metadata byte binding and actual ordinary-site asset comparisons. Save raw failures before assertions and preserve the original failed attempt when correcting the recipe.

**Limits:** a correct immutable source record does not prove the website served its associated model. Those four ordinary assets, actual viewer controls and both stable deployment revisions were separately checked in the complete accepted run ([actual acceptance](https://github.com/Valpatel/cad-agent/issues/427#issuecomment-6705278005)). No site route or cache setting was changed.
