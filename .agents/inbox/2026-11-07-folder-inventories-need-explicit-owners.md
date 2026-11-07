# Folder inventories need NUL-safe names and explicit consumer ownership

On 2026-11-07 UTC, the #113 read-only map study first split ordinary `git ls-tree` output on lines. Git quoted a vendored Unicode filename, producing invented quoted parent paths in that rejected inventory. The corrected inventory used `git ls-files -z`, decoded UTF-8 and split only on NUL. Historical 58/110 and 61/112 counts used declared exclusions; they are dated inventories, not completeness percentages or asserted missing-README defect counts.

At that audited revision, the installer treated every `.agents/agents/*.md` as a role prompt. An ordinary README there failed the existing frontmatter/discovery control. Generated figures, fixture trees and imported projects have different consumers from owned source packages; blindly adding READMEs or suppressing all unmatched folders would misrepresent ownership.

## Evidence and correction

- `node tools/site/compiler/site-repo-map.mjs --check` derives folders from a NUL-delimited Git inventory. Its current snapshot has 1,034 folders including fixture/upstream descendants; the number is not a quality score.
- `node --test tests/site/website-repo-map.test.mjs`: 18 structural tests pass locally. The actual Git fixture preserves a space/Unicode name and a filename containing a newline. Missing owner/diagram/table/up/down/member links, a new unmapped source child, a new unmapped fixture set and an unindexed incident are rejected.
- `python -m pytest -q tests/repo/test_layout.py tests/repo/test_areas.py tests/repo/test_cut_release.py tests/cli/test_agentkit.py`: 119 pass. Existing role discovery/frontmatter behavior and the root 14 budget remain enforced. The existing 42-file web-kit namespace warning remains; this map change moves no served module URLs and adds no executable module there.
- Initial structural run failed on its own newly added test missing from the site README and on a synthetic index self-link requirement. The owner row was added and the checker now excludes only the authoritative index itself from indexing itself. The original 16-pass/2-failure result is retained in the PR evidence; no defective run is counted as a pass.

## Actual CI and review findings

The first full CI head `3f697b98` exposed real consumers the initial structural slice did not exercise. Both browser jobs stopped in the existing vendor integrity test because the new owned vendor map lacked its recorded SHA-256. It is now bound in the existing viewer receipt; the all-file integrity requirement stays strict. Core 3.12 found two more exact failures: the two new starter child READMEs needed wheel data entries, and five new deep example README leaves were picked by the weekly Markdown glob despite remaining source-only. The package list and five explicit source-only paths were corrected. An initial inference about the image map was withdrawn after reading the full set difference; it was present in both sets and was not the cause.

Before the vendor failure, actual Chromium CI drew all 83 owned-map blocks in both themes: 166 fresh drawings, zero fallback/uncovered labels, 25.7 s. This is component evidence, not a passing whole-browser job. Independent source review also found a real checker bug: ownership delegation had accidentally exempted authored role/resource/policy Markdown from local-link checks. Explicit upstream/data link exemptions are now separate, with actual role/resource/policy negatives and typed policy/direct-skill-resource controls.

After the normal current-dev composition, 30 Node checks pass with the one explicit CI-only render locally skipped; 261 Python checks pass with the native CAD-dependent starter build locally skipped. Final required CI must exercise the full wheel/native and public site consumers. Every declared public owner destination is checked against actual built HTML, Markdown twin and catalogue output; source selection alone is not that evidence. The large inventory stays complete inside closed owner-grouped disclosures after a compact navigation table.

## Validate the publisher rather than inferring public links

