# Discovery and reading need one topic shell

**Design and test plan, 2026-11-12 UTC, #603.** The owner chose guides inside the same Explore layout and topic tree. The preceding #599 release made search coherent, but reading a result still leaves discovery for a separate flat section list; the Full catalogue destination retains a competing entrance. The right outline also inherits only foreground/muted theme tokens, so its hover can use the kit's pale default in dark mode. Footer dates currently discard the recorded commit time.

## Implementation boundary

- Extend the static compiler and existing gallery/nav components. No SPA, remote search service, dependency, source promotion or new manufacturing capability.
- Build one reusable topic-tree projection from `docs/areas.yaml` domain/area hierarchy and existing page/catalogue placement. A page can appear in relevant topics without duplicating its source identity. Keep an explicit cross-cutting group for pages not assigned to one process and a separate repository-map path.
- Explore remains the sole discovery entrance. Its nested topic tree, catalogue glyphs and useful type/source/adoption/compatibility facets lead to results or a focused reading view. Remove visible area maturity scores/bars/filters; machine data retains original fields and semantics.
- Reading pages retain their real current URLs, fragments, Markdown twins and article HTML. Surround them with the same Explore topic navigation and a compact search/back context; a dedicated right outline remains local to the article. Shared chrome must not inflate the article's reading width or bury its heading on phones.
- Absorb useful catalogue browsing into Explore. Old `/catalog` and its filtered/bookmarked URLs must remain meaningful, including canonical item anchors. Keep original JSON schemas, item IDs/aliases and external destinations. Compatibility is deliberate, not a blanket redirect that drops state or fragment.
- Complete the right outline's shared theme-token binding. Verify normal, hover, focus and current states in light/dark without lowering existing contrast thresholds.
- Format full recorded commit timestamps in `America/Los_Angeles` with an explicit PST/PDT label and a complete machine-readable `datetime`. Date-only source metadata must remain date-only; source update, build time and release revision are separate facts.

## Meaningful validation

1. Pure compiler/gallery tests: one shared hierarchy on browse/reader routes, real parent-child placement, icon reuse, visible maturity absence, preserved source counts/IDs/aliases and machine schema/data. Plant wrong topic placement, dropped compatibility query/anchor and erased timestamp controls where existing harnesses support them.
2. Route and link contracts: canonical old article/item anchors and filtered catalogue links remain usable; result-to-article navigation stays in the Explore shell. Legacy Markdown and JSON remain unchanged except release revision/build metadata.
3. Existing browser harness: update obsolete contracts to the new explicit design; retain visibility, keyboard, geometry, contrast, no-script and failure controls. Test dark outline hover/focus/current with the actual predicate and a failing-before fixture.
4. Coordinated bounded visual checks at desktop and phone: browse → nested topic → guide → local outline → search/back, useful compatibility filters, deep bookmarks, native no-JS navigation, readable article width and loaded glyphs/images. Measure initial height/DOM/payload and existing reading-wall predicate. No allowlist or threshold relaxation.
5. Exact-head independent GPT-6 review and normal current-head CI precede integration. Main/public primary-site acceptance precedes closing #603; alias registrar scope remains separate.

## Operational rule and limits

Inspect script parsing before invocation, including `--help`. Local producer commands use explicit existing Node 22 and `--client-diagrams` inside a reserved owned cap; never infer browser-free execution from a broad test filename or `CAD_AGENT_SITE`. Coordinate the browser lane first. Do not replay prior spent release/retirement operators. Keep the coordinator-managed claim active until it is explicitly completed by its owner.

This plan promises a bounded navigation/readability feature. It does not establish source evidence, physical qualification, universal search coverage or public deployment before the corresponding receipts exist.

**Prototype measurement:** rendering every catalogue note, cover and related-link list inside Explore produced 1,097,016 raw bytes / 151,329 gzip bytes / 10,035 start tags. This duplicated the existing catalogue feed and exceeded the compact-view contract. Keep default search metadata compact: rich catalogue details enhance a native disclosure from the same-origin, revision-bound existing `/catalog.json` only when opened. The legacy compatibility view retains its static full entries and old bookmarks; ordinary Explore users do not need that route. Keep the original absolute payload safeguards; measure before granting any representation budget. This is not a new search index or an evidence promotion.

## A document rail needs the same complete theme contract as its tree

**Observed baseline, 2026-11-12 UTC, #603:** independent actual-public-main `d27a3164` measurement of the toolkit's “Honest evidence” right-outline link reported 17.58:1 normal dark contrast but 1.0193:1 when hovered. The hovered foreground was `rgb(238,242,248)` on the kit's fallback `rgb(238,241,228)` background; `--cad-nav-hover` was empty. Light hover was 13.02:1. The left navigation and right outline both consume kit nav styles, but only `cad-nav` received the complete site-theme token binding.

**Corrective rule:** bind the same foreground, background, hover, current, accent and line tokens to both consumers. A readable resting link does not establish hover/focus/current readability. The existing whole-page WCAG predicate is shared with targeted outline-state checks, including a planted pale-background negative; its 4.5:1 normal-text threshold is unchanged. Keep the exact recorded commit instant in the footer and format it in the named Pacific timezone rather than truncating it or assuming a fixed UTC offset.

**Compatibility/testing limits:** the new hierarchy uses one page-placement/ancestor projection for topic links and result facets. Saved legacy type/status/licence/demo/maturity filters and maturity sorting remain data behavior, with no normal maturity UI. Old item/group fragments must reveal the actual row, not merely exist as invisible IDs. The old flat-card, maturity-bar and modal-sheet browser assertions are replaced by the new shell's real filter/bookmark/history/native-disclosure contracts; hostile URL/data, early/late gallery failure, no-JS/module/top-loader failure and unchanged reading/contrast thresholds remain tested. Local pure checks do not establish hosted WebKit or final public acceptance.
