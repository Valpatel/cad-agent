# Annotated numeric cells must leave printable room for part identities and names

On 2026-11-11, Gyropup's actual All orders/BOM table exposed a gap in printable-checklist acceptance. The prior shared75-row and actual queue/pending-plan PDFs had passed, but they did not exercise rich procurement numeric cells. The existing table-only planner fixture (`CHECKLIST_CASE=orders`,150s bound) printed279 real stable IDs while retaining complete quantities, currency strings and Ordered/In hand state, then rejected full Letter printable width: `scrollWidth1006 > innerWidth965`. Full A4 fitted its width but was still unreadable.

Offline `pdftotext -bbox` found all279 IDs once, repeated headers and no out-of-page words in both PDFs. However full A4 produced212 pages and Letter237; measured maximum row heights were4125/6029px. A visual first-page check showed Part descriptions squeezed to one to three characters per line. Matching one actual source row produced one page per paper. Original PDFs, measurements, failed assertion and complete32-path source/data closure are retained with the downstream Gyropup evidence. The fixture build revision0b7b5 and current-source-equivalent ec5 identity remain distinct; the unrelated assembly viewer was isolated, so this is not public/full Build integration evidence.

Cause: treating every numeric-column cell as a single nowrap token let pack/cut/unit/price annotations consume nearly all page width. Multiword nowrap headers compounded the constraint. Text-column min-content width could collapse because arbitrary word breaking was allowed. Plain scalar quantity/mass/hour success did not establish annotated BOM readability. `textContent` also concatenates adjacent block notes; `innerText` would instead drop off-page hidden rows.

Corrective rule: keep plain scalar values/status marks intact, permit annotated numeric text and multiword headers to wrap at word boundaries, and reserve actual space for stable IDs and the primary description. Preserve semantic note boundaries without using layout-dependent hidden-row text extraction. Product adapters may omit their own redundant mobile-only labels while retaining every meaningful pack/cut/price note; generic toolkit behavior stays shared. Check readable name widths, row height against a printable sheet, exact full/matched IDs/status/value text and actual multipage A4/Letter output. Page bounds and ID completeness alone are insufficient.

A first width-only candidate reduced full output to72 A4/75 Letter pages, but still failed: the longest sourcing narrative made one grouped row810/946px high. Those failed PDFs and its exact renderer hash84cd069e are retained too. The next candidate moves only supporting text cells longer than240 characters to a full-width labelled note under the same stable-key part, leaving quantities/currency/status/name fields in the main row; grouped sheet-height checks cover both rows.

The focused shared fixture now covers a long-name procurement table with quantity/pack/cut/unit/currency notes, per-part pending warnings and all original state/sorting/filter controls. Scalar1106/72.5 and actual pending-plan acceptance remain separate required regressions. Candidate source/PDF results and independent review must be recorded before merge; this note does not establish a passing correction or release.

Limits: source-fixture acceptance is separate from real public assembly integration, hosted CI, physical printers, manufacturing release and physical qualification. No CAD, geometry or device action follows from printable-layout checks.

## Concrete candidate acceptance and remaining gates

Shared sourcec9794848 and downstream functionala781e8e1 keep identical component SHA256a207cd6ed535d020fdcc9056055de0f92a0f0645863a2ce3064d6498acb985b4. The existing shared Chromium suite passes with40 distinct long sourcing-note records; actual14-page A4/Letter PDFs place every unique note record on the same page as its own part, with all40 IDs once/in order. Tracker unit tests pass5/5.

The actual279-part BOM passes full/matched source-fixture checks after fresh build: full45 A4/50 Letter pages, one actual matched part1/1 pages; all quantities/currency/status/supporting source text retained, readable names and grouped rows fitting their sheets. Independent offline audits check all279 IDs once/in order, headers on every page, page bounds and36 complete long notes on their own part's page. The longest2990-character note was visually checked on A4 page14 and Letter page15. Complete historical sourcing makes the full list long; filtering and scope labels stay explicit rather than discarding source history to reduce page counts.

Prior downstream queue controls pass:54 IDs/3 pages and whole1106/72.5/Hours; pending23 IDs/2 pages/all21 warnings. Active desktop/phone grids and seeded header misalignment, scope/state preservation and singleton printing remain covered. The transient old single-tbody assertion was corrected to explicit main-part selectors and retained separately as a harness failure. Source-fixture assembly isolation, the original failed PDFs, normal CI/WebKit, fresh exact-head independent review and actual released/public integration remain distinct claims.


## Keep printing actions visible and fold long API contracts

On 2026-11-11, normal browser run 43069569035 at shared head 7ea57fde reached
`node tests/site/website-browser.mjs` and rejected the extended `/docs/web-parts`:
Chromium job 130693470643 measured 1641 px and WebKit job 130693471457 measured 1630 px
against the unchanged 1200 px desktop reading limit. This was a published-reference
presentation regression; it was not a provisioning or printable-renderer failure.

Cause: the expanded print options, note predicate and DOM contract created a long
continuous stretch between the existing visuals. Keep the printing purpose and an
actionable constructor example visible, and retain the complete detailed reference
inside a named native disclosure. Clarify that `data-print="omit"` is only for purely
decorative pictures or control-only columns: placement/setup/manufacturing instructions
must remain plain text or labelled supporting notes. This clarification addresses a
separate product-adapter fidelity risk without changing generic component behavior.

A bounded actual-route probe used existing Node 22, Google Chrome 151.0.7922.71 and
`site-walls.mjs` at 1366×800. Committed 7ea57fde before: 1641 px; corrected default page: 958 px,
in light and dark, below the same 1200 px limit. The final documentation SHA-256 is
`8f4c6d0f96e39a2d0c8bd49f7c4cb80c7c2e2d83f66c0bcc7a48137d45eae8d0`.
At 320/360/1100/1366 px in both themes, an ordinary summary click exposes all API/DOM
reference text with no page overflow. Phone checks establish horizontal fit and
reference access; the 1200 px wall criterion is defined for the desktop viewport.
All previous reference details remain, apart from the explicit omission-guidance
clarification. Shared component SHA-256 remains exactly a207cd6ed535d020fdcc9056055de0f92a0f0645863a2ce3064d6498acb985b4.

Limits: the local before/after builds explicitly use client-drawn diagrams. New-head
normal CI must still establish complete prerendered publication and both browser
engines. No threshold, renderer, CAD, geometry, printer or device change is included.