The next head `92042358` passed its Python declarations but actual site consumers exposed three remaining issues: new raw-copied model/vendor Markdown links were correct in the repo yet wrong in their served namespaces; the new map test confused rewritten Markdown destinations with HTML URLs; and two new normal owner pages lacked catalogue-area placement. The copied-link class already has its [canonical rule](publish/2026-11-07-source-records-need-their-actual-namespace.md#a-copied-kit-readme-also-needs-its-own-namespace). Use source URLs valid in both namespaces and retain the strict actual Markdown-twin consumer, not a copy exclusion.

Actual WebKit at 920 additionally reported 740px map and 827px receipt diagrams against 641px room, plus a 1205px guide-index reading wall against 1200px. Rank grouping/explicit filename wraps and a closed supplementary metadata table preserve every name and row; no bound changes. The receipt map now shows the actual manifest→corpus-result relation and independent ownership of the other dated records.

A parent-authorized bounded headless local run at exact `d93ce8fe` then built 90 pages/220 catalogue entries/34 commands and 274 themed drawings in 44s with existing Node 22/Chrome 151. Real existing Node consumers returned 88 PASS / 1 FAIL / 1 CI-render-skip in 133s, preserving the new failure: generated `/README`-style links were rewritten by the source-aware publisher into GitHub tree URLs. Source selection was not proof of a delivered public route. Generated published-owner links now name physical Markdown sources relative to `docs/map.md`, so the existing alias resolver owns HTML and Markdown destinations. The actual HTML consumer rejects the old GitHub-tree counterexample and requires every public destination's built HTML, twin and catalogue identity. This failed candidate is retained; no unchanged retry is accepted.

## Corrective rule

Use the existing NUL-safe inventory convention and a real consumer-based owner for every directory. Ordinary owned folders require an authored map, explicit direct-file table, up link and child ownership links. A group delegates only to its actual named parent/index/validator: new fixture sets or figure topics still need parent rows, new prompt/resources need explicit owner links, dated incidents need real symptom-index entries, and temporary release fragments still pass the actual release parser. Do not preserve omissions by copying a baseline allowlist.

Keep publication scope separate: `docs/map.md` distinguishes public pages from canonical source-only code/tool/operational maps. It does not add broad new catalogue routes. The existing required Chromium job checks freshness and controls and renders source owner diagrams through the actual kit in both themes; local structural success is not that browser evidence.

## An ownership map does not replace a requested folder README

The 2026-11-07 audit of actual dev `422c9f38a907e31a67a118809ab26f9ca51d25a3` used
`git ls-tree -rz --name-only` and derived directories from the NUL-delimited names. All 1,034 directories had a
declared owner, but 38 still lacked their own README after the original upstream, fixture and GitHub-policy
exception concepts: eight skill roots, role/reference/plugin folders, 22 figure topics, one dated validation run
and four vendor metadata/patch folders. The original literal request remained unmet despite the green owner check.

The correction adds short human maps with actual file tables, parent/child links, existing figure previews and
small Mermaid diagrams. Skill maps link the canonical instructions rather than duplicate them. A typed
`folder-maps` policy keeps historical data prose separate from current authored instructions while requiring
each data directory's own map. The skill's bundled-resource links remain an independent check.

The actual role installer and supply-chain inventory now reserve exactly `.agents/agents/README.md` as a map;
other malformed role Markdown still fails discovery. The role map is explicitly source-only, so publication
does not misclassify it as a third agent. Skill maps copy with their local instructions and references; links
outside the copied bundle use canonical source URLs. Figure maps also use source URLs for captions/producers
outside their raw-copied asset namespace. No historical report, source record, patch or image bytes are rewritten.

**Rule:** test the requested entry point and the real consumers that discover or copy it. Parent ownership and
literal README coverage are different assertions. Keep the original narrow exceptions; do not add a broader
waiver merely to make a folder count pass. Current full tests and actual diagram rendering remain required.

The first local consumer run retained 268 Python passes, eight explicit skips and one failure: the weekly lychee
glob also selected the new source-only figure/run/role maps. The existing test compared actual workflow arguments
against the real publisher and caught that drift. The workflow now selects the publisher's supported document
depths plus the existing explicitly published coupon example, and excludes the role map. Seven obsolete example
exclusions disappear; no network permissions, action pins, result policy or publisher predicate changes. The exact
previously failing parity check then passed. The 26 map controls also passed, with their actual diagram renderer
still explicitly reserved for the existing CI browser job.

## Limits

Relative file/directory destinations are checked; public route/anchor consumers remain the existing site build and browser checks. Source-only Markdown anchors and remote availability are not newly claimed. A diagram rendering successfully does not prove its semantic correctness or physical CAD performance. Upstream and data descendants retain their recorded layouts; parent ownership does not turn them into reviewed toolkit source.

## Preserve dated release history while checking its actual public identities

The branch-flow gate rejected the five attempted historical CHANGELOG link repairs: released history is byte-preserved evidence, including destinations that were correct at release time. Those edits are restored byte-for-byte from actual main `02cbc3c9`; the gate is unchanged. The map checker now treats only the valid dated CHANGELOG history region as a historical namespace: a missing physical destination may resolve through the existing current publication identity contract, with its physical source present and selected. Current authored links and Unreleased remain strict physical-relative. Real controls reject an unknown alias, the same stale alias in Unreleased or an authored guide, an impossible release date and a missing mapped source. This is not a blanket history skip or permission to rewrite shipped records.

## Keep adversarial filenames out of the diagnostic artifact namespace

At `a05fe132`, every actual Chromium product/test step passed, but the job still failed in artifact upload. The successful NUL-safe inventory control left its newline-named file under the broad `/tmp/cad-agent-*` evidence namespace; the uploader correctly rejected that filename for cross-platform transport. The control still creates and verifies real Unicode, spaces and newline filenames through Git. Only its disposable fixture prefix moves outside the evidence namespace, with finally cleanup of exactly the directory this test created, including after an assertion failure. No evidence exclusion, upload relaxation, filename sanitization or control removal substitutes for this fix. Original job failure and step-level distinction remain retained; component passes do not make the failed job green.

Independent review found that lexing the two CHANGELOG regions separately lost cross-section Markdown reference definitions. A planted Unreleased usage with its definition in released history produced no checked link. The new actual control fails before correction and passes after: lex the complete document once, then classify link usages by their top-level dated heading state. Released usages may resolve current selected public identities, regardless of definition location; Unreleased usages and unknown aliases still fail. Reference-definition placement never grants a historical exemption to current text.

A second actual state control places Unreleased after a new dated entry and before the preserved older release. The historical state now resets at EVERY top-level section; only that section being a valid dated release grants alias resolution. The reordered Unreleased counterexample fails before this correction and passes after, while whole-document reference definitions remain resolved. The immutable-history suffix gate is not treated as a substitute for that current-text contract.

The next dedicated CI-only source-map renderer stopped before drawing: that caller omitted the actual publication context that the real CLI uses, so the five preserved historical aliases failed setup. The caller now supplies the same current page-source contract; the parser and immutable-history gate remain strict. The previously locally skipped path must be exercised explicitly through its actual renderer before the corrected candidate is pushed. A passing generic local slice is not evidence for a skipped caller.
